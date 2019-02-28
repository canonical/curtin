# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestLvmAbs(VMBaseClass):
    conf_file = "examples/tests/lvm.yaml"
    test_type = 'storage'
    interactive = False
    extra_disks = ['10G']
    dirty_disks = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs

        exit 0
        """)]
    fstab_expected = {
        '/dev/vg1/lv1': '/srv/data',
        '/dev/vg1/lv2': '/srv/backup',
    }
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 5),
                     ('main_disk', 6),
                     ('vg1-lv1', 0),
                     ('vg1-lv2', 0)]

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv1=vg1")
        self.check_file_strippedline("lvs", "lv2=vg1")

    def test_pvs(self):
        self.check_file_strippedline("pvs", "vg1=/dev/vda5")
        self.check_file_strippedline("pvs", "vg1=/dev/vda6")

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "ls_dname"])


class Centos70XenialTestLvm(centos_relbase.centos70_xenial, TestLvmAbs):
    __test__ = True


class TrustyTestLvm(relbase.trusty, TestLvmAbs):
    __test__ = True


class TrustyHWEXTestLvm(relbase.trusty_hwe_x, TestLvmAbs):
    __test__ = True


class XenialGATestLvm(relbase.xenial_ga, TestLvmAbs):
    __test__ = True


class XenialHWETestLvm(relbase.xenial_hwe, TestLvmAbs):
    __test__ = True


class XenialEdgeTestLvm(relbase.xenial_edge, TestLvmAbs):
    __test__ = True


class BionicTestLvm(relbase.bionic, TestLvmAbs):
    __test__ = True


class CosmicTestLvm(relbase.cosmic, TestLvmAbs):
    __test__ = True


class DiscoTestLvm(relbase.disco, TestLvmAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
