from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestBcacheBasic(VMBaseClass):
    arch_skip = [
        "s390x",  # lp:1565029
    ]
    conf_file = "examples/tests/bcache_basic.yaml"
    nr_cpus = 2
    dirty_disks = True
    extra_disks = ['2G']
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda2 > bcache_super_vda2
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        cat /proc/mounts > proc_mounts
        cat /proc/partitions > proc_partitions
        find /etc/network/interfaces.d > find_interfacesd
        cat /proc/cmdline > cmdline
        """)]

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

    def test_proc_cmdline_root_by_uuid(self):
        self.check_file_regex("cmdline", r"root=UUID=")


class TrustyBcacheBasic(relbase.trusty, TestBcacheBasic):
    __test__ = False  # covered by test_raid5_bcache


class TrustyHWEXBcacheBasic(relbase.trusty_hwe_x, TestBcacheBasic):
    __test__ = False  # covered by test_raid5_bcache


class XenialBcacheBasic(relbase.xenial, TestBcacheBasic):
    __test__ = True


class ZestyBcacheBasic(relbase.zesty, TestBcacheBasic):
    __test__ = True


class ArtfulBcacheBasic(relbase.artful, TestBcacheBasic):
    __test__ = True
