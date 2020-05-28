# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase

import textwrap


class TestPreserveBcache(VMBaseClass):
    arch_skip = [
        "s390x",  # lp:1565029
    ]
    test_type = 'storage'
    conf_file = 'examples/tests/preserve-bcache.yaml'
    nr_cpus = 2
    dirty_disks = False
    extra_disks = ['2G']
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls / > ls-root
        bcache-super-show /dev/vda2 > bcache_super_vda2
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode

        exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_vda2", "bcache_ls",
                                 "bcache_cache_mode"])

    @skip_if_flag('expected_failure')
    def test_bcache_status(self):
        bcache_cset_uuid = None
        for line in self.load_collect_file("bcache_super_vda2").splitlines():
            if line != "" and line.split()[0] == "cset.uuid":
                bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        self.assertTrue(bcache_cset_uuid in
                        self.load_collect_file("bcache_ls").splitlines())

    @skip_if_flag('expected_failure')
    def test_bcache_cachemode(self):
        self.check_file_regex("bcache_cache_mode", r"\[writeback\]")

    @skip_if_flag('expected_failure')
    def test_proc_cmdline_root_by_uuid(self):
        self.check_file_regex("proc_cmdline", r"root=UUID=")

    def test_preserved_data_exists(self):
        self.assertIn('existing', self.load_collect_file('ls-root'))


class BionicTestPreserveBcache(relbase.bionic, TestPreserveBcache):
    __test__ = True


class EoanTestPreserveBcache(relbase.eoan, TestPreserveBcache):
    __test__ = True


class FocalTestPreserveBcache(relbase.focal, TestPreserveBcache):
    __test__ = True


# vi: ts=4 expandtab syntax=python
