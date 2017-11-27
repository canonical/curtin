from . import (VMBaseClass)

from .releases import base_vm_classes as relbase

import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    arch_skip = ["s390x"]
    conf_file = "examples/tests/uefi_basic.yaml"
    extra_disks = ['4G']
    uefi = True
    disk_to_check = [('main_disk', 1), ('main_disk', 2), ('main_disk', 3)]
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
        sys_efi_possible = [
            'config_table',
            'efivars',
            'fw_platform_size',
            'fw_vendor',
            'runtime',
            'runtime-map',
            'systab',
            'vars',
        ]
        efi_lines = self.load_collect_file(
            "ls_sys_firmware_efi").strip().split('\n')

        # sys/firmware/efi contents differ based on kernel and configuration
        for efi_line in efi_lines:
            self.assertIn(efi_line, sys_efi_possible)

    def test_disk_block_sizes(self):
        """ Test disk logical and physical block size are match
            the class block size.
        """
        for bs in ['lbs', 'pbs']:
            size = int(self.load_collect_file('vda_' + bs))
            self.assertEqual(self.disk_block_size, size)

    def test_disk_block_size_with_blockdev(self):
        """ validate maas setting
        --getsz                   get size in 512-byte sectors
        --getss                   get logical block (sector) size
        --getpbsz                 get physical block (sector) size
        --getbsz                  get blocksize
        """
        for syscall in ['getss', 'getpbsz']:
            size = int(self.load_collect_file('vda_blockdev_' + syscall))
            self.assertEqual(self.disk_block_size, size)


class TrustyUefiTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEXUefiTestBasic(relbase.trusty_hwe_x, TrustyUefiTestBasic):
    __test__ = True


class XenialUefiTestBasic(relbase.xenial, TestBasicAbs):
    __test__ = True


class ZestyUefiTestBasic(relbase.zesty, TestBasicAbs):
    __test__ = True


class ArtfulUefiTestBasic(relbase.artful, TestBasicAbs):
    __test__ = True


class TrustyUefiTestBasic4k(TrustyUefiTestBasic):
    disk_block_size = 4096


class TrustyHWEXUefiTestBasic4k(relbase.trusty_hwe_x, TrustyUefiTestBasic4k):
    __test__ = True


class XenialUefiTestBasic4k(XenialUefiTestBasic):
    disk_block_size = 4096


class ZestyUefiTestBasic4k(ZestyUefiTestBasic):
    disk_block_size = 4096


class ArtfulUefiTestBasic4k(ArtfulUefiTestBasic):
    disk_block_size = 4096
