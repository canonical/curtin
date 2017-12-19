from . import VMBaseClass
from unittest import TestCase

import textwrap
import os


class TestMdadmBcacheAbs(VMBaseClass):
    __test__ = False
    conf_file = "examples/tests/lvm.yaml"
    install_timeout = 600
    boot_timeout = 100
    interactive = False
    extra_disks = []
    user_data = textwrap.dedent("""\
        #cloud-config
        password: passw0rd
        chpasswd: { expire: False }
        bootcmd:
          - mkdir -p /media/output
        runcmd:
          - cat /etc/fstab > /media/output/fstab
          - ls /dev/disk/by-dname > /media/output/ls_dname
          - pvdisplay -C --separator = -o vg_name,pv_name --noheadings > \
                  /media/output/pvs
          - lvdisplay -C --separator = -o lv_name,vg_name --noheadings > \
                  /media/output/lvs
          - [tar, -C, /media/output, -cf, /dev/vdb, .]
        power_state:
          mode: poweroff
        """)

    def test_fstab(self):
        with open(os.path.join(self.td.mnt, "fstab")) as fp:
            fstab_lines = fp.readlines()
        fstab_entry = None
        for line in fstab_lines:
            if "/dev/vg1/lv1" in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/srv/data")

    def test_lvs(self):
        with open(os.path.join(self.td.mnt, "lvs"), "r") as fp:
            lv_data = list(i.strip() for i in fp.readlines())
        self.assertIn("lv1=vg1", lv_data)
        self.assertIn("lv2=vg1", lv_data)

    def test_pvs(self):
        with open(os.path.join(self.td.mnt, "pvs"), "r") as fp:
            lv_data = list(i.strip() for i in fp.readlines())
        self.assertIn("vg1=/dev/vda5", lv_data)
        self.assertIn("vg1=/dev/vda6", lv_data)

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "ls_dname"])

    def test_dname(self):
        with open(os.path.join(self.td.mnt, "ls_dname"), "r") as fp:
            contents = fp.read().splitlines()
        for link in list(("main_disk-part%s" % i for i in (1, 5, 6))):
            self.assertIn(link, contents)
        self.assertIn("main_disk", contents)
        self.assertIn("vg1-lv1", contents)
        self.assertIn("vg1-lv2", contents)


class WilyTestLvm(TestMdadmBcacheAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestLvm(TestMdadmBcacheAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"
