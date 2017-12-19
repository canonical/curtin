import os
from mock import call, patch, MagicMock

from curtin.commands import curthooks
from curtin import util
from curtin import config
from curtin.reporter import events
from .helpers import CiTestCase


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
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
        self.add_patch('curtin.util.install_packages', 'mock_instpkg')
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


class TestInstallMissingPkgs(CiTestCase):
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
        is_core = curthooks.target_is_ubuntu_core(self.target)
        self.assertTrue(is_core)

    def test_target_is_ubuntu_core_no_target(self):
        is_core = curthooks.target_is_ubuntu_core(self.target)
        self.assertFalse(is_core)

    def test_target_is_ubuntu_core_noncore_target(self):
        self.target = self.tmp_dir()
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
             ('bridge-utils',)),
            ({'network': {
                'version': 2,
                'items': ('vlan',)}},
             ('vlan',)),
            ({'network': {
                'version': 2,
                'items': ('vlan', 'bridge')}},
             ('vlan', 'bridge-utils')),
        ))

    def test_mixed_storage_v1_network_v2_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 2,
                'items': ('bridge', 'vlan')},
             'storage': {
                 'version': 1,
                 'items': ('raid', 'bcache', 'ext4')}},
             ('vlan', 'bridge-utils', 'mdadm', 'bcache-tools', 'e2fsprogs')),
        ))

    def test_invalid_version_in_config(self):
        with self.assertRaises(ValueError):
            curthooks.detect_required_packages({'network': {'version': 3}})


# vi: ts=4 expandtab syntax=python
