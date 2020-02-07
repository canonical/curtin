# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestMdadmAbs(VMBaseClass):
    interactive = False
    test_type = 'storage'
    extra_disks = ['10G', '10G', '10G', '10G']
    active_mdadm = "1"
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        mdadm --detail --scan > mdadm_status
        mdadm --detail --scan | grep -c ubuntu > mdadm_active1
        grep -c active /proc/mdstat > mdadm_active2

        exit 0
        """)]

    def test_mdadm_output_files_exist(self):
        self.output_files_exist(["mdadm_status", "mdadm_active1",
                                 "mdadm_active2"])

    def test_mdadm_status(self):
        # ubuntu:<ID> is the name assigned to the md array
        self.check_file_regex("mdadm_status", r"ubuntu:[0-9]*")
        self.check_file_strippedline("mdadm_active1", self.active_mdadm)
        self.check_file_strippedline("mdadm_active2", self.active_mdadm)


class TestMdadmBcacheAbs(TestMdadmAbs):
    conf_file = "examples/tests/raid5bcache.yaml"
    disk_to_check = [('md0', 0), ('sda', 2)]
    dirty_disks = True

    extra_collect_scripts = (
        TestMdadmAbs.extra_collect_scripts +
        [textwrap.dedent("""\
            cd OUTPUT_COLLECT_D
            bcache-super-show /dev/vda2 > bcache_super_vda2
            ls /sys/fs/bcache > bcache_ls
            cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
            ls -al /dev/bcache/by-uuid/ > ls_al_bcache_byuuid

            exit 0""")])

    def get_fstab_expected(self):
        bcache0_kname = self._dname_to_kname('bcache0')
        return [
            (self._bcache_to_byuuid(bcache0_kname), '/', 'defaults'),
            (self._kname_to_uuid_devpath('md-uuid', 'md0'),
             '/srv/data', 'defaults')
        ]

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_vda2", "bcache_ls",
                                 "bcache_cache_mode"])

    def test_bcache_status(self):
        bcache_cset_uuid = None
        for line in self.load_collect_file("bcache_super_vda2").splitlines():
            if line != "" and line.split()[0] == "cset.uuid":
                bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        self.assertTrue(bcache_cset_uuid in
                        self.load_collect_file("bcache_ls").splitlines())

    def test_bcache_cachemode(self):
        self.check_file_regex("bcache_cache_mode", r"\[writeback\]")


class XenialGATestRaid5Bcache(relbase.xenial_ga, TestMdadmBcacheAbs):
    __test__ = True


class XenialHWETestRaid5Bcache(relbase.xenial_hwe, TestMdadmBcacheAbs):
    __test__ = True


class XenialEdgeTestRaid5Bcache(relbase.xenial_edge, TestMdadmBcacheAbs):
    __test__ = True


class BionicTestRaid5Bcache(relbase.bionic, TestMdadmBcacheAbs):
    __test__ = True


class EoanTestRaid5Bcache(relbase.eoan, TestMdadmBcacheAbs):
    __test__ = True


class FocalTestRaid5Bcache(relbase.focal, TestMdadmBcacheAbs):
    __test__ = True

    @TestMdadmBcacheAbs.skip_by_date("1861941", fixby="2020-04-15")
    def test_fstab(self):
        return super().test_fstab()


# vi: ts=4 expandtab syntax=python
