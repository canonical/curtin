# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestPreserve(VMBaseClass):
    """ Test that curtin can reuse a partition. """
    conf_file = "examples/tests/preserve.yaml"
    extra_disks = ['10G']
    uefi = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /srv > ls-srv
        exit 0
        """)]

    def test_existing_exists(self):
        self.assertIn('existing', self.load_collect_file('ls-srv'))


class BionicTestPreserve(relbase.bionic, TestPreserve):
    __test__ = True


class FocalTestPreserve(relbase.focal, TestPreserve):
    __test__ = True


class GroovyTestPreserve(relbase.groovy, TestPreserve):
    __test__ = True


# vi: ts=4 expandtab syntax=python
