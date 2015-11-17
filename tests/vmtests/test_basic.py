from . import (
    VMBaseClass,
    get_apt_proxy)

from unittest import TestCase

import os
import textwrap


class TestBasicAbs(VMBaseClass):
    __test__ = False
    interactive = False
    conf_file = "examples/tests/basic.yaml"
    install_timeout = 600
    boot_timeout = 120
    extra_disks = ['128G']
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname/ > ls_dname

        v=""
        out=$(apt-config shell v Acquire::HTTP::Proxy)
        eval "$out"
        echo "$v" > apt-proxy
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "fstab", "ls_dname"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_vda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

    def test_dname(self):
        with open(os.path.join(self.td.mnt, "ls_dname"), "r") as fp:
            contents = fp.read().splitlines()
        for link in ["main_disk", "main_disk-part1", "main_disk-part2"]:
            self.assertIn(link, contents)

    def test_partitions(self):
        with open(os.path.join(self.td.mnt, "fstab")) as fp:
            fstab_lines = fp.readlines()
        # Test that vda1 is on /
        blkid_info = self.get_blkid_data("blkid_output_vda1")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/")

        # Test that vda2 is on /home
        blkid_info = self.get_blkid_data("blkid_output_vda2")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/home")

    def test_proxy_set(self):
        expected = get_apt_proxy()
        with open(os.path.join(self.td.mnt, "apt-proxy")) as fp:
            apt_proxy_found = fp.read().rstrip()
        if expected:
            # the proxy should have gotten set through
            self.assertIn(expected, apt_proxy_found)
        else:
            # no proxy, so the output of apt-config dump should be empty
            self.assertEqual("", apt_proxy_found)


class WilyTestBasic(TestBasicAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestBasic(TestBasicAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"


class PreciseTestBasic(TestBasicAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "precise"
    arch = "amd64"

    def test_ptable(self):
        print("test_ptable does not work for Precise")

    def test_dname(self):
        print("test_dname does not work for Precise")
