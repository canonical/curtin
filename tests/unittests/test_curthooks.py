import os
from unittest import TestCase
from mock import call, patch
import shutil
import tempfile

from curtin.commands import curthooks
from curtin import util
from curtin import config
from curtin.reporter import events


class CurthooksBase(TestCase):
    def setUp(self):
        super(CurthooksBase, self).setUp()

    def add_patch(self, target, attr):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = patch(target, autospec=True)
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


class TestMultipath(CurthooksBase):
    def setUp(self):
        super(TestMultipath, self).setUp()
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.add_patch('curtin.util.install_packages', 'mock_instpkg')
        self.add_patch('curtin.block.detect_multipath',
                       'mock_blk_detect_multi')
        self.add_patch('curtin.block.get_devices_for_mp',
                       'mock_blk_get_devs_for_mp')
        self.add_patch('curtin.block.get_scsi_wwid',
                       'mock_blk_get_scsi_wwid')
        self.add_patch('curtin.block.get_blockdev_for_partition',
                       'mock_blk_get_blockdev_for_partition')
        self.add_patch('curtin.commands.curthooks.update_initramfs',
                       'mock_update_initramfs')
        self.target = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_multipath_cfg_disabled(self):
        cfg = {'multipath': {'mode': 'disabled'}}

        curthooks.detect_and_handle_multipath(cfg, self.target)
        self.assertEqual(None, self.mock_instpkg.call_args)

    def test_multipath_cfg_mode_auto_no_mpdevs(self):
        cfg = {'multipath': {'mode': 'auto'}}
        self.mock_blk_detect_multi.return_value = False

        curthooks.detect_and_handle_multipath(cfg, self.target)

        self.assertEqual(None, self.mock_instpkg.call_args)

    def _detect_and_handle_multipath(self, multipath_version=None,
                                     replace_spaces=None):
        self.mock_subp.side_effect = iter([
            (multipath_version, None),
            (None, None),
        ])

        target_dev = '/dev/sdz'
        partno = 1
        wwid = 'CURTIN WWID'
        if replace_spaces:
            wwid = 'CURTIN_WWID'
        # hard-coded in curtin
        mpname = "mpath0"
        grub_dev = "/dev/mapper/" + mpname
        if partno is not None:
            grub_dev += "-part%s" % partno

        self.mock_blk_detect_multi.return_value = True
        self.mock_blk_get_devs_for_mp.return_value = [target_dev]
        self.mock_blk_get_scsi_wwid.return_value = wwid
        self.mock_blk_get_blockdev_for_partition.return_value = (target_dev,
                                                                 partno)

        curthooks.detect_and_handle_multipath({}, self.target)

        self.mock_instpkg.assert_has_calls([
            call(['multipath-tools-boot'], target=self.target)])
        self.mock_blk_get_scsi_wwid.assert_has_calls([
            call(target_dev, replace_whitespace=replace_spaces)])
        self.mock_update_initramfs.assert_has_calls([
            call(self.target, all_kernels=True)])

        multipath_cfg_path = os.path.sep.join([self.target,
                                               '/etc/multipath.conf'])
        multipath_bind_path = os.path.sep.join([self.target,
                                                '/etc/multipath/bindings'])
        grub_cfg = os.path.sep.join([
            self.target, '/etc/default/grub.d/50-curtin-multipath.cfg'])

        expected_grub_dev = "GRUB_DEVICE=%s\n" % grub_dev
        expected_mpath_bind = "%s %s\n" % (mpname, wwid)
        expected_mpath_cfg = "\tuser_friendly_names yes\n"

        files_to_check = {
            grub_cfg: expected_grub_dev,
            multipath_bind_path: expected_mpath_bind,
            multipath_cfg_path: expected_mpath_cfg,
        }

        for (path, matchstr) in files_to_check.items():
            with open(path) as fh:
                self.assertIn(matchstr, fh.readlines())

    @patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    def test_install_multipath_dont_replace_whitespace(self):
        # validate that for multipath version 0.4.9, we do NOT replace spaces
        self._detect_and_handle_multipath(multipath_version='0.4.9',
                                          replace_spaces=False)

    @patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    def test_install_multipath_replace_whitespace(self):
        # validate that for multipath version 0.5.0, we DO replace spaces
        self._detect_and_handle_multipath(multipath_version='0.5.0',
                                          replace_spaces=True)


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
        netcfg = config.dump_config(cfg.get('network'))
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
