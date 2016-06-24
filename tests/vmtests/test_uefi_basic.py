from . import (VMBaseClass)

from .releases import base_vm_classes as relbase

import os
import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    arch_skip = ["s390x"]
    conf_file = "examples/tests/uefi_basic.yaml"
    extra_disks = []
    uefi = True
    disk_to_check = [('main_disk', 1), ('main_disk', 2)]
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        ls /sys/firmware/efi/ > ls_sys_firmware_efi
        cat /sys/class/block/vda/queue/logical_block_size > vda_lbs
        cat /sys/class/block/vda/queue/physical_block_size > vda_pbs
        blockdev --getsz /dev/vda > vda_blockdev_getsz
        blockdev --getss /dev/vda > vda_blockdev_getss
        blockdev --getpbsz /dev/vda > vda_blockdev_getpbsz
        blockdev --getbsz /dev/vda > vda_blockdev_getbsz
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "fstab", "ls_dname", "ls_uuid", "ls_sys_firmware_efi",
             "proc_partitions"])

    def test_sys_firmware_efi(self):
        sys_efi_expected = [
            'config_table',
            'efivars',
            'fw_platform_size',
            'fw_vendor',
            'runtime',
            'runtime-map',
            'systab',
            'vars',
        ]
        sys_efi = self.td.collect + "ls_sys_firmware_efi"
        if (os.path.exists(sys_efi)):
            with open(sys_efi) as fp:
                efi_lines = fp.read().strip().split('\n')
                self.assertEqual(sorted(sys_efi_expected),
                                 sorted(efi_lines))

    def test_disk_block_sizes(self):
        """ Test disk logical and physical block size are match
            the class block size.
        """
        for bs in ['lbs', 'pbs']:
            with open(os.path.join(self.td.collect,
                      'vda_' + bs), 'r') as fp:
                size = int(fp.read())
                self.assertEqual(self.disk_block_size, size)

    def test_disk_block_size_with_blockdev(self):
        """ validate maas setting
        --getsz                   get size in 512-byte sectors
        --getss                   get logical block (sector) size
        --getpbsz                 get physical block (sector) size
        --getbsz                  get blocksize
        """
        for syscall in ['getss', 'getpbsz']:
            with open(os.path.join(self.td.collect,
                      'vda_blockdev_' + syscall), 'r') as fp:
                size = int(fp.read())
                self.assertEqual(self.disk_block_size, size)


class PreciseUefiTestBasic(relbase.precise, TestBasicAbs):
    __test__ = True

    def test_ptable(self):
        print("test_ptable does not work for Precise")

    def test_dname(self):
        print("test_dname does not work for Precise")


class TrustyUefiTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class WilyUefiTestBasic(relbase.wily, TestBasicAbs):
    __test__ = True


class XenialUefiTestBasic(relbase.xenial, TestBasicAbs):
    __test__ = True


class YakketyUefiTestBasic(relbase.yakkety, TestBasicAbs):
    __test__ = True


class PreciseUefiTestBasic4k(PreciseUefiTestBasic):
    disk_block_size = 4096


class TrustyUefiTestBasic4k(TrustyUefiTestBasic):
    disk_block_size = 4096


class WilyUefiTestBasic4k(WilyUefiTestBasic):
    disk_block_size = 4096


class XenialUefiTestBasic4k(XenialUefiTestBasic):
    disk_block_size = 4096


class YakketyUefiTestBasic4k(YakketyUefiTestBasic):
    disk_block_size = 4096
