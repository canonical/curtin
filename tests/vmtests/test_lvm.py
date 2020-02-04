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
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 5),
                     ('main_disk', 6),
                     ('vg1-lv1', 0),
                     ('vg1-lv2', 0)]

    def _test_pvs(self, dname_to_vg):
        for dname, vg in dname_to_vg.items():
            kname = self._dname_to_kname(dname)
            self.check_file_strippedline("pvs", "%s=/dev/%s" % (vg, kname))

    def test_pvs(self):
        dname_to_vg = {
            'main_disk-part5': 'vg1',
            'main_disk-part6': 'vg1',
        }
        return self._test_pvs(dname_to_vg)

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv1=vg1")
        self.check_file_strippedline("lvs", "lv2=vg1")

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "ls_dname"])

    def get_fstab_expected(self):
        data_kname = self._dname_to_kname('vg1-lv1')
        srv_kname = self._dname_to_kname('vg1-lv2')
        return [
            (self._kname_to_uuid_devpath('dm-uuid', data_kname),
             '/srv/data', 'defaults'),
            (self._kname_to_uuid_devpath('dm-uuid', srv_kname),
             '/srv/backup', 'defaults'),
        ]


class Centos70XenialTestLvm(centos_relbase.centos70_xenial, TestLvmAbs):
    __test__ = True


class XenialGATestLvm(relbase.xenial_ga, TestLvmAbs):
    __test__ = True


class XenialHWETestLvm(relbase.xenial_hwe, TestLvmAbs):
    __test__ = True


class XenialEdgeTestLvm(relbase.xenial_edge, TestLvmAbs):
    __test__ = True


class BionicTestLvm(relbase.bionic, TestLvmAbs):
    __test__ = True


class EoanTestLvm(relbase.eoan, TestLvmAbs):
    __test__ = True


class FocalTestLvm(relbase.focal, TestLvmAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
