# This file is part of curtin. See LICENSE file for copyright and license info.

import os
from mock import call, patch, MagicMock
import textwrap

from curtin.commands import curthooks
from curtin import distro
from curtin import util
from curtin import config
from curtin.reporter import events
from .helpers import CiTestCase, dir2dict, populate_dir


class TestGetFlashKernelPkgs(CiTestCase):
    def setUp(self):
        super(TestGetFlashKernelPkgs, self).setUp()
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.add_patch('curtin.util.get_architecture', 'mock_get_architecture')
        self.add_patch('curtin.util.is_uefi_bootable', 'mock_is_uefi_bootable')

    def test__returns_none_when_uefi(self):
        self.assertIsNone(curthooks.get_flash_kernel_pkgs(uefi=True))
        self.assertFalse(self.mock_subp.called)

    def test__returns_none_when_not_arm(self):
        self.assertIsNone(curthooks.get_flash_kernel_pkgs('amd64', False))
        self.assertFalse(self.mock_subp.called)

    def test__returns_none_on_error(self):
        self.mock_subp.side_effect = util.ProcessExecutionError()
        self.assertIsNone(curthooks.get_flash_kernel_pkgs('arm64', False))
        self.mock_subp.assert_called_with(
            ['list-flash-kernel-packages'], capture=True)

    def test__returns_flash_kernel_pkgs(self):
        self.mock_subp.return_value = 'u-boot-tools', ''
        self.assertEquals(
            'u-boot-tools', curthooks.get_flash_kernel_pkgs('arm64', False))
        self.mock_subp.assert_called_with(
            ['list-flash-kernel-packages'], capture=True)

    def test__calls_get_arch_and_is_uefi_bootable_when_undef(self):
        curthooks.get_flash_kernel_pkgs()
        self.mock_get_architecture.assert_called_once_with()
        self.mock_is_uefi_bootable.assert_called_once_with()


class TestCurthooksInstallKernel(CiTestCase):
    def setUp(self):
        super(TestCurthooksInstallKernel, self).setUp()
        self.add_patch('curtin.distro.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.distro.install_packages', 'mock_instpkg')
        self.add_patch(
            'curtin.commands.curthooks.get_flash_kernel_pkgs',
            'mock_get_flash_kernel_pkgs')

        self.kernel_cfg = {'kernel': {'package': 'mock-linux-kernel',
                                      'fallback-package': 'mock-fallback',
                                      'mapping': {}}}
        # Tests don't actually install anything so we just need a name
        self.target = self.tmp_dir()

    def test__installs_flash_kernel_packages_when_needed(self):
        kernel_package = self.kernel_cfg.get('kernel', {}).get('package', {})
        self.mock_get_flash_kernel_pkgs.return_value = 'u-boot-tools'

        curthooks.install_kernel(self.kernel_cfg, self.target)

        inst_calls = [
            call(['u-boot-tools'], target=self.target),
            call([kernel_package], target=self.target)]

        self.mock_instpkg.assert_has_calls(inst_calls)

    def test__installs_kernel_package(self):
        kernel_package = self.kernel_cfg.get('kernel', {}).get('package', {})
        self.mock_get_flash_kernel_pkgs.return_value = None

        curthooks.install_kernel(self.kernel_cfg, self.target)

        self.mock_instpkg.assert_called_with(
            [kernel_package], target=self.target)


class TestUpdateInitramfs(CiTestCase):
    def setUp(self):
        super(TestUpdateInitramfs, self).setUp()
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.target = self.tmp_dir()

    def _mnt_call(self, point):
        target = os.path.join(self.target, point)
        return call(['mount', '--bind', '/%s' % point, target])

    def test_mounts_and_runs(self):
        curthooks.update_initramfs(self.target)

        print('subp calls: %s' % self.mock_subp.mock_calls)
        subp_calls = [
            self._mnt_call('dev'),
            self._mnt_call('proc'),
            self._mnt_call('sys'),
            call(['update-initramfs', '-u'], target=self.target),
            call(['udevadm', 'settle']),
        ]
        self.mock_subp.assert_has_calls(subp_calls)

    def test_mounts_and_runs_for_all_kernels(self):
        curthooks.update_initramfs(self.target, True)

        print('subp calls: %s' % self.mock_subp.mock_calls)
        subp_calls = [
            self._mnt_call('dev'),
            self._mnt_call('proc'),
            self._mnt_call('sys'),
            call(['update-initramfs', '-u', '-k', 'all'], target=self.target),
            call(['udevadm', 'settle']),
        ]
        self.mock_subp.assert_has_calls(subp_calls)


