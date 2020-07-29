# This file is part of curtin. See LICENSE file for copyright and license info.

from .test_uefi_basic import TestBasicAbs
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as cent_rbase


class TestUefiReuseEspAbs(TestBasicAbs):
    conf_file = "examples/tests/uefi_reuse_esp.yaml"

    def test_efiboot_menu_has_one_distro_entry(self):
        efiboot_mgr_content = self.load_collect_file("efibootmgr.out")
        distro_lines = [line for line in efiboot_mgr_content.splitlines()
                        if self.target_distro in line]
        print(distro_lines)
        self.assertEqual(1, len(distro_lines))


@TestUefiReuseEspAbs.skip_by_date("1881030", fixby="2020-07-15")
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


class GroovyTestUefiReuseEsp(relbase.groovy, TestUefiReuseEspAbs):
    __test__ = True

    def test_efiboot_menu_has_one_distro_entry(self):
        return super().test_efiboot_menu_has_one_distro_entry()


# vi: ts=4 expandtab syntax=python
