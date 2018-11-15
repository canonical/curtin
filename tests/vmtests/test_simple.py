# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestSimple(VMBaseClass):
    """ Test that curtin runs block-meta simple mode correctly. """
    conf_file = "examples/tests/simple.yaml"
    extra_disks = []
    extra_nics = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp /etc/netplan/50-cloud-init.yaml netplan.yaml

        exit 0
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


class DiscoTestSimple(relbase.disco, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class TestSimpleStorage(VMBaseClass):
    """ Test curtin runs clear-holders when mode=simple with storage cfg. """
    conf_file = "examples/tests/simple-storage.yaml"
    dirty_disks = True
    extra_disks = ['5G', '5G']
    extra_nics = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        sfdisk --list > sfdisk_list
        for d in /dev/[sv]d[a-z] /dev/xvd?; do
            [ -b "$d" ] || continue
            echo == $d ==
            sgdisk --print $d
        done > sgdisk_list
        blkid > blkid
        cat /proc/partitions > proc_partitions
        cp /etc/network/interfaces interfaces
        cp /etc/netplan/50-cloud-init.yaml netplan.yaml
        if [ -f /var/log/cloud-init-output.log ]; then
           cp /var/log/cloud-init-output.log .
        fi
        cp /var/log/cloud-init.log .
        find /etc/network/interfaces.d > find_interfacesd
        exit 0
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["sfdisk_list", "blkid",
                                 "proc_partitions"])


class XenialGATestSimpleStorage(relbase.xenial, TestSimpleStorage):
    __test__ = True


class BionicTestSimpleStorage(relbase.bionic, TestSimpleStorage):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class CosmicTestSimpleStorage(relbase.cosmic, TestSimpleStorage):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class DiscoTestSimpleStorage(relbase.disco, TestSimpleStorage):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


# vi: ts=4 expandtab syntax=python