class TestSetupKernelImgConf(CiTestCase):

    def setUp(self):
        super(TestSetupKernelImgConf, self).setUp()
        self.add_patch('platform.machine', 'mock_machine')
        self.add_patch('curtin.util.get_architecture', 'mock_arch')
        self.add_patch('curtin.util.write_file', 'mock_write_file')
        self.target = 'not-a-real-target'

    def test_on_s390x(self):
        self.mock_machine.return_value = "s390x"
        self.mock_arch.return_value = "s390x"
        curthooks.setup_kernel_img_conf(self.target)
        self.mock_write_file.assert_called_with(
            os.path.sep.join([self.target, '/etc/kernel-img.conf']),
            content="""# Kernel image management overrides
# See kernel-img.conf(5) for details
do_symlinks = yes
do_bootloader = yes
do_initrd = yes
link_in_boot = yes
""")

    def test_on_i386(self):
        self.mock_machine.return_value = "i686"
        self.mock_arch.return_value = "i386"
        curthooks.setup_kernel_img_conf(self.target)
        self.mock_write_file.assert_called_with(
            os.path.sep.join([self.target, '/etc/kernel-img.conf']),
            content="""# Kernel image management overrides
# See kernel-img.conf(5) for details
do_symlinks = yes
do_bootloader = no
do_initrd = yes
link_in_boot = no
""")

    def test_on_amd64(self):
        self.mock_machine.return_value = "x86_64"
        self.mock_arch.return_value = "amd64"
        curthooks.setup_kernel_img_conf(self.target)
        self.mock_write_file.assert_called_with(
            os.path.sep.join([self.target, '/etc/kernel-img.conf']),
            content="""# Kernel image management overrides
# See kernel-img.conf(5) for details
do_symlinks = yes
do_bootloader = no
do_initrd = yes
link_in_boot = no
""")


class TestInstallMissingPkgs(CiTestCase):
    def setUp(self):
        super(TestInstallMissingPkgs, self).setUp()
        self.add_patch('platform.machine', 'mock_machine')
        self.add_patch('curtin.util.get_architecture', 'mock_arch')
        self.add_patch('curtin.distro.get_installed_packages',
                       'mock_get_installed_packages')
        self.add_patch('curtin.util.load_command_environment',
                       'mock_load_cmd_evn')
        self.add_patch('curtin.util.which', 'mock_which')
        self.add_patch('curtin.util.is_uefi_bootable', 'mock_uefi')
        self.add_patch('curtin.distro.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.distro.install_packages',
                       'mock_install_packages')
        self.add_patch('curtin.distro.get_osfamily', 'mock_osfamily')
        self.distro_family = distro.DISTROS.debian
        self.mock_osfamily.return_value = self.distro_family
        self.mock_uefi.return_value = False
        self.mock_haspkg.return_value = False

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_s390x(self, mock_events):

        self.mock_machine.return_value = "s390x"
        self.mock_which.return_value = False
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.mock_install_packages.assert_called_with(
            ['s390-tools'], target=target,
            osfamily=self.distro_family)

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_s390x_has_zipl(self, mock_events):

        self.mock_machine.return_value = "s390x"
        self.mock_which.return_value = True
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.assertEqual([], self.mock_install_packages.call_args_list)

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_x86_64_no_zipl(self, mock_events):

        self.mock_machine.return_value = "x86_64"
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.assertEqual([], self.mock_install_packages.call_args_list)

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_on_uefi_amd64_shim_signed(self, mock_events):
        arch = 'amd64'
        self.mock_arch.return_value = arch
        self.mock_machine.return_value = 'x86_64'
        expected_pkgs = ['grub-efi-%s' % arch,
                         'grub-efi-%s-signed' % arch,
                         'shim-signed']
        self.mock_machine.return_value = 'x86_64'
        self.mock_uefi.return_value = True
        self.mock_haspkg.return_value = True
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.mock_install_packages.assert_called_with(
                expected_pkgs, target=target, osfamily=self.distro_family)

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_on_uefi_i386_noshim_nosigned(self, mock_events):
        arch = 'i386'
        self.mock_arch.return_value = arch
        self.mock_machine.return_value = 'i386'
        expected_pkgs = ['grub-efi-%s' % arch]
        self.mock_machine.return_value = 'i686'
        self.mock_uefi.return_value = True
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.mock_install_packages.assert_called_with(
                expected_pkgs, target=target, osfamily=self.distro_family)

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_on_uefi_arm64_nosign_noshim(self, mock_events):
        arch = 'arm64'
        self.mock_arch.return_value = arch
        self.mock_machine.return_value = 'aarch64'
        expected_pkgs = ['grub-efi-%s' % arch]
        self.mock_uefi.return_value = True
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.mock_install_packages.assert_called_with(
                expected_pkgs, target=target, osfamily=self.distro_family)


class TestSetupZipl(CiTestCase):

    def setUp(self):
        super(TestSetupZipl, self).setUp()
        self.target = self.tmp_dir()

    @patch('curtin.block.get_devices_for_mp')
    @patch('platform.machine')
    def test_noop_non_s390x(self, m_machine, m_get_devices):
        m_machine.return_value = 'non-s390x'
        curthooks.setup_zipl(None, self.target)
        self.assertEqual(0, m_get_devices.call_count)

    @patch('curtin.block.get_devices_for_mp')
    @patch('platform.machine')
    def test_setup_zipl_writes_etc_zipl_conf(self, m_machine, m_get_devices):
        m_machine.return_value = 's390x'
        m_get_devices.return_value = ['/dev/mapper/ubuntu--vg-root']
        curthooks.setup_zipl(None, self.target)
        m_get_devices.assert_called_with(self.target)
        with open(os.path.join(self.target, 'etc', 'zipl.conf')) as stream:
            content = stream.read()
        self.assertIn(
            '# This has been modified by the MAAS curtin installer',
            content)


