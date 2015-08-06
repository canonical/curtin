from . import VMBaseClass
from unittest import TestCase

import os
import textwrap


class TestBasicAbs(VMBaseClass):
    __test__ = False
    conf_file = "examples/tests/basic.yaml"
    install_timeout = 600
    boot_timeout = 120
    interactive = False
    user_data = textwrap.dedent("""\
        #cloud-config
        password: passw0rd
        chpasswd: { expire: False }
        bootcmd:
          - mkdir /media/output
          - mount /dev/vdb /media/output
        runcmd:
          - blkid -o export /dev/vda > /media/output/blkid_output_vda
          - blkid -o export /dev/vda1 > /media/output/blkid_output_vda1
          - blkid -o export /dev/vda2 > /media/output/blkid_output_vda2
          - cat /etc/fstab > /media/output/fstab
        power_state:
          mode: poweroff
        """)

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "fstab"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_vda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

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
