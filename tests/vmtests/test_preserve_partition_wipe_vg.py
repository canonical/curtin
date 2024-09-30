# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase

import textwrap


class TestPreserveWipeLvm(VMBaseClass):
    """ Test that curtin can reuse a partition that was previously in lvm. """
    conf_file = "examples/tests/preserve-partition-wipe-vg.yaml"
    extra_disks = ['20G']
    uefi = False
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /opt > ls-opt
        exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_existing_exists(self):
        self.assertIn('existing', self.load_collect_file('ls-opt'))


class BionicTestPreserveWipeLvm(relbase.bionic, TestPreserveWipeLvm):
    __test__ = True


class FocalTestPreserveWipeLvm(relbase.focal, TestPreserveWipeLvm):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestPreserveWipeLvm(relbase.jammy, TestPreserveWipeLvm):
    skip = True  # XXX Broken for now
    __test__ = True


class TestPreserveWipeLvmSimple(VMBaseClass):
    conf_file = "examples/tests/preserve-partition-wipe-vg-simple.yaml"
    uefi = False
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /opt > ls-opt
        exit 0
        """)]


class BionicTestPreserveWipeLvmSimple(relbase.bionic,
                                      TestPreserveWipeLvmSimple):
    __test__ = True


class FocalTestPreserveWipeLvmSimple(relbase.focal, TestPreserveWipeLvmSimple):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestPreserveWipeLvmSimple(relbase.jammy, TestPreserveWipeLvmSimple):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