class TestSetupGrub(CiTestCase):

    def setUp(self):
        super(TestSetupGrub, self).setUp()
        self.target = self.tmp_dir()
        self.distro_family = distro.DISTROS.debian
        self.add_patch('curtin.distro.lsb_release', 'mock_lsb_release')
        self.mock_lsb_release.return_value = {
            'codename': 'xenial',
        }
        self.add_patch('curtin.util.is_uefi_bootable',
                       'mock_is_uefi_bootable')
        self.mock_is_uefi_bootable.return_value = False
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.subp_output = []
        self.mock_subp.side_effect = iter(self.subp_output)
        self.add_patch('curtin.commands.block_meta.devsync', 'mock_devsync')
        self.add_patch('curtin.util.get_architecture', 'mock_arch')
        self.mock_arch.return_value = 'amd64'
        self.add_patch(
            'curtin.util.ChrootableTarget', 'mock_chroot', autospec=False)
        self.mock_in_chroot = MagicMock()
        self.mock_in_chroot.__enter__.return_value = self.mock_in_chroot
        self.in_chroot_subp_output = []
        self.mock_in_chroot_subp = self.mock_in_chroot.subp
        self.mock_in_chroot_subp.side_effect = iter(self.in_chroot_subp_output)
        self.mock_chroot.return_value = self.mock_in_chroot

    def test_uses_old_grub_install_devices_in_cfg(self):
        cfg = {
            'grub_install_devices': ['/dev/vdb']
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--os-family=%s' % self.distro_family,
                self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_uses_install_devices_in_grubcfg(self):
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
            },
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--os-family=%s' % self.distro_family,
                self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_uses_grub_install_on_storage_config(self):
        cfg = {
            'storage': {
                'version': 1,
                'config': [
                    {
                        'id': 'vdb',
                        'type': 'disk',
                        'grub_device': True,
                        'path': '/dev/vdb',
                    }
                ]
            },
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--os-family=%s' % self.distro_family,
                self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_installs_to_none_if_install_devices_None(self):
        cfg = {
            'grub': {
                'install_devices': None,
            },
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--os-family=%s' % self.distro_family,
                self.target, 'none'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_updates_nvram_skips_remove_and_reorder(self):
        self.add_patch('curtin.distro.install_packages', 'mock_install')
        self.add_patch('curtin.distro.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.util.get_efibootmgr', 'mock_efibootmgr')
        self.mock_is_uefi_bootable.return_value = True
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
                'update_nvram': True,
                'remove_old_uefi_loaders': False,
                'reorder_uefi': False,
            },
        }
        self.subp_output.append(('', ''))
        self.mock_haspkg.return_value = False
        self.mock_efibootmgr.return_value = {
            'current': '0000',
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': (
                        'HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)'),
                }
            }
        }
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--uefi', '--update-nvram',
                '--os-family=%s' % self.distro_family,
                self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_updates_nvram_removes_old_loaders(self):
        self.add_patch('curtin.distro.install_packages', 'mock_install')
        self.add_patch('curtin.distro.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.util.get_efibootmgr', 'mock_efibootmgr')
        self.mock_is_uefi_bootable.return_value = True
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
                'update_nvram': True,
                'remove_old_uefi_loaders': True,
                'reorder_uefi': False,
            },
        }
        self.subp_output.append(('', ''))
        self.mock_efibootmgr.return_value = {
            'current': '0000',
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': (
                        'HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)'),
                },
                '0001': {
                    'name': 'centos',
                    'path': (
                        'HD(1,GPT)/File(\\EFI\\centos\\shimx64.efi)'),
                },
                '0002': {
                    'name': 'sles',
                    'path': (
                        'HD(1,GPT)/File(\\EFI\\sles\\shimx64.efi)'),
                },
            }
        }
        self.in_chroot_subp_output.append(('', ''))
        self.in_chroot_subp_output.append(('', ''))
        self.mock_haspkg.return_value = False
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            ['efibootmgr', '-B', '-b'],
            self.mock_in_chroot_subp.call_args_list[0][0][0][:3])
        self.assertEquals(
            ['efibootmgr', '-B', '-b'],
            self.mock_in_chroot_subp.call_args_list[1][0][0][:3])
        self.assertEquals(
            set(['0001', '0002']),
            set([
                self.mock_in_chroot_subp.call_args_list[0][0][0][3],
                self.mock_in_chroot_subp.call_args_list[1][0][0][3]]))

    def test_grub_install_uefi_updates_nvram_reorders_loaders(self):
        self.add_patch('curtin.distro.install_packages', 'mock_install')
        self.add_patch('curtin.distro.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.util.get_efibootmgr', 'mock_efibootmgr')
        self.mock_is_uefi_bootable.return_value = True
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
                'update_nvram': True,
                'remove_old_uefi_loaders': False,
                'reorder_uefi': True,
            },
        }
        self.subp_output.append(('', ''))
        self.mock_efibootmgr.return_value = {
            'current': '0001',
            'order': ['0000', '0001'],
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': (
                        'HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)'),
                },
                '0001': {
                    'name': 'UEFI:Network Device',
                    'path': 'BBS(131,,0x0)',
                },
            }
        }
        self.in_chroot_subp_output.append(('', ''))
        self.mock_haspkg.return_value = False
        curthooks.setup_grub(cfg, self.target, osfamily=self.distro_family)
        self.assertEquals(
            (['efibootmgr', '-o', '0001,0000'],),
            self.mock_in_chroot_subp.call_args_list[0][0])


