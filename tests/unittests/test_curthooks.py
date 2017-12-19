import os
from unittest import TestCase
from mock import call, patch, MagicMock
import shutil
import tempfile

from curtin.commands import curthooks
from curtin import util
from curtin import config
from curtin.reporter import events


class CurthooksBase(TestCase):
    def setUp(self):
        super(CurthooksBase, self).setUp()

    def add_patch(self, target, attr, autospec=True):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = patch(target, autospec=autospec)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class TestGetFlashKernelPkgs(CurthooksBase):
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


class TestCurthooksInstallKernel(CurthooksBase):
    def setUp(self):
        super(TestCurthooksInstallKernel, self).setUp()
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.util.install_packages', 'mock_instpkg')
        self.add_patch(
            'curtin.commands.curthooks.get_flash_kernel_pkgs',
            'mock_get_flash_kernel_pkgs')

        self.kernel_cfg = {'kernel': {'package': 'mock-linux-kernel',
                                      'fallback-package': 'mock-fallback',
                                      'mapping': {}}}
        # Tests don't actually install anything so we just need a name
        self.target = tempfile.mktemp()

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


class TestUpdateInitramfs(CurthooksBase):
    def setUp(self):
        super(TestUpdateInitramfs, self).setUp()
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.target = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.target)

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


class TestInstallMissingPkgs(CurthooksBase):
    def setUp(self):
        super(TestInstallMissingPkgs, self).setUp()
        self.add_patch('platform.machine', 'mock_machine')
        self.add_patch('curtin.util.get_installed_packages',
                       'mock_get_installed_packages')
        self.add_patch('curtin.util.load_command_environment',
                       'mock_load_cmd_evn')
        self.add_patch('curtin.util.which', 'mock_which')
        self.add_patch('curtin.util.install_packages', 'mock_install_packages')

    @patch.object(events, 'ReportEventStack')
    def test_install_packages_s390x(self, mock_events):

        self.mock_machine.return_value = "s390x"
        self.mock_which.return_value = False
        target = "not-a-real-target"
        cfg = {}
        curthooks.install_missing_packages(cfg, target=target)
        self.mock_install_packages.assert_called_with(['s390-tools'],
                                                      target=target)

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


class TestSetupGrub(CurthooksBase):

    def setUp(self):
        super(TestSetupGrub, self).setUp()
        self.target = tempfile.mkdtemp()
        self.add_patch('curtin.util.lsb_release', 'mock_lsb_release')
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

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_uses_old_grub_install_devices_in_cfg(self):
        cfg = {
            'grub_install_devices': ['/dev/vdb']
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_uses_install_devices_in_grubcfg(self):
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
            },
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', self.target, '/dev/vdb'],),
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
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_installs_to_none_if_install_devices_None(self):
        cfg = {
            'grub': {
                'install_devices': None,
            },
        }
        self.subp_output.append(('', ''))
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', self.target, 'none'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_installs_signed_packages_for_amd64(self):
        self.add_patch('curtin.util.install_packages', 'mock_install')
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
        self.mock_is_uefi_bootable.return_value = True
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
                'update_nvram': False,
            },
        }
        self.subp_output.append(('', ''))
        self.mock_arch.return_value = 'amd64'
        self.mock_haspkg.return_value = True
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            (['grub-efi-amd64', 'grub-efi-amd64-signed', 'shim-signed'],),
            self.mock_install.call_args_list[0][0])
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--uefi', self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_installs_packages_for_arm64(self):
        self.add_patch('curtin.util.install_packages', 'mock_install')
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
        self.mock_is_uefi_bootable.return_value = True
        cfg = {
            'grub': {
                'install_devices': ['/dev/vdb'],
                'update_nvram': False,
            },
        }
        self.subp_output.append(('', ''))
        self.mock_arch.return_value = 'arm64'
        self.mock_haspkg.return_value = False
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            (['grub-efi-arm64'],),
            self.mock_install.call_args_list[0][0])
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--uefi', self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_updates_nvram_skips_remove_and_reorder(self):
        self.add_patch('curtin.util.install_packages', 'mock_install')
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
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
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            ([
                'sh', '-c', 'exec "$0" "$@" 2>&1',
                'install-grub', '--uefi', '--update-nvram',
                self.target, '/dev/vdb'],),
            self.mock_subp.call_args_list[0][0])

    def test_grub_install_uefi_updates_nvram_removes_old_loaders(self):
        self.add_patch('curtin.util.install_packages', 'mock_install')
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
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
        curthooks.setup_grub(cfg, self.target)
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
        self.add_patch('curtin.util.install_packages', 'mock_install')
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
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
        curthooks.setup_grub(cfg, self.target)
        self.assertEquals(
            (['efibootmgr', '-o', '0001,0000'],),
            self.mock_in_chroot_subp.call_args_list[0][0])


