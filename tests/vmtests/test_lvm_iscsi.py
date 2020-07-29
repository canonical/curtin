# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_lvm import TestLvmAbs
from .test_iscsi import TestBasicIscsiAbs

import textwrap


class TestLvmIscsiAbs(TestLvmAbs, TestBasicIscsiAbs):
    interactive = False
    dirty_disks = True
    iscsi_disks = [
        {'size': '6G'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/lvm_iscsi.yaml"
    nr_testfiles = 4

    extra_collect_scripts = (
        TestLvmAbs.extra_collect_scripts +
        TestBasicIscsiAbs.extra_collect_scripts +
        [textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            ls -al /sys/class/block/dm*/slaves/  > dm_slaves

            exit 0
            """)])

    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('iscsi_disk1', 5),
                     ('iscsi_disk1', 6),
                     ('iscsi_disk2', 5),
                     ('iscsi_disk2', 6),
                     ('vg1-lv1', 0),
                     ('vg1-lv2', 0),
                     ('vg2-lv3', 0),
                     ('vg2-lv4', 0)]

    def get_fstab_expected(self):
        iscsi1 = self._dname_to_kname('vg1-lv1')
        iscsi2 = self._dname_to_kname('vg1-lv2')
        iscsi3 = self._dname_to_kname('vg2-lv3')
        iscsi4 = self._dname_to_kname('vg2-lv4')
        return [
            (self._kname_to_uuid_devpath('dm-uuid', iscsi1),
             '/mnt/iscsi1', 'defaults,_netdev'),
            (self._kname_to_uuid_devpath('dm-uuid', iscsi2),
             '/mnt/iscsi2', 'defaults,_netdev'),
            (self._kname_to_uuid_devpath('dm-uuid', iscsi3),
             '/mnt/iscsi3', 'defaults,_netdev'),
            (self._kname_to_uuid_devpath('dm-uuid', iscsi4),
             '/mnt/iscsi4', 'defaults,_netdev'),
        ]

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv1=vg1")
        self.check_file_strippedline("lvs", "lv2=vg1")
        self.check_file_strippedline("lvs", "lv3=vg2")
        self.check_file_strippedline("lvs", "lv4=vg2")

    def test_pvs(self):
        dname_to_vg = {
            'iscsi_disk1-part5': 'vg1',
            'iscsi_disk1-part6': 'vg1',
            'iscsi_disk2-part5': 'vg2',
            'iscsi_disk2-part6': 'vg2',
        }
        return self._test_pvs(dname_to_vg)


class Centos70XenialTestLvmIscsi(centos_relbase.centos70_xenial,
                                 TestLvmIscsiAbs):
    __test__ = True


class XenialTestIscsiLvm(relbase.xenial, TestLvmIscsiAbs):
    __test__ = True


class XenialGATestIscsiLvm(relbase.xenial_ga, TestLvmIscsiAbs):
    __test__ = True


class XenialHWETestIscsiLvm(relbase.xenial_hwe, TestLvmIscsiAbs):
    __test__ = True


class XenialEdgeTestIscsiLvm(relbase.xenial_edge, TestLvmIscsiAbs):
    __test__ = True


class BionicTestIscsiLvm(relbase.bionic, TestLvmIscsiAbs):
    __test__ = True


class FocalTestIscsiLvm(relbase.focal, TestLvmIscsiAbs):
    __test__ = True


class GroovyTestIscsiLvm(relbase.groovy, TestLvmIscsiAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
