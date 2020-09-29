# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestReuseLVMMemberPartition(VMBaseClass):
    """ Curtin can install to a LVM member if other members are missing. """
    conf_file = "examples/tests/reuse-lvm-member-partition.yaml"
    extra_disks = ['10G', '10G']
    disk_driver = 'scsi-hd'
    test_stype = 'storage'
    uefi = True

    def test_simple(self):
        pass


class BionicTestReuseLVMMemberPartition(relbase.bionic,
                                        TestReuseLVMMemberPartition):
    __test__ = True


class FocalTestReuseLVMMemberPartition(relbase.focal,
                                       TestReuseLVMMemberPartition):
    __test__ = True


class GroovyTestReuseLVMMemberPartition(relbase.groovy,
                                        TestReuseLVMMemberPartition):
    __test__ = True


# vi: ts=4 expandtab syntax=python
