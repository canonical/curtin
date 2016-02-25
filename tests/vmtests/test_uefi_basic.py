from . import (VMBaseClass)

from .releases import base_vm_classes as relbase

import os
import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    conf_file = "examples/tests/uefi_basic.yaml"
    install_timeout = 600
    boot_timeout = 120
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
        ls /sys/firmware/efi/ > ls_sys_firmware_efi
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