class TestUbuntuCoreHooks(CiTestCase):
    def setUp(self):
        super(TestUbuntuCoreHooks, self).setUp()
        self.target = None

    def test_target_is_ubuntu_core(self):
        self.target = self.tmp_dir()
        ubuntu_core_path = os.path.join(self.target, 'system-data',
                                        'var/lib/snapd')
        util.ensure_dir(ubuntu_core_path)
        self.assertTrue(os.path.isdir(ubuntu_core_path))
        is_core = distro.is_ubuntu_core(self.target)
        self.assertTrue(is_core)

    def test_target_is_ubuntu_core_no_target(self):
        is_core = distro.is_ubuntu_core(self.target)
        self.assertFalse(is_core)

    def test_target_is_ubuntu_core_noncore_target(self):
        self.target = self.tmp_dir()
        non_core_path = os.path.join(self.target, 'curtin')
        util.ensure_dir(non_core_path)
        self.assertTrue(os.path.isdir(non_core_path))
        is_core = distro.is_ubuntu_core(self.target)
        self.assertFalse(is_core)

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_no_config(self, mock_handle_cc, mock_del_file,
                                 mock_write_file):
        self.target = self.tmp_dir()
        cfg = {}
        curthooks.ubuntu_core_curthooks(cfg, target=self.target)
        self.assertEqual(len(mock_handle_cc.call_args_list), 0)
        self.assertEqual(len(mock_del_file.call_args_list), 0)
        self.assertEqual(len(mock_write_file.call_args_list), 0)

    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_cloud_config_remove_disabled(self, mock_handle_cc):
        self.target = self.tmp_dir()
        uc_cloud = os.path.join(self.target, 'system-data', 'etc/cloud')
        cc_disabled = os.path.join(uc_cloud, 'cloud-init.disabled')
        cc_path = os.path.join(uc_cloud, 'cloud.cfg.d')

        util.ensure_dir(uc_cloud)
        util.write_file(cc_disabled, content="# disable cloud-init\n")
        cfg = {
            'cloudconfig': {
                'file1': {
                    'content': "Hello World!\n",
                }
            }
        }
        self.assertTrue(os.path.exists(cc_disabled))
        curthooks.ubuntu_core_curthooks(cfg, target=self.target)

        mock_handle_cc.assert_called_with(cfg.get('cloudconfig'),
                                          base_dir=cc_path)
        self.assertFalse(os.path.exists(cc_disabled))

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_cloud_config(self, mock_handle_cc, mock_del_file,
                                    mock_write_file):
        self.target = self.tmp_dir()
        cfg = {
            'cloudconfig': {
                'file1': {
                    'content': "Hello World!\n",
                }
            }
        }
        curthooks.ubuntu_core_curthooks(cfg, target=self.target)

        self.assertEqual(len(mock_del_file.call_args_list), 0)
        cc_path = os.path.join(self.target,
                               'system-data/etc/cloud/cloud.cfg.d')
        mock_handle_cc.assert_called_with(cfg.get('cloudconfig'),
                                          base_dir=cc_path)
        self.assertEqual(len(mock_write_file.call_args_list), 0)

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_net_config(self, mock_handle_cc, mock_del_file,
                                  mock_write_file):
        self.target = self.tmp_dir()
        cfg = {
            'network': {
                'version': '1',
                'config': [{'type': 'physical',
                            'name': 'eth0', 'subnets': [{'type': 'dhcp4'}]}]
            }
        }
        curthooks.ubuntu_core_curthooks(cfg, target=self.target)

        self.assertEqual(len(mock_del_file.call_args_list), 0)
        self.assertEqual(len(mock_handle_cc.call_args_list), 0)
        netcfg_path = os.path.join(self.target,
                                   'system-data',
                                   'etc/cloud/cloud.cfg.d',
                                   '50-curtin-networking.cfg')
        netcfg = config.dump_config({'network': cfg.get('network')})
        mock_write_file.assert_called_with(netcfg_path,
                                           content=netcfg)
        self.assertEqual(len(mock_del_file.call_args_list), 0)

    @patch('curtin.commands.curthooks.futil.write_files')
    def test_handle_cloudconfig(self, mock_write_files):
        cc_target = "tmpXXXX/systemd-data/etc/cloud/cloud.cfg.d"
        cloudconfig = {
            'file1': {
                'content': "Hello World!\n",
            },
            'foobar': {
                'path': '/sys/wark',
                'content': "Engauge!\n",
            }
        }

        expected_cfg = {
            'file1': {
                'path': '50-cloudconfig-file1.cfg',
                'content': cloudconfig['file1']['content']},
            'foobar': {
                'path': '50-cloudconfig-foobar.cfg',
                'content': cloudconfig['foobar']['content']}
        }
        curthooks.handle_cloudconfig(cloudconfig, base_dir=cc_target)
        mock_write_files.assert_called_with(expected_cfg, cc_target)

    def test_handle_cloudconfig_bad_config(self):
        with self.assertRaises(ValueError):
            curthooks.handle_cloudconfig([], base_dir="foobar")


