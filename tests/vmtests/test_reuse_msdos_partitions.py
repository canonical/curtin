# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestReuseMSDOSPartitions(VMBaseClass):
    """ Curtin can reuse MSDOS partitions with flags. """
    conf_file = "examples/tests/reuse-msdos-partitions.yaml"
    test_stype = 'storage'

    def test_simple(self):
        pass


class BionicTestReuseMSDOSPartitions(relbase.bionic,
                                     TestReuseMSDOSPartitions):
    __test__ = True


class EoanTestReuseMSDOSPartitions(relbase.eoan,
                                   TestReuseMSDOSPartitions):
    __test__ = True


class FocalTestReuseMSDOSPartitions(relbase.focal,
                                    TestReuseMSDOSPartitions):
    __test__ = True


# vi: ts=4 expandtab syntax=python
