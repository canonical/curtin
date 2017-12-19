from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap
import os


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
        fname = os.path.join(self.td.collect, "bcache_super_vda2")
        with open(fname, "r") as fp:
            for line in fp.read().splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        with open(os.path.join(self.td.collect, "bcache_ls"), "r") as fp:
            self.assertTrue(bcache_cset_uuid in fp.read().splitlines())

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


class VividTestRaid5Bcache(relbase.vivid, TestMdadmBcacheAbs):
    __test__ = True


class WilyTestRaid5Bcache(relbase.wily, TestMdadmBcacheAbs):
    __test__ = True