class TestDetectRequiredPackages(CiTestCase):
    test_config = {
        'storage': {
            1: {
                'bcache': {
                    'type': 'bcache', 'name': 'bcache0', 'id': 'cache0',
                    'backing_device': 'sda3', 'cache_device': 'sdb'},
                'lvm_partition': {
                    'id': 'lvol1', 'name': 'lv1', 'volgroup': 'vg1',
                    'type': 'lvm_partition'},
                'lvm_volgroup': {
                    'id': 'vol1', 'name': 'vg1', 'devices': ['sda', 'sdb'],
                    'type': 'lvm_volgroup'},
                'raid': {
                    'id': 'mddevice', 'name': 'md0', 'type': 'raid',
                    'raidlevel': 5, 'devices': ['sda1', 'sdb1', 'sdc1']},
                'ext2': {
                    'id': 'format0', 'fstype': 'ext2', 'type': 'format'},
                'ext3': {
                    'id': 'format1', 'fstype': 'ext3', 'type': 'format'},
                'ext4': {
                    'id': 'format2', 'fstype': 'ext4', 'type': 'format'},
                'btrfs': {
                    'id': 'format3', 'fstype': 'btrfs', 'type': 'format'},
                'xfs': {
                    'id': 'format4', 'fstype': 'xfs', 'type': 'format'}}
        },
        'network': {
            1: {
                'bond': {
                    'name': 'bond0', 'type': 'bond',
                    'bond_interfaces': ['interface0', 'interface1'],
                    'params': {'bond-mode': 'active-backup'},
                    'subnets': [
                        {'type': 'static', 'address': '10.23.23.2/24'},
                        {'type': 'static', 'address': '10.23.24.2/24'}]},
                'vlan': {
                    'id': 'interface1.2667', 'mtu': 1500, 'name':
                    'interface1.2667', 'type': 'vlan', 'vlan_id': 2667,
                    'vlan_link': 'interface1',
                    'subnets': [{'address': '10.245.184.2/24',
                                 'dns_nameservers': [], 'type': 'static'}]},
                'bridge': {
                    'name': 'br0', 'bridge_interfaces': ['eth0', 'eth1'],
                    'type': 'bridge', 'params': {
                        'bridge_stp': 'off', 'bridge_fd': 0,
                        'bridge_maxwait': 0},
                    'subnets': [
                        {'type': 'static', 'address': '192.168.14.2/24'},
                        {'type': 'static', 'address': '2001:1::1/64'}]}},
            2: {
                'vlan': {
                    'vlans': {
                        'en-intra': {'id': 1, 'link': 'eno1', 'dhcp4': 'yes'},
                        'en-vpn': {'id': 2, 'link': 'eno1'}}},
                'bridge': {
                    'bridges': {
                        'br0': {
                            'interfaces': ['wlp1s0', 'switchports'],
                            'dhcp4': True}}}}
        },
    }

    def _fmt_config(self, config_items):
        res = {}
        for item, item_confs in config_items.items():
            version = item_confs['version']
            res[item] = {'version': version}
            if version == 1:
                res[item]['config'] = [self.test_config[item][version][i]
                                       for i in item_confs['items']]
            elif version == 2 and item == 'network':
                for cfg_item in item_confs['items']:
                    res[item].update(self.test_config[item][version][cfg_item])
            else:
                raise NotImplementedError
        return res

    def _test_req_mappings(self, req_mappings):
        for (config_items, expected_reqs) in req_mappings:
            cfg = self._fmt_config(config_items)
            actual_reqs = curthooks.detect_required_packages(cfg)
            self.assertEqual(set(actual_reqs), set(expected_reqs),
                             'failed for config: {}'.format(config_items))

    def test_storage_v1_detect(self):
        self._test_req_mappings((
            ({'storage': {
                'version': 1,
                'items': ('lvm_partition', 'lvm_volgroup', 'btrfs', 'xfs')}},
             ('lvm2', 'xfsprogs', 'btrfs-tools')),
            ({'storage': {
                'version': 1,
                'items': ('raid', 'bcache', 'ext3', 'xfs')}},
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'xfsprogs')),
            ({'storage': {
                'version': 1,
                'items': ('raid', 'lvm_volgroup', 'lvm_partition', 'ext3',
                          'ext4', 'btrfs')}},
             ('lvm2', 'mdadm', 'e2fsprogs', 'btrfs-tools')),
            ({'storage': {
                'version': 1,
                'items': ('bcache', 'lvm_volgroup', 'lvm_partition', 'ext2')}},
             ('bcache-tools', 'lvm2', 'e2fsprogs')),
        ))

    def test_network_v1_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 1,
                'items': ('bridge',)}},
             ('bridge-utils',)),
            ({'network': {
                'version': 1,
                'items': ('vlan', 'bond')}},
             ('vlan', 'ifenslave')),
            ({'network': {
                'version': 1,
                'items': ('bond', 'bridge')}},
             ('ifenslave', 'bridge-utils')),
            ({'network': {
                'version': 1,
                'items': ('vlan', 'bridge', 'bond')}},
             ('ifenslave', 'bridge-utils', 'vlan')),
        ))

    def test_mixed_v1_detect(self):
        self._test_req_mappings((
            ({'storage': {
                'version': 1,
                'items': ('raid', 'bcache', 'ext4')},
              'network': {
                  'version': 1,
                  'items': ('vlan',)}},
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'vlan')),
            ({'storage': {
                'version': 1,
                'items': ('lvm_partition', 'lvm_volgroup', 'xfs')},
              'network': {
                  'version': 1,
                  'items': ('bridge', 'bond')}},
             ('lvm2', 'xfsprogs', 'bridge-utils', 'ifenslave')),
            ({'storage': {
                'version': 1,
                'items': ('ext3', 'ext4', 'btrfs')},
              'network': {
                  'version': 1,
                  'items': ('bond', 'vlan')}},
             ('e2fsprogs', 'btrfs-tools', 'vlan', 'ifenslave')),
        ))

    def test_network_v2_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 2,
                'items': ('bridge',)}},
             ()),
            ({'network': {
                'version': 2,
                'items': ('vlan',)}},
             ()),
            ({'network': {
                'version': 2,
                'items': ('vlan', 'bridge')}},
             ()),
        ))

    def test_mixed_storage_v1_network_v2_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 2,
                'items': ('bridge', 'vlan')},
             'storage': {
                 'version': 1,
                 'items': ('raid', 'bcache', 'ext4')}},
             ('mdadm', 'bcache-tools', 'e2fsprogs')),
        ))

    def test_invalid_version_in_config(self):
        with self.assertRaises(ValueError):
            curthooks.detect_required_packages({'network': {'version': 3}})


