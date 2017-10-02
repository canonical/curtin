from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import textwrap


class TestInstallUnmount(VMBaseClass):
    """ Test a curtin install which disabled unmonting """
    conf_file = "examples/tests/install_disable_unmount.yaml"""
    extra_nics = []
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    disk_to_check = [('main_disk_with_in---valid--dname', 1),
                     ('main_disk_with_in---valid--dname', 2)]
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

    def test_proc_mounts_before_unmount(self):
        self.output_file_exists([
            'root/curtin_postinst_mounts.out',
            'root/target_mount_point.sh'])


class XenialTestInstallUnmount(relbase.xenial, TestInstallUnmount):
    __test__ = True


class ArtfulTestInstallUnmount(relbase.artful, TestInstallUnmount):
    __test__ = True
