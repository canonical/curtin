# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .test_bcache_basic import TestBcacheBasic


class TestBcachePartitions(TestBcacheBasic):
    conf_file = "examples/tests/bcache-partitions.yaml"
    dirty_disks = True
    nr_cpus = 2
    extra_disks = ['10G', '10G']


class XenialTestBcachePartitions(relbase.xenial, TestBcachePartitions):
    # Xenial 4.4 kernel does not support bcache partitions
    expected_failure = True
    __test__ = True


class XenialHWETestBcachePartitions(relbase.xenial_hwe, TestBcachePartitions):
    __test__ = True


class BionicTestBcachePartitions(relbase.bionic, TestBcachePartitions):
    __test__ = True


class DiscoTestBcachePartitions(relbase.disco, TestBcachePartitions):
    __test__ = True


class EoanTestBcachePartitions(relbase.eoan, TestBcachePartitions):
    __test__ = True


class FocalTestBcachePartitions(relbase.focal, TestBcachePartitions):
    __test__ = True


# vi: ts=4 expandtab syntax=python
