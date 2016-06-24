from . import VMBaseClass, logger
from .releases import base_vm_classes as relbase

import ipaddress
import os
import re
import textwrap
import yaml


class TestSimple(VMBaseClass):
    # Test that curtin with no config does the right thing
    conf_file = "examples/tests/simple.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
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
        if [ -f /var/log/cloud-init-output.log ]; then
           cp /var/log/cloud-init-output.log .
        fi
        cp /var/log/cloud-init.log .
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["sfdisk_list", "blkid",
                                 "proc_partitions", "interfaces"])


class TrustyTestSimple(relbase.trusty, TestSimple):
    # FIXME PPC64: this fails because it ends up trying to
    # boot with root=vdb1 rather than how we normally boot
    # which is with root=UUID= .  so update-grub is  making
    # some decision here that it doesn't make elsewhere
    # (on xenial ppc64 or on other trusty arches)
    __test__ = True


class XenialTestSimple(relbase.xenial, TestSimple):
    __test__ = True
