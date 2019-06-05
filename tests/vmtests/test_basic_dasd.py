# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestBasicDasd(VMBaseClass):
    """ Test curtin formats dasd devices and uses them as disks. """
    conf_file = "examples/tests/basic-dasd.yaml"
    dirty_disks = False
    disk_driver = 'virtio-blk-ccw'
    extra_disks = ['/dev/dasdd']
    extra_nics = []
    # dasd is s390x only
    arch_skip = ["amd64", "arm64", "i386", "ppc64el"]
    test_type = 'storage'
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        lsdasd > lsdasd.out
        sfdisk --list > sfdisk_list
        for d in /dev/[sv]d[a-z] /dev/xvd? /dev/dasd?; do
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


class XenialGATestBasicDasd(relbase.xenial, TestBasicDasd):
    __test__ = True


class BionicTestBasicDasd(relbase.bionic, TestBasicDasd):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class CosmicTestBasicDasd(relbase.cosmic, TestBasicDasd):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class DiscoTestBasicDasd(relbase.disco, TestBasicDasd):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class EoanTestBasicDasd(relbase.eoan, TestBasicDasd):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])

# vi: ts=4 expandtab syntax=python