class TestCurthooksWriteFiles(CiTestCase):
    def test_handle_write_files_empty(self):
        """ Test curthooks.write_files returns for empty config """
        tmpd = self.tmp_dir()
        ret = curthooks.write_files({}, tmpd)
        self.assertEqual({}, dir2dict(tmpd, prefix=tmpd))
        self.assertIsNone(ret)

    def test_handle_write_files(self):
        """ Test curthooks.write_files works as it used to """
        tmpd = self.tmp_dir()
        cfg = {'file1': {'path': '/etc/default/hello.txt',
                         'content': "Hello World!\n"},
               'foobar': {'path': '/sys/wark', 'content': "Engauge!\n"}}
        curthooks.write_files({'write_files': cfg}, tmpd)
        self.assertEqual(
            dict((cfg[i]['path'], cfg[i]['content']) for i in cfg.keys()),
            dir2dict(tmpd, prefix=tmpd))

    @patch('curtin.commands.curthooks.paths.target_path')
    @patch('curtin.commands.curthooks.futil.write_finfo')
    def test_handle_write_files_finfo(self, mock_write_finfo, mock_tp):
        """ Validate that futils.write_files handles target_path correctly """
        cc_target = "/tmpXXXX/random/dir/used/by/maas"
        cfg = {
            'file1': {
                'path': '/etc/default/hello.txt',
                'content': "Hello World!\n",
            },
        }
        mock_tp.side_effect = [
            cc_target + cfg['file1']['path'],
        ]

        expected_cfg = {
            'file1': {
                'path': '/etc/default/hello.txt',
                'content': cfg['file1']['content']},
        }
        curthooks.write_files({'write_files': cfg}, cc_target)
        mock_write_finfo.assert_called_with(
            content=expected_cfg['file1']['content'], owner='-1:-1',
            path=cc_target + expected_cfg['file1']['path'],
            perms='0644')


class TestCurthooksPollinate(CiTestCase):
    def setUp(self):
        super(TestCurthooksPollinate, self).setUp()
        self.add_patch('curtin.version.version_string', 'mock_curtin_version')
        self.add_patch('curtin.util.write_file', 'mock_write')
        self.add_patch('curtin.commands.curthooks.get_maas_version',
                       'mock_maas_version')
        self.add_patch('curtin.util.which', 'mock_which')
        self.mock_which.return_value = '/usr/bin/pollinate'
        self.target = self.tmp_dir()

    def test_handle_pollinate_user_agent_disable(self):
        """ handle_pollinate_user_agent does nothing if disabled """
        cfg = {'pollinate': {'user_agent': False}}
        curthooks.handle_pollinate_user_agent(cfg, self.target)
        self.assertEqual(0, self.mock_curtin_version.call_count)
        self.assertEqual(0, self.mock_maas_version.call_count)
        self.assertEqual(0, self.mock_write.call_count)

    def test_handle_pollinate_returns_if_no_pollinate_binary(self):
        """ handle_pollinate_user_agent does nothing if no pollinate binary"""
        self.mock_which.return_value = None
        cfg = {'reporting': {'maas': {'endpoint': 'http://127.0.0.1/foo'}}}
        curthooks.handle_pollinate_user_agent(cfg, self.target)
        self.assertEqual(0, self.mock_curtin_version.call_count)
        self.assertEqual(0, self.mock_maas_version.call_count)
        self.assertEqual(0, self.mock_write.call_count)

    def test_handle_pollinate_user_agent_default(self):
        """ handle_pollinate_user_agent checks curtin/maas version by default
        """
        cfg = {'reporting': {'maas': {'endpoint': 'http://127.0.0.1/foo'}}}
        curthooks.handle_pollinate_user_agent(cfg, self.target)
        self.assertEqual(1, self.mock_curtin_version.call_count)
        self.assertEqual(1, self.mock_maas_version.call_count)
        self.assertEqual(1, self.mock_write.call_count)

    def test_handle_pollinate_user_agent_default_no_maas(self):
        """ handle_pollinate_user_agent checks curtin version, skips maas """
        cfg = {}
        curthooks.handle_pollinate_user_agent(cfg, self.target)
        self.assertEqual(1, self.mock_curtin_version.call_count)
        self.assertEqual(0, self.mock_maas_version.call_count)
        self.assertEqual(1, self.mock_write.call_count)

    @patch('curtin.commands.curthooks.inject_pollinate_user_agent_config')
    def test_handle_pollinate_user_agent_custom(self, mock_inject):
        """ handle_pollinate_user_agent merges custom with default config """
        self.mock_curtin_version.return_value = 'curtin-version'
        cfg = {'pollinate': {'user_agent': {'myapp': 'myversion'}}}
        curthooks.handle_pollinate_user_agent(cfg, self.target)
        self.assertEqual(1, self.mock_curtin_version.call_count)
        self.assertEqual(0, self.mock_maas_version.call_count)
        expected_cfg = {
            'curtin': 'curtin-version',
            'myapp': 'myversion',
        }
        mock_inject.assert_called_with(expected_cfg, self.target)


