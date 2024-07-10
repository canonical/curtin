# This file is part of curtin. See LICENSE file for copyright and license info.

from .test_uefi_basic import TestBasicAbs
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as cent_rbase
from curtin.commands.curthooks import uefi_find_duplicate_entries
from curtin import util


class TestUefiReuseEspAbs(TestBasicAbs):
    conf_file = "examples/tests/uefi_reuse_esp.yaml"

    def test_efiboot_menu_has_one_distro_entry(self):
        efi_output = util.parse_efibootmgr(
            self.load_collect_file("efibootmgr.out"))
        duplicates = uefi_find_duplicate_entries(
            grubcfg=None, target=None, efi_output=efi_output)
        print(duplicates)
        self.assertEqual(0, len(duplicates))


class Cent70TestUefiReuseEsp(cent_rbase.centos70_bionic, TestUefiReuseEspAbs):
    __test__ = True


# grub-efi-amd64 + shim-signed isn't happy on XenialGA ephemeral env
class XenialGATestUefiReuseEsp(relbase.xenial_ga, TestUefiReuseEspAbs):
    __test__ = False


class BionicTestUefiReuseEsp(relbase.bionic, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


class FocalTestUefiReuseEsp(relbase.focal, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


class HirsuteTestUefiReuseEsp(relbase.hirsute, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


class ImpishTestUefiReuseEsp(relbase.impish, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


class JammyTestUefiReuseEsp(relbase.jammy, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


# vi: ts=4 expandtab syntax=python
