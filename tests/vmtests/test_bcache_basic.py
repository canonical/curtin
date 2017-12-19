from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap
import os


class TestBcacheBasic(VMBaseClass):
    arch_skip = [
        "s390x",  # lp:1565029
    ]
    conf_file = "examples/tests/bcache_basic.yaml"
    extra_disks = ['2G']
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda2 > bcache_super_vda2
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        cat /proc/mounts > proc_mounts
        cat /proc/partitions > proc_partitions
        """)]

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


class PreciseHWETBcacheBasic(relbase.precise_hwe_t, TestBcacheBasic):
    __test__ = True


class TrustyBcacheBasic(relbase.trusty, TestBcacheBasic):
    __test__ = False  # covered by test_raid5_bcache


class XenialBcacheBasic(relbase.xenial, TestBcacheBasic):
    __test__ = True
