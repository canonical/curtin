# This file is part of curtin. See LICENSE file for copyright and license info.

from . import (VMBaseClass)
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    test_type = 'storage'
    arch_skip = ["s390x"]
    conf_file = "examples/tests/uefi_basic.yaml"
    extra_disks = ['4G']
    uefi = True
    disk_to_check = [('main_disk', 1), ('main_disk', 2)]
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/firmware/efi/ | cat >ls_sys_firmware_efi
        cp /sys/class/block/vda/queue/logical_block_size vda_lbs
        cp /sys/class/block/vda/queue/physical_block_size vda_pbs
        blockdev --getsz /dev/vda | cat >vda_blockdev_getsz
        blockdev --getss /dev/vda | cat >vda_blockdev_getss
        blockdev --getpbsz /dev/vda | cat >vda_blockdev_getpbsz
        blockdev --getbsz /dev/vda | cat >vda_blockdev_getbsz

        exit 0
        """)]

    def test_sys_firmware_efi(self):
        self.output_files_exist(["ls_sys_firmware_efi"])
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
        blocksize_files = ['vda_' + bs for bs in ['lbs', 'pbs']]
        self.output_files_exist(blocksize_files)
        for bs_file in blocksize_files:
            size = int(self.load_collect_file(bs_file))
            self.assertEqual(self.disk_block_size, size)

    def test_disk_block_size_with_blockdev(self):
        """ validate maas setting
        --getsz                   get size in 512-byte sectors
        --getss                   get logical block (sector) size
        --getpbsz                 get physical block (sector) size
        --getbsz                  get blocksize
        """
        bdev_files = ['vda_blockdev_' + sc for sc in ['getss', 'getpbsz']]
        self.output_files_exist(bdev_files)
        for sc_file in bdev_files:
            size = int(self.load_collect_file(sc_file))
            self.assertEqual(self.disk_block_size, size)


class Centos70UefiTestBasic(centos_relbase.centos70_xenial, TestBasicAbs):
    __test__ = True


class PreciseUefiTestBasic(relbase.precise, TestBasicAbs):
    __test__ = False

    def test_ptable(self):
        print("test_ptable does not work for Precise")

    def test_dname(self):
        print("test_dname does not work for Precise")


class PreciseHWETUefiTestBasic(relbase.precise_hwe_t, PreciseUefiTestBasic):
    __test__ = False


class TrustyUefiTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True


class TrustyHWEXUefiTestBasic(relbase.trusty_hwe_x, TestBasicAbs):
    __test__ = True


class XenialGAUefiTestBasic(relbase.xenial_ga, TestBasicAbs):
    __test__ = True


class XenialHWEUefiTestBasic(relbase.xenial_hwe, TestBasicAbs):
    __test__ = True


class XenialEdgeUefiTestBasic(relbase.xenial_edge, TestBasicAbs):
    __test__ = True


class BionicUefiTestBasic(relbase.bionic, TestBasicAbs):
    __test__ = True


class CosmicUefiTestBasic(relbase.cosmic, TestBasicAbs):
    __test__ = True


class DiscoUefiTestBasic(relbase.disco, TestBasicAbs):
    __test__ = True


class Centos70UefiTestBasic4k(centos_relbase.centos70_xenial, TestBasicAbs):
    disk_block_size = 4096


class TrustyUefiTestBasic4k(relbase.trusty, TestBasicAbs):
    disk_block_size = 4096


class TrustyHWEXUefiTestBasic4k(relbase.trusty_hwe_x, TestBasicAbs):
    disk_block_size = 4096


class XenialGAUefiTestBasic4k(relbase.xenial_ga, TestBasicAbs):
    disk_block_size = 4096


class BionicUefiTestBasic4k(relbase.bionic, TestBasicAbs):
    disk_block_size = 4096


class CosmicUefiTestBasic4k(relbase.cosmic, TestBasicAbs):
    disk_block_size = 4096


class DiscoUefiTestBasic4k(relbase.disco, TestBasicAbs):
    disk_block_size = 4096

# vi: ts=4 expandtab syntax=python
