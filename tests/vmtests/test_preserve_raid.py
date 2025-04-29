# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestPreserveRAID(VMBaseClass):
    """ Test that curtin can reuse a RAID. """
    conf_file = "examples/tests/preserve-raid.yaml"
    extra_disks = ['10G', '10G', '10G']
    uefi = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /srv > ls-srv
        exit 0
        """)]

    def test_existing_exists(self):
        self.assertIn('existing', self.load_collect_file('ls-srv'))


class BionicTestPreserveRAID(relbase.bionic, TestPreserveRAID):
    __test__ = True


class FocalTestPreserveRAID(relbase.focal, TestPreserveRAID):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestPreserveRAID(relbase.jammy, TestPreserveRAID):
    skip = True  # XXX Broken for now
    __test__ = True


class TestPartitionExistingRAID(VMBaseClass):
    """ Test that curtin can repartition an existing RAID. """
    conf_file = "examples/tests/partition-existing-raid.yaml"
    extra_disks = ['10G', '10G', '10G']
    uefi = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        lsblk --nodeps --noheading --raw --output PTTYPE /dev/md1 > md1-pttype
        exit 0
        """)]

    def test_correct_ptype(self):
        self.assertEqual('gpt', self.load_collect_file('md1-pttype').strip())


class BionicTestPartitionExistingRAID(
        relbase.bionic, TestPartitionExistingRAID):
    __test__ = True

    def test_correct_ptype(self):
        self.skipTest("lsblk on bionic does not support PTTYPE")


class FocalTestPartitionExistingRAID(
        relbase.focal, TestPartitionExistingRAID):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestPartitionExistingRAID(
        relbase.jammy, TestPartitionExistingRAID):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
