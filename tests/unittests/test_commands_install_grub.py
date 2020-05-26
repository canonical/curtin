# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin import distro
from curtin import util
from curtin import paths
from curtin.commands import install_grub
from .helpers import CiTestCase

import mock
import os


class TestGetGrubPackageName(CiTestCase):

    def test_ppc64_arch(self):
        target_arch = 'ppc64le'
        uefi = False
        rhel_ver = None
        self.assertEqual(
            ('grub-ieee1275', 'powerpc-ieee1275'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_uefi_debian_amd64(self):
        target_arch = 'amd64'
        uefi = True
        rhel_ver = None
        self.assertEqual(
            ('grub-efi-amd64', 'x86_64-efi'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_uefi_rhel7_amd64(self):
        target_arch = 'x86_64'
        uefi = True
        rhel_ver = '7'
        self.assertEqual(
            ('grub2-efi-x64', 'x86_64-efi'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_uefi_rhel8_amd64(self):
        target_arch = 'x86_64'
        uefi = True
        rhel_ver = '8'
        self.assertEqual(
            ('grub2-efi-x64', 'x86_64-efi'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_uefi_debian_arm64(self):
        target_arch = 'arm64'
        uefi = True
        rhel_ver = None
        self.assertEqual(
            ('grub-efi-arm64', 'arm64-efi'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_uefi_debian_i386(self):
        target_arch = 'i386'
        uefi = True
        rhel_ver = None
        self.assertEqual(
            ('grub-efi-ia32', 'i386-efi'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_debian_amd64(self):
        target_arch = 'amd64'
        uefi = False
        rhel_ver = None
        self.assertEqual(
            ('grub-pc', 'i386-pc'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_rhel6_amd64(self):
        target_arch = 'x86_64'
        uefi = False
        rhel_ver = '6'
        self.assertEqual(
            ('grub', 'i386-pc'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_rhel7_amd64(self):
        target_arch = 'x86_64'
        uefi = False
        rhel_ver = '7'
        self.assertEqual(
            ('grub2-pc', 'i386-pc'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_rhel8_amd64(self):
        target_arch = 'x86_64'
        uefi = False
        rhel_ver = '8'
        self.assertEqual(
            ('grub2-pc', 'i386-pc'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_debian_i386(self):
        target_arch = 'i386'
        uefi = False
        rhel_ver = None
        self.assertEqual(
            ('grub-pc', 'i386-pc'),
            install_grub.get_grub_package_name(target_arch, uefi, rhel_ver))

    def test_invalid_rhel_version(self):
        with self.assertRaises(ValueError):
            install_grub.get_grub_package_name('x86_64', uefi=False,
                                               rhel_ver='5')

    def test_invalid_arch(self):
        with self.assertRaises(ValueError):
            install_grub.get_grub_package_name(self.random_string(),
                                               uefi=False, rhel_ver=None)

    def test_invalid_arch_uefi(self):
        with self.assertRaises(ValueError):
            install_grub.get_grub_package_name(self.random_string(),
                                               uefi=True, rhel_ver=None)


class TestGetGrubConfigFile(CiTestCase):

    @mock.patch('curtin.commands.install_grub.distro.os_release')
    def test_grub_config_redhat(self, mock_os_release):
        mock_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            '/etc/default/grub',
            install_grub.get_grub_config_file(distroinfo.family))

    @mock.patch('curtin.commands.install_grub.distro.os_release')
    def test_grub_config_debian(self, mock_os_release):
        mock_os_release.return_value = {'ID': 'ubuntu'}
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            '/etc/default/grub.d/50-curtin-settings.cfg',
            install_grub.get_grub_config_file(distroinfo.family))


class TestPrepareGrubDir(CiTestCase):

    def setUp(self):
        super(TestPrepareGrubDir, self).setUp()
        self.target = self.tmp_dir()
        self.add_patch('curtin.commands.install_grub.util.ensure_dir',
                       'm_ensure_dir')
        self.add_patch('curtin.commands.install_grub.shutil.move', 'm_move')
        self.add_patch('curtin.commands.install_grub.os.path.exists', 'm_path')

    def test_prepare_grub_dir(self):
        grub_conf = 'etc/default/grub.d/%s' % self.random_string()
        target_grub_conf = os.path.join(self.target, grub_conf)
        ci_conf = os.path.join(
            os.path.dirname(target_grub_conf), '50-cloudimg-settings.cfg')
        self.m_path.return_value = True
        install_grub.prepare_grub_dir(self.target, grub_conf)
        self.m_ensure_dir.assert_called_with(os.path.dirname(target_grub_conf))
        self.m_move.assert_called_with(ci_conf, ci_conf + '.disabled')

    def test_prepare_grub_dir_no_ci_cfg(self):
        grub_conf = 'etc/default/grub.d/%s' % self.random_string()
        target_grub_conf = os.path.join(self.target, grub_conf)
        self.m_path.return_value = False
        install_grub.prepare_grub_dir(self.target, grub_conf)
        self.m_ensure_dir.assert_called_with(
            os.path.dirname(target_grub_conf))
        self.assertEqual(0, self.m_move.call_count)


class TestGetCarryoverParams(CiTestCase):

    def setUp(self):
        super(TestGetCarryoverParams, self).setUp()
        self.add_patch('curtin.commands.install_grub.util.load_file',
                       'm_load_file')
        self.add_patch('curtin.commands.install_grub.distro.os_release',
                       'm_os_release')
        self.m_os_release.return_value = {'ID': 'ubuntu'}

    def test_no_carry_params(self):
        distroinfo = install_grub.distro.get_distroinfo()
        cmdline = "root=ZFS=rpool/ROOT/ubuntu_bo2om9 ro quiet splash"
        self.m_load_file.return_value = cmdline
        self.assertEqual([], install_grub.get_carryover_params(distroinfo))

    def test_legacy_separator(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '--'
        expected_carry_params = ['foo=bar', 'debug=1']
        cmdline = "root=/dev/xvda1 ro quiet splash %s %s" % (
            sep, " ".join(expected_carry_params))
        self.m_load_file.return_value = cmdline
        self.assertEqual(expected_carry_params,
                         install_grub.get_carryover_params(distroinfo))

    def test_preferred_separator(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '---'
        expected_carry_params = ['foo=bar', 'debug=1']
        cmdline = "root=/dev/xvda1 ro quiet splash %s %s" % (
            sep, " ".join(expected_carry_params))
        self.m_load_file.return_value = cmdline
        self.assertEqual(expected_carry_params,
                         install_grub.get_carryover_params(distroinfo))

    def test_multiple_preferred_separator(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '---'
        expected_carry_params = ['extra', 'additional']
        cmdline = "lead=args %s extra %s additional" % (sep, sep)
        self.m_load_file.return_value = cmdline
        self.assertEqual(expected_carry_params,
                         install_grub.get_carryover_params(distroinfo))

    def test_drop_bootif_initrd_boot_image_from_extra(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '---'
        expected_carry_params = ['foo=bar', 'debug=1']
        filtered = ["BOOTIF=eth0", "initrd=initrd-2.3", "BOOT_IMAGE=/xv1"]
        cmdline = "root=/dev/xvda1 ro quiet splash %s %s" % (
            sep, " ".join(filtered + expected_carry_params))
        self.m_load_file.return_value = cmdline
        self.assertEqual(expected_carry_params,
                         install_grub.get_carryover_params(distroinfo))

    def test_keep_console_always(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '---'
        console = "console=ttyS1,115200"
        cmdline = "root=/dev/xvda1 ro quiet splash %s %s" % (console, sep)
        self.m_load_file.return_value = cmdline
        self.assertEqual([console],
                         install_grub.get_carryover_params(distroinfo))

    def test_keep_console_only_once(self):
        distroinfo = install_grub.distro.get_distroinfo()
        sep = '---'
        console = "console=ttyS1,115200"
        cmdline = "root=/dev/xvda1 ro quiet splash %s %s %s" % (
            console, sep, console)
        self.m_load_file.return_value = cmdline
        self.assertEqual([console],
                         install_grub.get_carryover_params(distroinfo))

    def test_always_set_rh_params(self):
        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        cmdline = "root=ZFS=rpool/ROOT/ubuntu_bo2om9 ro quiet splash"
        self.m_load_file.return_value = cmdline
        self.assertEqual(['rd.auto=1'],
                         install_grub.get_carryover_params(distroinfo))


class TestReplaceGrubCmdlineLinuxDefault(CiTestCase):

    def setUp(self):
        super(TestReplaceGrubCmdlineLinuxDefault, self).setUp()
        self.target = self.tmp_dir()
        self.grubconf = "/etc/default/grub"
        self.target_grubconf = paths.target_path(self.target, self.grubconf)
        util.ensure_dir(os.path.dirname(self.target_grubconf))

    @mock.patch('curtin.commands.install_grub.util.write_file')
    @mock.patch('curtin.commands.install_grub.util.load_file')
    def test_append_line_if_not_found(self, m_load_file, m_write_file):
        existing = [
            "# If you change this file, run 'update-grub' after to update",
            "# /boot/grub/grub.cfg",
        ]
        m_load_file.return_value = "\n".join(existing)
        new_args = ["foo=bar", "wark=1"]
        newline = 'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(new_args)
        expected = newline + "\n"

        install_grub.replace_grub_cmdline_linux_default(
            self.target, new_args)

        m_write_file.assert_called_with(
            self.target_grubconf, expected, omode="a+")

    def test_append_line_if_not_found_verify_content(self):
        existing = [
            "# If you change this file, run 'update-grub' after to update",
            "# /boot/grub/grub.cfg",
        ]
        with open(self.target_grubconf, "w") as fh:
            fh.write("\n".join(existing))

        new_args = ["foo=bar", "wark=1"]
        newline = 'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(new_args)
        expected = "\n".join(existing) + newline + "\n"

        install_grub.replace_grub_cmdline_linux_default(
            self.target, new_args)

        with open(self.target_grubconf) as fh:
            found = fh.read()
        self.assertEqual(expected, found)

    @mock.patch('curtin.commands.install_grub.os.path.exists')
    @mock.patch('curtin.commands.install_grub.util.write_file')
    @mock.patch('curtin.commands.install_grub.util.load_file')
    def test_replace_line_when_found(self, m_load_file, m_write_file,
                                     m_exists):
        existing = [
            "# Line1",
            "# Line2",
            'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"',
            "# Line4",
            "# Line5",
        ]
        m_exists.return_value = True
        m_load_file.return_value = "\n".join(existing)
        new_args = ["foo=bar", "wark=1"]
        newline = 'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(new_args)
        expected = ("\n".join(existing[0:2]) + "\n" +
                    newline + "\n" +
                    "\n".join(existing[3:]))

        install_grub.replace_grub_cmdline_linux_default(
            self.target, new_args)

        m_write_file.assert_called_with(
            self.target_grubconf, expected, omode="w+")

    def test_replace_line_when_found_verify_content(self):
        existing = [
            "# Line1",
            "# Line2",
            'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"',
            "# Line4",
            "# Line5",
        ]
        with open(self.target_grubconf, "w") as fh:
            fh.write("\n".join(existing))

        new_args = ["foo=bar", "wark=1"]
        newline = 'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(new_args)
        expected = ("\n".join(existing[0:2]) + "\n" +
                    newline + "\n" +
                    "\n".join(existing[3:]))

        install_grub.replace_grub_cmdline_linux_default(
            self.target, new_args)

        with open(self.target_grubconf) as fh:
            found = fh.read()
            print(found)
        self.assertEqual(expected, found)


class TestWriteGrubConfig(CiTestCase):

    def setUp(self):
        super(TestWriteGrubConfig, self).setUp()
        self.target = self.tmp_dir()
        self.grubdefault = "/etc/default/grub"
        self.grubconf = "/etc/default/grub.d/50-curtin.cfg"
        self.target_grubdefault = paths.target_path(self.target,
                                                    self.grubdefault)
        self.target_grubconf = paths.target_path(self.target, self.grubconf)

    def _verify_expected(self, expected_default, expected_curtin):

        for expected, conffile in zip([expected_default, expected_curtin],
                                      [self.target_grubdefault,
                                       self.target_grubconf]):
            if expected:
                with open(conffile) as fh:
                    found = fh.read()
                self.assertEqual(expected, found)

    def test_write_grub_config_defaults(self):
        grubcfg = {}
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([
             'GRUB_CMDLINE_LINUX_DEFAULT="foo=bar wark=1"', ''])
        expected_curtin = "\n".join([
             ("# Curtin disable grub os prober that might find "
              "other OS installs."),
             'GRUB_DISABLE_OS_PROBER="true"',
             '# Curtin configured GRUB_TERMINAL value',
             'GRUB_TERMINAL="console"'])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_no_replace(self):
        grubcfg = {'replace_linux_default': False}
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([])
        expected_curtin = "\n".join([
             ("# Curtin disable grub os prober that might find "
              "other OS installs."),
             'GRUB_DISABLE_OS_PROBER="true"',
             '# Curtin configured GRUB_TERMINAL value',
             'GRUB_TERMINAL="console"'])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_disable_probe(self):
        grubcfg = {'probe_additional_os': False}  # DISABLE_OS_PROBER=1
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([
             'GRUB_CMDLINE_LINUX_DEFAULT="foo=bar wark=1"', ''])
        expected_curtin = "\n".join([
             ("# Curtin disable grub os prober that might find "
              "other OS installs."),
             'GRUB_DISABLE_OS_PROBER="true"',
             '# Curtin configured GRUB_TERMINAL value',
             'GRUB_TERMINAL="console"'])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_enable_probe(self):
        grubcfg = {'probe_additional_os': True}  # DISABLE_OS_PROBER=0, default
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([
             'GRUB_CMDLINE_LINUX_DEFAULT="foo=bar wark=1"', ''])
        expected_curtin = "\n".join([
             '# Curtin configured GRUB_TERMINAL value',
             'GRUB_TERMINAL="console"'])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_no_grub_settings_file(self):
        grubcfg = {
            'probe_additional_os': True,
            'terminal': 'unmodified',
        }
        new_params = []
        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)
        self.assertTrue(os.path.exists(self.target_grubdefault))
        self.assertFalse(os.path.exists(self.target_grubconf))

    def test_write_grub_config_specify_terminal(self):
        grubcfg = {'terminal': 'serial'}
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([
             'GRUB_CMDLINE_LINUX_DEFAULT="foo=bar wark=1"', ''])
        expected_curtin = "\n".join([
             ("# Curtin disable grub os prober that might find "
              "other OS installs."),
             'GRUB_DISABLE_OS_PROBER="true"',
             '# Curtin configured GRUB_TERMINAL value',
             'GRUB_TERMINAL="serial"'])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_terminal_unmodified(self):
        grubcfg = {'terminal': 'unmodified'}
        new_params = ['foo=bar', 'wark=1']
        expected_default = "\n".join([
             'GRUB_CMDLINE_LINUX_DEFAULT="foo=bar wark=1"', ''])
        expected_curtin = "\n".join([
             ("# Curtin disable grub os prober that might find "
              "other OS installs."),
             'GRUB_DISABLE_OS_PROBER="true"', ''])

        install_grub.write_grub_config(
            self.target, grubcfg, self.grubconf, new_params)

        self._verify_expected(expected_default, expected_curtin)

    def test_write_grub_config_invalid_terminal(self):
        grubcfg = {'terminal': ['color-tv']}
        new_params = ['foo=bar', 'wark=1']
        with self.assertRaises(ValueError):
            install_grub.write_grub_config(
                self.target, grubcfg, self.grubconf, new_params)


class TestFindEfiLoader(CiTestCase):

    def setUp(self):
        super(TestFindEfiLoader, self).setUp()
        self.target = self.tmp_dir()
        self.efi_path = 'boot/efi/EFI'
        self.target_efi_path = os.path.join(self.target, self.efi_path)
        self.bootid = self.random_string()

    def _possible_loaders(self):
        return [
            os.path.join(self.efi_path, self.bootid, 'shimx64.efi'),
            os.path.join(self.efi_path, 'BOOT', 'BOOTX64.EFI'),
            os.path.join(self.efi_path, self.bootid, 'grubx64.efi'),
        ]

    def test_return_none_with_no_loaders(self):
        self.assertIsNone(
            install_grub.find_efi_loader(self.target, self.bootid))

    def test_prefer_shim_loader(self):
        # touch loaders in target filesystem
        loaders = self._possible_loaders()
        for loader in loaders:
            tloader = os.path.join(self.target, loader)
            util.ensure_dir(os.path.dirname(tloader))
            with open(tloader, 'w+') as fh:
                fh.write('\n')

        found = install_grub.find_efi_loader(self.target, self.bootid)
        self.assertTrue(found.endswith(
            os.path.join(self.efi_path, self.bootid, 'shimx64.efi')))

    def test_prefer_existing_bootx_loader_with_no_shim(self):
        # touch all loaders in target filesystem
        loaders = self._possible_loaders()[1:]
        for loader in loaders:
            tloader = os.path.join(self.target, loader)
            util.ensure_dir(os.path.dirname(tloader))
            with open(tloader, 'w+') as fh:
                fh.write('\n')

        found = install_grub.find_efi_loader(self.target, self.bootid)
        self.assertTrue(found.endswith(
            os.path.join(self.efi_path, 'BOOT', 'BOOTX64.EFI')))

    def test_prefer_existing_grub_loader_with_no_other_loader(self):
        # touch all loaders in target filesystem
        loaders = self._possible_loaders()[2:]
        for loader in loaders:
            tloader = os.path.join(self.target, loader)
            util.ensure_dir(os.path.dirname(tloader))
            with open(tloader, 'w+') as fh:
                fh.write('\n')

        found = install_grub.find_efi_loader(self.target, self.bootid)
        print(found)
        self.assertTrue(found.endswith(
            os.path.join(self.efi_path, self.bootid, 'grubx64.efi')))


class TestGetGrubInstallCommand(CiTestCase):

    def setUp(self):
        super(TestGetGrubInstallCommand, self).setUp()
        self.add_patch('curtin.commands.install_grub.distro.os_release',
                       'm_os_release')
        self.add_patch('curtin.commands.install_grub.os.path.exists',
                       'm_exists')
        self.m_os_release.return_value = {'ID': 'ubuntu'}
        self.m_exists.return_value = False
        self.target = self.tmp_dir()

    def test_grub_install_command_ubuntu_no_uefi(self):
        uefi = False
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            'grub-install',
            install_grub.get_grub_install_command(
                uefi, distroinfo, self.target))

    def test_grub_install_command_ubuntu_with_uefi(self):
        self.m_exists.return_value = True
        uefi = True
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            install_grub.GRUB_MULTI_INSTALL,
            install_grub.get_grub_install_command(
                uefi, distroinfo, self.target))

    def test_grub_install_command_ubuntu_with_uefi_no_multi(self):
        uefi = True
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            'grub-install',
            install_grub.get_grub_install_command(
                uefi, distroinfo, self.target))

    def test_grub_install_command_redhat_no_uefi(self):
        uefi = False
        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        self.assertEqual(
            'grub2-install',
            install_grub.get_grub_install_command(
                uefi, distroinfo, self.target))


class TestGetEfiDiskPart(CiTestCase):

    def setUp(self):
        super(TestGetEfiDiskPart, self).setUp()
        self.add_patch(
            'curtin.commands.install_grub.block.get_blockdev_for_partition',
            'm_blkpart')

    def test_returns_first_result_with_partition(self):
        self.m_blkpart.side_effect = iter([
            ('/dev/disk-a', None),
            ('/dev/disk-b', '1'),
            ('/dev/disk-c', None),
        ])
        devices = ['/dev/disk-a', '/dev/disk-b', '/dev/disc-c']
        self.assertEqual(('/dev/disk-b', '1'),
                         install_grub.get_efi_disk_part(devices))

    def test_returns_none_tuple_if_no_partitions(self):
        self.m_blkpart.side_effect = iter([
            ('/dev/disk-a', None),
            ('/dev/disk-b', None),
            ('/dev/disk-c', None),
        ])
        devices = ['/dev/disk-a', '/dev/disk-b', '/dev/disc-c']
        self.assertEqual((None, None),
                         install_grub.get_efi_disk_part(devices))


class TestGenUefiInstallCommands(CiTestCase):

    def setUp(self):
        super(TestGenUefiInstallCommands, self).setUp()
        self.add_patch(
            'curtin.commands.install_grub.get_efi_disk_part',
            'm_get_disk_part')
        self.add_patch('curtin.commands.install_grub.distro.os_release',
                       'm_os_release')
        self.m_os_release.return_value = {'ID': 'ubuntu'}
        self.target = self.tmp_dir()

    def test_unsupported_distro_family_raises_valueerror(self):
        self.m_os_release.return_value = {'ID': 'arch'}
        distroinfo = install_grub.distro.get_distroinfo()
        grub_name = 'grub-efi-amd64'
        grub_target = 'x86_64-efi'
        grub_cmd = 'grub-install'
        update_nvram = True
        devices = ['/dev/disk-a-part1']
        disk = '/dev/disk-a'
        part = '1'
        self.m_get_disk_part.return_value = (disk, part)

        with self.assertRaises(ValueError):
            install_grub.gen_uefi_install_commands(
                grub_name, grub_target, grub_cmd, update_nvram, distroinfo,
                devices, self.target)

    def test_ubuntu_install(self):
        distroinfo = install_grub.distro.get_distroinfo()
        grub_name = 'grub-efi-amd64'
        grub_target = 'x86_64-efi'
        grub_cmd = 'grub-install'
        update_nvram = True
        devices = ['/dev/disk-a-part1']
        disk = '/dev/disk-a'
        part = '1'
        self.m_get_disk_part.return_value = (disk, part)

        expected_install = [
            ['efibootmgr', '-v'],
            ['dpkg-reconfigure', grub_name],
            ['update-grub'],
            [grub_cmd, '--target=%s' % grub_target,
             '--efi-directory=/boot/efi',
             '--bootloader-id=%s' % distroinfo.variant, '--recheck'],
        ]
        expected_post = [['efibootmgr', '-v']]
        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_uefi_install_commands(
                grub_name, grub_target, grub_cmd, update_nvram,
                distroinfo, devices, self.target))

    def test_ubuntu_install_multiple_esp(self):
        distroinfo = install_grub.distro.get_distroinfo()
        grub_name = 'grub-efi-amd64'
        grub_cmd = install_grub.GRUB_MULTI_INSTALL
        grub_target = 'x86_64-efi'
        update_nvram = True
        devices = ['/dev/disk-a-part1']
        disk = '/dev/disk-a'
        part = '1'
        self.m_get_disk_part.return_value = (disk, part)

        expected_install = [
            ['efibootmgr', '-v'],
            ['dpkg-reconfigure', grub_name],
            ['update-grub'],
            [install_grub.GRUB_MULTI_INSTALL],
        ]
        expected_post = [['efibootmgr', '-v']]
        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_uefi_install_commands(
                grub_name, grub_target, grub_cmd, update_nvram, distroinfo,
                devices, self.target))

    def test_redhat_install(self):
        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        grub_name = 'grub2-efi-x64'
        grub_target = 'x86_64-efi'
        grub_cmd = 'grub2-install'
        update_nvram = True
        devices = ['/dev/disk-a-part1']
        disk = '/dev/disk-a'
        part = '1'
        self.m_get_disk_part.return_value = (disk, part)

        expected_install = [
            ['efibootmgr', '-v'],
            [grub_cmd, '--target=%s' % grub_target,
             '--efi-directory=/boot/efi',
             '--bootloader-id=%s' % distroinfo.variant, '--recheck'],
        ]
        expected_post = [
            ['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'],
            ['efibootmgr', '-v']
        ]
        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_uefi_install_commands(
                grub_name, grub_target, grub_cmd, update_nvram, distroinfo,
                devices, self.target))

    def test_redhat_install_existing(self):
        # simulate existing bootloaders already installed in target system
        # by touching the files grub would have installed, including shim
        def _enable_loaders(bootid):
            efi_path = 'boot/efi/EFI'
            target_efi_path = os.path.join(self.target, efi_path)
            loaders = [
                os.path.join(target_efi_path, bootid, 'shimx64.efi'),
                os.path.join(target_efi_path, 'BOOT', 'BOOTX64.EFI'),
                os.path.join(target_efi_path, bootid, 'grubx64.efi'),
            ]
            for loader in loaders:
                util.ensure_dir(os.path.dirname(loader))
                with open(loader, 'w+') as fh:
                    fh.write('\n')

        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        bootid = distroinfo.variant
        _enable_loaders(bootid)
        grub_name = 'grub2-efi-x64'
        grub_target = 'x86_64-efi'
        grub_cmd = 'grub2-install'
        update_nvram = True
        devices = ['/dev/disk-a-part1']
        disk = '/dev/disk-a'
        part = '1'
        self.m_get_disk_part.return_value = (disk, part)

        expected_loader = '/boot/efi/EFI/%s/shimx64.efi' % bootid
        expected_install = [
            ['efibootmgr', '-v'],
            ['efibootmgr', '--create', '--write-signature',
             '--label', bootid, '--disk', disk, '--part', part,
             '--loader', expected_loader],
        ]
        expected_post = [
            ['grub2-mkconfig', '-o', '/boot/efi/EFI/%s/grub.cfg' % bootid],
            ['efibootmgr', '-v']
        ]

        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_uefi_install_commands(
                grub_name, grub_target, grub_cmd, update_nvram, distroinfo,
                devices, self.target))


class TestGenInstallCommands(CiTestCase):

    def setUp(self):
        super(TestGenInstallCommands, self).setUp()
        self.add_patch('curtin.commands.install_grub.distro.os_release',
                       'm_os_release')
        self.m_os_release.return_value = {'ID': 'ubuntu'}

    def test_unsupported_install(self):
        self.m_os_release.return_value = {'ID': 'gentoo'}
        distroinfo = install_grub.distro.get_distroinfo()
        devices = ['/dev/disk-a-part1', '/dev/disk-b-part1']
        rhel_ver = None
        grub_name = 'grub-pc'
        grub_cmd = 'grub-install'
        with self.assertRaises(ValueError):
            install_grub.gen_install_commands(
                grub_name, grub_cmd, distroinfo, devices, rhel_ver)

    def test_ubuntu_install(self):
        distroinfo = install_grub.distro.get_distroinfo()
        devices = ['/dev/disk-a-part1', '/dev/disk-b-part1']
        rhel_ver = None
        grub_name = 'grub-pc'
        grub_cmd = 'grub-install'
        expected_install = [
            ['dpkg-reconfigure', grub_name],
            ['update-grub']
        ] + [[grub_cmd, dev] for dev in devices]
        expected_post = []
        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_install_commands(
                grub_name, grub_cmd, distroinfo, devices, rhel_ver))

    def test_redhat_6_install_unsupported(self):
        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        devices = ['/dev/disk-a-part1', '/dev/disk-b-part1']
        rhel_ver = '6'
        grub_name = 'grub-pc'
        grub_cmd = 'grub-install'
        with self.assertRaises(ValueError):
            install_grub.gen_install_commands(
                grub_name, grub_cmd, distroinfo, devices, rhel_ver)

    def test_redhatp_7_or_8_install(self):
        self.m_os_release.return_value = {'ID': 'redhat'}
        distroinfo = install_grub.distro.get_distroinfo()
        devices = ['/dev/disk-a-part1', '/dev/disk-b-part1']
        rhel_ver = '7'
        grub_name = 'grub-pc'
        grub_cmd = 'grub2-install'
        expected_install = [[grub_cmd, dev] for dev in devices]
        expected_post = [
            ['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg']
        ]
        self.assertEqual(
            (expected_install, expected_post),
            install_grub.gen_install_commands(
                grub_name, grub_cmd, distroinfo, devices, rhel_ver))


@mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
class TestInstallGrub(CiTestCase):

    def setUp(self):
        super(TestInstallGrub, self).setUp()
        base = 'curtin.commands.install_grub.'
        self.add_patch(base + 'distro.get_distroinfo',
                       'm_distro_get_distroinfo')
        self.add_patch(base + 'distro.get_architecture',
                       'm_distro_get_architecture')
        self.add_patch(base + 'distro.rpm_get_dist_id',
                       'm_distro_rpm_get_dist_id')
        self.add_patch(base + 'get_grub_package_name',
                       'm_get_grub_package_name')
        self.add_patch(base + 'platform.machine', 'm_platform_machine')
        self.add_patch(base + 'get_grub_config_file', 'm_get_grub_config_file')
        self.add_patch(base + 'get_carryover_params', 'm_get_carryover_params')
        self.add_patch(base + 'prepare_grub_dir', 'm_prepare_grub_dir')
        self.add_patch(base + 'write_grub_config', 'm_write_grub_config')
        self.add_patch(base + 'get_grub_install_command',
                       'm_get_grub_install_command')
        self.add_patch(base + 'gen_uefi_install_commands',
                       'm_gen_uefi_install_commands')
        self.add_patch(base + 'gen_install_commands', 'm_gen_install_commands')
        self.add_patch(base + 'util.subp', 'm_subp')
        self.add_patch(base + 'os.environ.copy', 'm_environ')

        self.distroinfo = distro.DistroInfo('ubuntu', 'debian')
        self.m_distro_get_distroinfo.return_value = self.distroinfo
        self.m_distro_rpm_get_dist_id.return_value = '7'
        self.m_distro_get_architecture.return_value = 'amd64'
        self.m_platform_machine.return_value = 'amd64'
        self.m_environ.return_value = {}
        self.env = {'DEBIAN_FRONTEND': 'noninteractive'}
        self.target = self.tmp_dir()

    def test_grub_install_raise_exception_on_no_devices(self):
        devices = []
        with self.assertRaises(ValueError):
            install_grub.install_grub(devices, self.target, False, {})

    def test_grub_install_raise_exception_on_no_target(self):
        devices = ['foobar']
        with self.assertRaises(ValueError):
            install_grub.install_grub(devices, None, False, {})

    def test_grub_install_raise_exception_on_s390x(self):
        self.m_distro_get_architecture.return_value = 's390x'
        self.m_platform_machine.return_value = 's390x'
        devices = ['foobar']
        with self.assertRaises(RuntimeError):
            install_grub.install_grub(devices, self.target, False, {})

    def test_grub_install_raise_exception_on_armv7(self):
        self.m_distro_get_architecture.return_value = 'armhf'
        self.m_platform_machine.return_value = 'armv7l'
        devices = ['foobar']
        with self.assertRaises(RuntimeError):
            install_grub.install_grub(devices, self.target, False, {})

    def test_grub_install_raise_exception_on_arm64_no_uefi(self):
        self.m_distro_get_architecture.return_value = 'arm64'
        self.m_platform_machine.return_value = 'aarch64'
        uefi = False
        devices = ['foobar']
        with self.assertRaises(RuntimeError):
            install_grub.install_grub(devices, self.target, uefi, {})

    def test_grub_install_ubuntu(self):
        devices = ['/dev/disk-a-part1']
        uefi = False
        grubcfg = {}
        grub_conf = self.tmp_path('grubconf')
        new_params = []
        self.m_get_grub_package_name.return_value = ('grub-pc', 'i386-pc')
        self.m_get_grub_config_file.return_value = grub_conf
        self.m_get_carryover_params.return_value = new_params
        self.m_get_grub_install_command.return_value = 'grub-install'
        self.m_gen_install_commands.return_value = (
            [['/bin/true']], [['/bin/false']])

        install_grub.install_grub(devices, self.target, uefi, grubcfg)

        self.m_distro_get_distroinfo.assert_called_with(target=self.target)
        self.m_distro_get_architecture.assert_called_with(target=self.target)
        self.assertEqual(0, self.m_distro_rpm_get_dist_id.call_count)
        self.m_get_grub_package_name.assert_called_with('amd64', uefi, None)
        self.m_get_grub_config_file.assert_called_with(self.target,
                                                       self.distroinfo.family)
        self.m_get_carryover_params.assert_called_with(self.distroinfo)
        self.m_prepare_grub_dir.assert_called_with(self.target, grub_conf)
        self.m_write_grub_config.assert_called_with(self.target, grubcfg,
                                                    grub_conf, new_params)
        self.m_get_grub_install_command.assert_called_with(
            uefi, self.distroinfo, self.target)
        self.m_gen_install_commands.assert_called_with(
            'grub-pc', 'grub-install', self.distroinfo, devices, None)

        self.m_subp.assert_has_calls([
            mock.call(['/bin/true'], env=self.env, capture=True,
                      target=self.target),
            mock.call(['/bin/false'], env=self.env, capture=True,
                      target=self.target),
        ])

    def test_uefi_grub_install_ubuntu(self):
        devices = ['/dev/disk-a-part1']
        uefi = True
        update_nvram = True
        grubcfg = {'update_nvram': update_nvram}
        grub_conf = self.tmp_path('grubconf')
        new_params = []
        grub_name = 'grub-efi-amd64'
        grub_target = 'x86_64-efi'
        grub_cmd = 'grub-install'
        self.m_get_grub_package_name.return_value = (grub_name, grub_target)
        self.m_get_grub_config_file.return_value = grub_conf
        self.m_get_carryover_params.return_value = new_params
        self.m_get_grub_install_command.return_value = grub_cmd
        self.m_gen_uefi_install_commands.return_value = (
            [['/bin/true']], [['/bin/false']])

        install_grub.install_grub(devices, self.target, uefi, grubcfg)

        self.m_distro_get_distroinfo.assert_called_with(target=self.target)
        self.m_distro_get_architecture.assert_called_with(target=self.target)
        self.assertEqual(0, self.m_distro_rpm_get_dist_id.call_count)
        self.m_get_grub_package_name.assert_called_with('amd64', uefi, None)
        self.m_get_grub_config_file.assert_called_with(self.target,
                                                       self.distroinfo.family)
        self.m_get_carryover_params.assert_called_with(self.distroinfo)
        self.m_prepare_grub_dir.assert_called_with(self.target, grub_conf)
        self.m_write_grub_config.assert_called_with(self.target, grubcfg,
                                                    grub_conf, new_params)
        self.m_get_grub_install_command.assert_called_with(
            uefi, self.distroinfo, self.target)
        self.m_gen_uefi_install_commands.assert_called_with(
            grub_name, grub_target, grub_cmd, update_nvram, self.distroinfo,
            devices, self.target)

        self.m_subp.assert_has_calls([
            mock.call(['/bin/true'], env=self.env, capture=True,
                      target=self.target),
            mock.call(['/bin/false'], env=self.env, capture=True,
                      target=self.target),
        ])

    def test_uefi_grub_install_ubuntu_multiple_esp(self):
        devices = ['/dev/disk-a-part1']
        uefi = True
        update_nvram = True
        grubcfg = {'update_nvram': update_nvram}
        grub_conf = self.tmp_path('grubconf')
        new_params = []
        grub_name = 'grub-efi-amd64'
        grub_target = 'x86_64-efi'
        grub_cmd = install_grub.GRUB_MULTI_INSTALL
        self.m_get_grub_package_name.return_value = (grub_name, grub_target)
        self.m_get_grub_config_file.return_value = grub_conf
        self.m_get_carryover_params.return_value = new_params
        self.m_get_grub_install_command.return_value = grub_cmd
        self.m_gen_uefi_install_commands.return_value = (
            [['/bin/true']], [['/bin/false']])

        install_grub.install_grub(devices, self.target, uefi, grubcfg)

        self.m_distro_get_distroinfo.assert_called_with(target=self.target)
        self.m_distro_get_architecture.assert_called_with(target=self.target)
        self.assertEqual(0, self.m_distro_rpm_get_dist_id.call_count)
        self.m_get_grub_package_name.assert_called_with('amd64', uefi, None)
        self.m_get_grub_config_file.assert_called_with(self.target,
                                                       self.distroinfo.family)
        self.m_get_carryover_params.assert_called_with(self.distroinfo)
        self.m_prepare_grub_dir.assert_called_with(self.target, grub_conf)
        self.m_write_grub_config.assert_called_with(self.target, grubcfg,
                                                    grub_conf, new_params)
        self.m_get_grub_install_command.assert_called_with(
            uefi, self.distroinfo, self.target)
        self.m_gen_uefi_install_commands.assert_called_with(
            grub_name, grub_target, grub_cmd, update_nvram, self.distroinfo,
            devices, self.target)

        self.m_subp.assert_has_calls([
            mock.call(['/bin/true'], env=self.env, capture=True,
                      target=self.target),
            mock.call(['/bin/false'], env=self.env, capture=True,
                      target=self.target),
        ])


# vi: ts=4 expandtab syntax=python