class TestCurthooksInjectPollinate(CiTestCase):
    def setUp(self):
        super(TestCurthooksInjectPollinate, self).setUp()
        self.target = self.tmp_dir()
        self.user_agent = os.path.join(self.target,
                                       'etc/pollinate/add-user-agent')

    def test_inject_ua_output(self):
        cfg = {'mykey': 'myvalue', 'foobar': 127}
        expected_content = [
            "mykey/myvalue # written by curtin\n",
            "foobar/127 # written by curtin\n"
        ]
        curthooks.inject_pollinate_user_agent_config(cfg, self.target)
        content = open(self.user_agent).readlines()
        for line in expected_content:
            self.assertIn(line, content)

    def test_inject_ua_raises_exception(self):
        with self.assertRaises(ValueError):
            curthooks.inject_pollinate_user_agent_config(None, self.target)


class TestCurthooksChzdev(CiTestCase):

    chzdev_export = textwrap.dedent("""\
    # Generated by chzdev on s1lp6
    [active dasd-eckd 0.0.1518]
    online=1
    expires=30
    retries=256

    [active zfcp-host 0.0.e000]
    online=1

    [active zfcp-lun 0.0.e000:0x50050763060b16b6:0x4024400600000000]
    scsi_dev/queue_depth=32

    [active qeth 0.0.c000:0.0.c001:0.0.c002]
    online=1
    layer2=1
    buffer_count=64
    vnicc/flooding=n/a
    vnicc/mcast_flooding=n/a
    vnicc/learning=n/a
    vnicc/learning_timeout=n/a
    vnicc/takeover_setvmac=n/a
    vnicc/takeover_learning=n/a
    vnicc/bridge_invisible=n/a
    vnicc/rx_bcast=n/a""")

    chzdev_import = textwrap.dedent("""\
    # Generated by chzdev on s1lp6
    [persistent dasd-eckd 0.0.1518]
    online=1
    expires=30
    retries=256

    [persistent zfcp-host 0.0.e000]
    online=1

    [persistent zfcp-lun 0.0.e000:0x50050763060b16b6:0x4024400600000000]
    scsi_dev/queue_depth=32

    [persistent qeth 0.0.c000:0.0.c001:0.0.c002]
    online=1
    layer2=1
    buffer_count=64""")

    def setUp(self):
        super(TestCurthooksChzdev, self).setUp()
        self.add_patch('curtin.commands.curthooks.util.subp', 'm_subp')
        self.add_patch('platform.machine', 'm_machine')
        self.target = self.tmp_dir()
        self.chzdev_export_fn = os.path.join(self.target, self.random_string())
        self.chzdev_import_fn = os.path.join(self.target, self.random_string())

        # defaults
        self.m_machine.return_value = 's390x'
        self.m_subp.return_value = ('', '')

    @patch('curtin.commands.curthooks.chzdev_export')
    @patch('curtin.commands.curthooks.chzdev_prepare_for_import')
    @patch('curtin.commands.curthooks.chzdev_import')
    def test_chzdev_persist_skips_if_not_s390x(self, m_chz_import,
                                               m_chz_prepare, m_chz_export):
        """chzdev_persist skips running if not on s390x."""
        self.m_machine.return_value = self.random_string()
        curthooks.chzdev_persist_active_online({}, self.target)
        self.assertEqual(0, m_chz_export.call_count)
        self.assertEqual(0, m_chz_prepare.call_count)
        self.assertEqual(0, m_chz_import.call_count)

    @patch('curtin.commands.curthooks.chzdev_export')
    @patch('curtin.commands.curthooks.chzdev_prepare_for_import')
    @patch('curtin.commands.curthooks.chzdev_import')
    def test_chzdev_persist_into_target(self, m_chz_import,
                                        m_chz_prepare, m_chz_export):
        """chzdev_persist uses export, sends to prepare & import consumes."""
        export_value = self.random_string()
        import_value = self.random_string().encode()
        m_chz_export.return_value = (export_value, '')
        m_chz_prepare.return_value = import_value
        curthooks.chzdev_persist_active_online({}, self.target)
        self.assertEqual(1, m_chz_export.call_count)
        self.assertEqual(1, m_chz_prepare.call_count)
        self.assertEqual(1, m_chz_import.call_count)
        m_chz_prepare.assert_called_with(export_value)
        m_chz_import.assert_called_with(data=import_value,
                                        persistent=True, noroot=True,
                                        base={'/etc': self.target + '/etc'})

    def test_export_defaults_to_stdout(self):
        """chzdev_export returns (stdout, stderr) from subp."""
        self.m_subp.return_value = (self.chzdev_export, '')
        self.assertEqual(self.chzdev_export, curthooks.chzdev_export()[0])

    def test_export_passed_export_file_param_to_subp(self):
        """chzdev_export specifies export_file value to chzdev command."""
        curthooks.chzdev_export(export_file=self.chzdev_export_fn)
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--active', '--online', '--export',
             self.chzdev_export_fn], capture=True)

    def test_export_passed_persistent_if_true(self):
        """chzdev_export passed --persistent if param is Ture."""
        curthooks.chzdev_export(persistent=True)
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--active', '--online', '--persistent',
             '--export', '-'], capture=True)

    def test_import_raises_error_on_no_input(self):
        """chzdev_import raises ValueError if data or import_file are None."""
        with self.assertRaises(ValueError):
            curthooks.chzdev_import()

    def test_import_accepts_data_or_import_file(self):
        """chzdev_import accepts data or import_file."""
        curthooks.chzdev_import(data=self.chzdev_import)
        curthooks.chzdev_import(import_file=self.chzdev_import_fn)

    def test_import_accepts_data_and_import_file(self):
        """chzdev_import raises ValueError if data and import_file."""
        with self.assertRaises(ValueError):
            curthooks.chzdev_import(data=self.chzdev_import,
                                    import_file=self.chzdev_import_fn)

    def test_import_passes_data_to_subp(self):
        """chzdev_import passed data to subp (stdinput) and input_file is -."""
        curthooks.chzdev_import(data=self.chzdev_import)
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--persistent', '--no-root-update',
             '--import', '-'], data=self.chzdev_import.encode(), capture=True)

    def test_import_sets_import_file(self):
        """chzdev_import passed import_file value to subp."""
        curthooks.chzdev_import(import_file=self.chzdev_import_fn)
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--persistent', '--no-root-update',
             '--import', self.chzdev_import_fn], data=None, capture=True)

    def test_import_sets_base_param_from_dict(self):
        """chzdev_import passed --base key=value from dict param."""
        mykey = self.random_string()
        myval = self.random_string()
        curthooks.chzdev_import(data=self.chzdev_import, base={mykey: myval})
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--persistent', '--no-root-update',
             '--base', '%s=%s' % (mykey, myval),
             '--import', '-'], data=self.chzdev_import.encode(), capture=True)

    def test_import_sets_base_param_from_string(self):
        """chzdev_import passed --base value for string input."""
        mybase = self.random_string()
        curthooks.chzdev_import(data=self.chzdev_import, base=mybase)
        self.m_subp.assert_called_with(
            ['chzdev', '--quiet', '--persistent', '--no-root-update',
             '--base', mybase, '--import', '-'],
            data=self.chzdev_import.encode(), capture=True)

    def test_import_skips_persist_and_noroot_if_false(self):
        """chzdev_import omits --persistent and --no-root-update on false."""
        curthooks.chzdev_import(data=self.chzdev_import, persistent=False,
                                noroot=False)
        self.m_subp.assert_called_with(['chzdev', '--quiet', '--import', '-'],
                                       data=self.chzdev_import.encode(),
                                       capture=True)

    def test_prepare_empty_content(self):
        """chzdev_prepare raises ValueError with invalid input."""
        for invalid in [None, '', ('',), 123]:
            with self.assertRaises(ValueError):
                curthooks.chzdev_prepare_for_import(invalid)

    def test_prepare_non_chzdev_content(self):
        """chzdev_prepare ignores non-chzdev string input."""
        conf = self.random_string()
        self.assertEqual(conf, curthooks.chzdev_prepare_for_import(conf))

    def test_prepare_transforms_active_drops_na(self):
        """chzdev_prepare transforms active to persistent and removes n/a."""
        output = curthooks.chzdev_prepare_for_import(self.chzdev_export)
        self.assertEqual(self.chzdev_import, output)


class TestCurthooksCopyZkey(CiTestCase):
    def setUp(self):
        super(TestCurthooksCopyZkey, self).setUp()
        self.add_patch('curtin.distro.install_packages', 'mock_instpkg')

        self.target = self.tmp_dir()
        self.host_dir = self.tmp_dir()
        self.zkey_content = {
            '/etc/zkey/repository/mykey.info': "key info",
            '/etc/zkey/repository/mykey.skey': "key data",
        }
        self.files = populate_dir(self.host_dir, self.zkey_content)
        self.host_zkey = os.path.join(self.host_dir, 'etc/zkey/repository')

    def test_copy_zkey_when_dir_present(self):
        curthooks.copy_zkey_repository(self.host_zkey, self.target)
        found_files = dir2dict(self.target, prefix=self.target)
        self.assertEqual(self.zkey_content, found_files)


# vi: ts=4 expandtab syntax=python