class TestUbuntuCoreHooks(CurthooksBase):
    def setUp(self):
        super(TestUbuntuCoreHooks, self).setUp()
        self.target = None

    def tearDown(self):
        if self.target:
            shutil.rmtree(self.target)

    def test_target_is_ubuntu_core(self):
        self.target = tempfile.mkdtemp()
        ubuntu_core_path = os.path.join(self.target, 'system-data',
                                        'var/lib/snapd')
        util.ensure_dir(ubuntu_core_path)
        self.assertTrue(os.path.isdir(ubuntu_core_path))
        is_core = curthooks.target_is_ubuntu_core(self.target)
        self.assertTrue(is_core)

    def test_target_is_ubuntu_core_no_target(self):
        is_core = curthooks.target_is_ubuntu_core(self.target)
        self.assertFalse(is_core)

    def test_target_is_ubuntu_core_noncore_target(self):
        self.target = tempfile.mkdtemp()
        non_core_path = os.path.join(self.target, 'curtin')
        util.ensure_dir(non_core_path)
        self.assertTrue(os.path.isdir(non_core_path))
        is_core = curthooks.target_is_ubuntu_core(self.target)
        self.assertFalse(is_core)

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_no_config(self, mock_handle_cc, mock_del_file,
                                 mock_write_file):
        self.target = tempfile.mkdtemp()
        cfg = {}
        curthooks.ubuntu_core_curthooks(cfg, target=self.target)
        self.assertEqual(len(mock_handle_cc.call_args_list), 0)
        self.assertEqual(len(mock_del_file.call_args_list), 0)
        self.assertEqual(len(mock_write_file.call_args_list), 0)

    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_cloud_config_remove_disabled(self, mock_handle_cc):
        self.target = tempfile.mkdtemp()
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
                                          target=cc_path)
        self.assertFalse(os.path.exists(cc_disabled))

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_cloud_config(self, mock_handle_cc, mock_del_file,
                                    mock_write_file):
        self.target = tempfile.mkdtemp()
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
                                          target=cc_path)
        self.assertEqual(len(mock_write_file.call_args_list), 0)

    @patch('curtin.util.write_file')
    @patch('curtin.util.del_file')
    @patch('curtin.commands.curthooks.handle_cloudconfig')
    def test_curthooks_net_config(self, mock_handle_cc, mock_del_file,
                                  mock_write_file):
        self.target = tempfile.mkdtemp()
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
                                   '50-network-config.cfg')
        netcfg = config.dump_config({'network': cfg.get('network')})
        mock_write_file.assert_called_with(netcfg_path,
                                           content=netcfg)
        self.assertEqual(len(mock_del_file.call_args_list), 0)

    @patch('curtin.commands.curthooks.write_files')
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
            'write_files': {
                'file1': {
                    'path': '50-cloudconfig-file1.cfg',
                    'content': cloudconfig['file1']['content']},
                'foobar': {
                    'path': '50-cloudconfig-foobar.cfg',
                    'content': cloudconfig['foobar']['content']}
            }
        }
        curthooks.handle_cloudconfig(cloudconfig, target=cc_target)
        mock_write_files.assert_called_with(expected_cfg, cc_target)

    def test_handle_cloudconfig_bad_config(self):
        with self.assertRaises(ValueError):
            curthooks.handle_cloudconfig([], target="foobar")

# vi: ts=4 expandtab syntax=python
