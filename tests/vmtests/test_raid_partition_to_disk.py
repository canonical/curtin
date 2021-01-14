# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestRAIDPartitionToDisk(VMBaseClass):
    """Convert a RAID made of partitions to one made of disks."""
    conf_file = "examples/tests/raid-partition-to-disk.yaml"
    extra_disks = ['10G', '10G', '10G']
    uefi = True

    def test_simple(self):
        pass


class BionicTestRAIDPartitionToDisk(relbase.bionic, TestRAIDPartitionToDisk):
    __test__ = True


class FocalTestRAIDPartitionToDisk(relbase.focal, TestRAIDPartitionToDisk):
    __test__ = True


class HirsuteTestRAIDPartitionToDisk(relbase.hirsute, TestRAIDPartitionToDisk):
    __test__ = True


class GroovyTestRAIDPartitionToDisk(relbase.groovy, TestRAIDPartitionToDisk):
    __test__ = True


# vi: ts=4 expandtab syntax=python
