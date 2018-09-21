# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestSimple(VMBaseClass):
    # Test that curtin with no config does the right thing
    conf_file = "examples/tests/simple.yaml"
    extra_disks = []
    extra_nics = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp /etc/netplan/50-cloud-init.yaml netplan.yaml
        """)]


class Centos70TestSimple(centos_relbase.centos70_xenial, TestSimple):
    __test__ = True


class TrustyTestSimple(relbase.trusty, TestSimple):
    __test__ = True


class XenialTestSimple(relbase.xenial, TestSimple):
    __test__ = True


class BionicTestSimple(relbase.bionic, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class CosmicTestSimple(relbase.cosmic, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])

# vi: ts=4 expandtab syntax=python
