from . import VMBaseClass
from unittest import TestCase

import textwrap
import os


class TestMdadmAbs(VMBaseClass, TestCase):
    __test__ = False
    repo = "maas-daily"
    arch = "amd64"
    install_timeout = 600
    boot_timeout = 100
    interactive = False
    extra_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        mdadm --detail --scan > mdadm_status
        ls /dev/disk/by-dname > ls_dname
        """)]

    def test_mdadm_status(self):
        with open(os.path.join(self.td.mnt, "mdadm_status"), "r") as fp:
            mdadm_status = fp.read()
        self.assertTrue("/dev/md/ubuntu" in mdadm_status)

    def test_mdadm_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "mdadm_status", "ls_dname"])

    def test_bcache_status(self):
        bcache_cset_uuid = None
        with open(os.path.join(self.td.mnt, "bcache_super_vda6"), "r") as fp:
            for line in fp.read().splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        with open(os.path.join(self.td.mnt, "bcache_ls"), "r") as fp:
            self.assertTrue(bcache_cset_uuid in fp.read().splitlines())


class TestMdadmBcacheAbs(TestMdadmAbs):
    conf_file = "examples/tests/mdadm_bcache.yaml"
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'main_disk': 3,
                     'main_disk': 4,
                     'main_disk': 5,
                     'main_disk': 6,
                     'md0': 0,
                     'cached_array': 0}

    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda6 > bcache_super_vda6
        ls /sys/fs/bcache > bcache_ls
        """)]
    fstab_expected = {
        '/dev/bcache0': '/media/data'
    }

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_vda6", "bcache_ls"])


class WilyTestMdadmBcache(TestMdadmBcacheAbs):
    __test__ = True
    release = "wily"


class VividTestMdadmBcache(TestMdadmBcacheAbs):
    __test__ = True
    release = "vivid"
