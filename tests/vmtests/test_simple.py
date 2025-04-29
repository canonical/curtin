# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import os
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


class Centos70XenialTestSimple(centos_relbase.centos70_xenial, TestSimple):
    __test__ = True


class Centos70BionicTestSimple(centos_relbase.centos70_bionic, TestSimple):
    __test__ = True


class XenialTestSimple(relbase.xenial, TestSimple):
    __test__ = True


class BionicTestSimple(relbase.bionic, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class FocalTestSimple(relbase.focal, TestSimple):
    skip = True  # XXX Broken for now
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class JammyTestSimple(relbase.jammy, TestSimple):
    skip = True  # XXX Broken for now
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

    @skip_if_flag('expected_failure')
    def test_output_files_exist(self):
        self.output_files_exist(["sfdisk_list", "blkid",
                                 "proc_partitions"])


class XenialGATestSimpleStorage(relbase.xenial, TestSimpleStorage):
    __test__ = True


class BionicTestSimpleStorage(relbase.bionic, TestSimpleStorage):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class FocalTestSimpleStorage(relbase.focal, TestSimpleStorage):
    skip = True  # XXX Broken for now
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class JammyTestSimpleStorage(relbase.jammy, TestSimpleStorage):
    skip = True  # XXX Broken for now
    __test__ = True

    @skip_if_flag('expected_failure')
    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class TestGrubNoDefaults(VMBaseClass):
    """ Test that curtin does not emit any grub configuration files. """
    conf_file = "examples/tests/no-grub-file.yaml"
    extra_disks = []
    extra_nics = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp /etc/netplan/50-cloud-init.yaml netplan.yaml

        exit 0
        """)]

    def test_no_grub_file_created(self):
        """ Curtin did not write a grub configuration file. """
        grub_d_path = self.collect_path('etc_default_grub_d')
        grub_d_files = os.listdir(grub_d_path)
        self.assertNotIn('50-curtin-settings.cfg', grub_d_files)


class FocalTestGrubNoDefaults(relbase.focal, TestGrubNoDefaults):
    skip = True  # XXX Broken for now
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class JammyTestGrubNoDefaults(relbase.jammy, TestGrubNoDefaults):
    skip = True  # XXX Broken for now
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


# vi: ts=4 expandtab syntax=python
