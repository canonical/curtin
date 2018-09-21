# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import os
import textwrap

centos70_xenial = centos_relbase.centos70_xenial


class TestNvmeAbs(VMBaseClass):
    arch_skip = [
        "s390x",  # nvme is a pci device, no pci on s390x
    ]
    test_type = 'storage'
    interactive = False
    conf_file = "examples/tests/nvme.yaml"
    extra_disks = []
    nvme_disks = ['4G', '4G']
    disk_to_check = [('main_disk', 1), ('main_disk', 2), ('main_disk', 15),
                     ('nvme_disk', 1), ('nvme_disk', 2), ('nvme_disk', 3),
                     ('second_nvme', 1)]
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/class/ > sys_class
        ls /sys/class/nvme/ > ls_nvme
        ls /dev/nvme* > ls_dev_nvme
        """)]

    def _test_nvme_device_names(self, expected):
        self.output_files_exist(["ls_nvme", "ls_dev_nvme"])
        print('expected: %s' % expected)
        if os.path.getsize(self.collect_path('ls_dev_nvme')) > 0:
            print('using ls_dev_nvme')
            for device in ['/dev/' + dev for dev in expected]:
                print('checking device: %s' % device)
                self.check_file_strippedline("ls_dev_nvme", device)

        # trusty and vivid do not have sys/class/nvme but
        # nvme devices do work
        else:
            print('using ls_nvme')
            for device in expected:
                print('checking device: %s' % device)
                self.check_file_strippedline("ls_nvme", device)

    def test_nvme_device_names(self):
        self._test_nvme_device_names(['nvme0', 'nvme1'])


class Centos70TestNvme(centos70_xenial, TestNvmeAbs):
    __test__ = True


class TrustyTestNvme(relbase.trusty, TestNvmeAbs):
    __test__ = True


class TrustyHWEXTestNvme(relbase.trusty_hwe_x, TestNvmeAbs):
    __test__ = True


class XenialGATestNvme(relbase.xenial_ga, TestNvmeAbs):
    __test__ = True


class XenialHWETestNvme(relbase.xenial_hwe, TestNvmeAbs):
    __test__ = True


class XenialEdgeTestNvme(relbase.xenial_edge, TestNvmeAbs):
    __test__ = True


class BionicTestNvme(relbase.bionic, TestNvmeAbs):
    __test__ = True


class CosmicTestNvme(relbase.cosmic, TestNvmeAbs):
    __test__ = True


class TestNvmeBcacheAbs(TestNvmeAbs):
    arch_skip = [
        "s390x",  # nvme is a pci device, no pci on s390x
    ]
    interactive = False
    conf_file = "examples/tests/nvme_bcache.yaml"
    extra_disks = ['10G']
    nvme_disks = ['6G']
    uefi = True
    disk_to_check = [('sda', 1), ('sda', 2), ('sda', 3)]

    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/class/ > sys_class
        ls /sys/class/nvme/ > ls_nvme
        ls /dev/nvme* > ls_dev_nvme
        ls -al /dev/bcache/by-uuid/ > ls_bcache_by_uuid |:
        bcache-super-show /dev/nvme0n1p1 > bcache_super_nvme0n1p1
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        """)]

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_nvme0n1p1", "bcache_ls",
                                 "bcache_cache_mode"])

    def test_nvme_device_names(self):
        self._test_nvme_device_names(['nvme0', 'nvme0n1', 'nvme0n1p1'])

    def test_bcache_status(self):
        bcache_cset_uuid = None
        bcache_super = self.load_collect_file("bcache_super_nvme0n1p1")
        for line in bcache_super.splitlines():
            if line != "" and line.split()[0] == "cset.uuid":
                bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        self.assertTrue(bcache_cset_uuid in
                        self.load_collect_file("bcache_ls").splitlines())

    def test_bcache_cachemode(self):
        self.check_file_regex("bcache_cache_mode", r"\[writeback\]")


class XenialGATestNvmeBcache(relbase.xenial_ga, TestNvmeBcacheAbs):
    __test__ = True


class XenialHWETestNvmeBcache(relbase.xenial_hwe, TestNvmeBcacheAbs):
    __test__ = True


class XenialEdgeTestNvmeBcache(relbase.xenial_edge, TestNvmeBcacheAbs):
    __test__ = True


class BionicTestNvmeBcache(relbase.bionic, TestNvmeBcacheAbs):
    __test__ = True


class CosmicTestNvmeBcache(relbase.cosmic, TestNvmeBcacheAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
