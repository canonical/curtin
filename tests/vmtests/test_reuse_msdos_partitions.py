# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase


class TestReuseMSDOSPartitions(VMBaseClass):
    """ Curtin can reuse MSDOS partitions with flags. """
    conf_file = "examples/tests/reuse-msdos-partitions.yaml"
    test_stype = 'storage'

    @skip_if_flag('expected_failure')
    def test_simple(self):
        pass


class BionicTestReuseMSDOSPartitions(relbase.bionic,
                                     TestReuseMSDOSPartitions):
    __test__ = True


class FocalTestReuseMSDOSPartitions(relbase.focal,
                                    TestReuseMSDOSPartitions):
    __test__ = True


class JammyTestReuseMSDOSPartitions(relbase.jammy,
                                    TestReuseMSDOSPartitions):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
