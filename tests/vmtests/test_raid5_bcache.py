from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestMdadmAbs(VMBaseClass):
    interactive = False
    extra_disks = ['10G', '10G', '10G', '10G']
    active_mdadm = "1"
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        mdadm --detail --scan > mdadm_status
        mdadm --detail --scan | grep -c ubuntu > mdadm_active1
        grep -c active /proc/mdstat > mdadm_active2
        ls /dev/disk/by-dname > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_mdadm_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "mdadm_status", "mdadm_active1", "mdadm_active2",
             "ls_dname"])

    def test_mdadm_status(self):
        # ubuntu:<ID> is the name assigned to the md array
        self.check_file_regex("mdadm_status", r"ubuntu:[0-9]*")
        self.check_file_strippedline("mdadm_active1", self.active_mdadm)
        self.check_file_strippedline("mdadm_active2", self.active_mdadm)


class TestMdadmBcacheAbs(TestMdadmAbs):
    conf_file = "examples/tests/raid5bcache.yaml"
    disk_to_check = [('md0', 0), ('sda', 2)]

    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda2 > bcache_super_vda2
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        cat /proc/mounts > proc_mounts
        cat /proc/partitions > proc_partitions
        find /etc/network/interfaces.d > find_interfacesd
        """)]
    fstab_expected = {
        '/dev/bcache0': '/',
        '/dev/md0': '/srv/data',
    }

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


class PreciseHWETTestRaid5Bcache(relbase.precise_hwe_t, TestMdadmBcacheAbs):
    # FIXME: off due to failing install: RUN_ARRAY failed: Invalid argument
    __test__ = False


class TrustyTestRaid5Bcache(relbase.trusty, TestMdadmBcacheAbs):
    __test__ = True
    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    disk_to_check = [('md0', 0)]


class TrustyHWEUTestRaid5Bcache(relbase.trusty_hwe_u, TrustyTestRaid5Bcache):
    __test__ = True


class TrustyHWEVTestRaid5Bcache(relbase.trusty_hwe_v, TrustyTestRaid5Bcache):
    __test__ = True


class TrustyHWEWTestRaid5Bcache(relbase.trusty_hwe_w, TrustyTestRaid5Bcache):
    __test__ = False


class WilyTestRaid5Bcache(relbase.wily, TestMdadmBcacheAbs):
    # EOL - 2016-07-28
    __test__ = False


class XenialTestRaid5Bcache(relbase.xenial, TestMdadmBcacheAbs):
    __test__ = True


class YakketyTestRaid5Bcache(relbase.yakkety, TestMdadmBcacheAbs):
    __test__ = True
