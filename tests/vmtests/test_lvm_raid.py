# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .test_mdadm_bcache import TestMdadmAbs
from .test_lvm import TestLvmAbs

import textwrap


class TestLvmOverRaidAbs(TestMdadmAbs, TestLvmAbs):
    conf_file = "examples/tests/lvmoverraid.yaml"
    active_mdadm = "2"
    nr_cpus = 2
    dirty_disks = True
    extra_disks = ['10G'] * 4

    extra_collect_scripts = (
        TestLvmAbs.extra_collect_scripts +
        TestMdadmAbs.extra_collect_scripts +
        [textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            ls -al /dev/md* > dev_md
            cp -a /etc/mdadm etc_mdadm
            cp -a /etc/lvm etc_lvm

            exit 0
            """)]
        )
    disk_to_check = [('main_disk', 1),
                     ('md0', 0),
                     ('md1', 0)]

    def get_fstab_expected(self):
        rootdev = self._dname_to_kname('main_disk')
        homedev = self._dname_to_kname('vg0-lv--0')
        return [
            (self._kname_to_byuuid(rootdev + '2'), '/', 'defaults'),
            (self._kname_to_uuid_devpath('dm-uuid', homedev),
             '/home', 'defaults'),
        ]

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv-0=vg0")

    def test_pvs(self):
        dname_to_vg = {'md0': 'vg0', 'md1': 'vg0'}
        return self._test_pvs(dname_to_vg)


class FocalTestLvmOverRaid(relbase.focal, TestLvmOverRaidAbs):
    __test__ = True


class EoanTestLvmOverRaid(relbase.eoan, TestLvmOverRaidAbs):
    __test__ = True


class BionicTestLvmOverRaid(relbase.bionic, TestLvmOverRaidAbs):
    __test__ = True


class XenialGATestLvmOverRaid(relbase.xenial_ga, TestLvmOverRaidAbs):
    __test__ = True
