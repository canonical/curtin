from . import VMBaseClass
from .releases import base_vm_classes as relbase

import os
import textwrap


class TestNvmeAbs(VMBaseClass):
    arch_skip = [
        "s390x",  # nvme is a pci device, no pci on s390x
    ]
    interactive = False
    conf_file = "examples/tests/nvme.yaml"
    extra_disks = []
    nvme_disks = ['4G', '4G']
    disk_to_check = [('main_disk', 1), ('main_disk', 2), ('main_disk', 15),
                     ('nvme_disk', 1), ('nvme_disk', 2), ('nvme_disk', 3),
                     ('second_nvme', 1)]
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/class/ > sys_class
        ls /sys/class/nvme/ > ls_nvme
        ls /dev/nvme* > ls_dev_nvme
        ls /dev/disk/by-dname/ > ls_dname
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        btrfs-show-super /dev/vdd > btrfs_show_super_vdd
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd

        v=""
        out=$(apt-config shell v Acquire::HTTP::Proxy)
        eval "$out"
        echo "$v" > apt-proxy
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["ls_nvme", "ls_dname", "ls_dev_nvme"])

    def test_nvme_device_names(self):
        ls_nvme = os.path.join(self.td.collect, 'ls_nvme')
        # trusty and vivid do not have sys/class/nvme but
        # nvme devices do work
        if os.path.getsize(ls_nvme) > 0:
            self.check_file_strippedline("ls_nvme", "nvme0")
            self.check_file_strippedline("ls_nvme", "nvme1")
        else:
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme0")
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme1")


class PreciseTestNvme(relbase.precise, TestNvmeAbs):
    __test__ = False
    # Precise kernel doesn't have NVME support, with TrustyHWE it would


class TrustyTestNvme(relbase.trusty, TestNvmeAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class WilyTestNvme(relbase.wily, TestNvmeAbs):
    # EOL - 2016-07-28
    __test__ = False


class XenialTestNvme(relbase.xenial, TestNvmeAbs):
    __test__ = True


class YakketyTestNvme(relbase.yakkety, TestNvmeAbs):
    __test__ = True
