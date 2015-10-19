from . import VMBaseClass
from unittest import TestCase

import textwrap


class TestMdadmBcacheAbs(VMBaseClass, TestCase):
    __test__ = False
    conf_file = "examples/tests/lvm.yaml"
    install_timeout = 600
    boot_timeout = 100
    interactive = False
    extra_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname > ls_dname
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        """)]
    fstab_expected = {
        '/dev/vg1/lv1': '/srv/data',
        '/dev/vg1/lv2': '/srv/backup',
    }
    disk_to_check = {'main_disk': 1,
                     'main_disk': 5,
                     'main_disk': 6,
                     'vg1-lv1': 0,
                     'vg1-lv2': 0}

    def test_lvs(self):
        self.check_file_content("lvs", "lv1=vg1")
        self.check_file_content("lvs", "lv2=vg1")

    def test_pvs(self):
        self.check_file_content("pvs", "vg1=/dev/vda5")
        self.check_file_content("pvs", "vg1=/dev/vda6")

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "ls_dname"])


class WilyTestLvm(TestMdadmBcacheAbs):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestLvm(TestMdadmBcacheAbs):
    __test__ = True
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"
