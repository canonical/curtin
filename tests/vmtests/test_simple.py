from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestSimple(VMBaseClass):
    # Test that curtin with no config does the right thing
    conf_file = "examples/tests/simple.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
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
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["sfdisk_list", "blkid",
                                 "proc_partitions"])


class TrustyTestSimple(relbase.trusty, TestSimple):
    __test__ = True


class XenialTestSimple(relbase.xenial, TestSimple):
    __test__ = True


class ArtfulTestSimple(relbase.artful, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])


class BionicTestSimple(relbase.bionic, TestSimple):
    __test__ = True

    def test_output_files_exist(self):
        self.output_files_exist(["netplan.yaml"])
