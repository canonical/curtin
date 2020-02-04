# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestReuseRAIDMember(VMBaseClass):
    """ Curtin can install to a RAID member if other members are missing. """
    conf_file = "examples/tests/reuse-raid-member-wipe.yaml"
    extra_disks = ['10G', '10G']
    uefi = True

    def test_simple(self):
        pass


class TestReuseRAIDMemberPartition(VMBaseClass):
    """ Curtin can install to a RAID member if other members are missing. """
    conf_file = "examples/tests/reuse-raid-member-wipe.yaml"
    extra_disks = ['10G', '10G']
    uefi = True

    def test_simple(self):
        pass


class BionicTestReuseRAIDMember(relbase.bionic, TestReuseRAIDMember):
    __test__ = True


class EoanTestReuseRAIDMember(relbase.eoan, TestReuseRAIDMember):
    __test__ = True


class FocalTestReuseRAIDMember(relbase.focal, TestReuseRAIDMember):
    __test__ = True


class BionicTestReuseRAIDMemberPartition(relbase.bionic,
                                         TestReuseRAIDMemberPartition):
    __test__ = True


class EoanTestReuseRAIDMemberPartition(relbase.eoan,
                                       TestReuseRAIDMemberPartition):
    __test__ = True


class FocalTestReuseRAIDMemberPartition(relbase.focal,
                                        TestReuseRAIDMemberPartition):
    __test__ = True


# vi: ts=4 expandtab syntax=python
