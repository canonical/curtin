# This file is part of curtin. See LICENSE file for copyright and license info.

import copy
import mock

from curtin import config
from curtin.commands import install
from curtin.util import BadUsage, ensure_dir, write_file
from .helpers import CiTestCase
from collections import namedtuple


FakeArgs = namedtuple('FakeArgs', ['config', 'source', 'reportstack'])


class FakeReportStack(object):
    post_files = []
    reporting_enabled = False
    fullname = 'fake-report-stack'
    children = {}


class TestMigrateProxy(CiTestCase):

    def test_legacy_moved_over(self):
        """Legacy setting should get moved over."""
        proxy = "http://my.proxy:3128"
        cfg = {'http_proxy': proxy}
        install.migrate_proxy_settings(cfg)
        self.assertEqual(cfg, {'proxy': {'http_proxy': proxy}})

    def test_no_legacy_new_only(self):
        """If only new 'proxy', then no change is expected."""
        proxy = "http://my.proxy:3128"
        cfg = {'proxy': {'http_proxy': proxy, 'https_proxy': proxy,
                         'no_proxy': "10.2.2.2"}}
        expected = copy.deepcopy(cfg)
        install.migrate_proxy_settings(cfg)
        self.assertEqual(expected, cfg)


class TestCmdInstall(CiTestCase):

    def setUp(self):
        super(TestCmdInstall, self).setUp()
        self.new_root = self.tmp_dir()
        self.logfile = self.tmp_path('my.log', _dir=self.new_root)

    def test_error_no_sources_in_config(self):
        """An error is raised when the configuration does not have sources."""
        myargs = FakeArgs(config={}, source=[], reportstack=None)
        with self.assertRaises(BadUsage) as context_manager:
            install.cmd_install(myargs)
        self.assertEqual(
            'no sources provided to install', str(context_manager.exception))

    def test_error_invalid_proxy_value(self):
        """An error is raised when the proxy configuration is not a dict."""
        myargs = FakeArgs(config={
            'proxy': 'junk'},
            source=['https://cloud-images.ubuntu.com/some.tar.gz'],
            reportstack=None)
        with self.assertRaises(ValueError) as context_manager:
            install.cmd_install(myargs)
        self.assertEqual(
            "'proxy' in config is not a dictionary: junk",
            str(context_manager.exception))

    def test_curtin_error_unmount_doesnt_lose_exception(self):
        """Confirm unmount:disable skips unmounting, keeps exception"""
        working_dir = self.tmp_path('working', _dir=self.new_root)
        ensure_dir(working_dir)
        write_file(self.logfile, 'old log')

        # Providing two dd images raises an error, set unmount: disabled
        myargs = FakeArgs(
            config={'install':
                    {'log_file': self.logfile, 'unmount': 'disabled'}},
            source=['dd-raw:https://localhost/raw_images/centos-6-3.img',
                    'dd-raw:https://localhost/cant/provide/two/images.img'],
            reportstack=FakeReportStack())
        self.add_patch(
            'curtin.commands.collect_logs.create_log_tarfile', 'm_tar')
        self.add_patch(
            'curtin.commands.install.copy_install_log', 'm_copy_log')
        self.add_patch('curtin.util.do_umount', 'm_umount')

        rv = 42
        with self.assertRaises(Exception):
            rv = install.cmd_install(myargs)

        # make sure install.cmd_install does not return a value, but Exception
        self.assertEqual(42, rv)
        self.assertEqual(0, self.m_umount.call_count)
        self.assertEqual(1, self.m_copy_log.call_count)

    def test_curtin_error_copies_config_and_error_tarfile_defaults(self):
        """On curtin error, install error_tarfile is created with all logs.

        Curtin config, install log and error_tarfile are copied into target.
        """
        working_dir = self.tmp_path('working', _dir=self.new_root)
        ensure_dir(working_dir)
        target_dir = self.tmp_path('target', _dir=working_dir)
        write_file(self.logfile, 'old log')
        # Providing two dd images raises an error
        myargs = FakeArgs(
            config={'install': {'log_file': self.logfile}},
            source=['dd-raw:https://localhost/raw_images/centos-6-3.img',
                    'dd-raw:https://localhost/cant/provide/two/images.img'],
            reportstack=FakeReportStack())
        self.add_patch(
            'curtin.commands.collect_logs.create_log_tarfile', 'm_tar')
        self.add_patch(
            'curtin.commands.install.copy_install_log', 'm_copy_log')
        self.add_patch(
            'curtin.commands.install.tempfile.mkdtemp', 'm_mkdtemp')
        self.m_mkdtemp.return_value = working_dir
        with self.assertRaises(ValueError) as context_manager:
            install.cmd_install(myargs)
        self.assertEqual(
            'You may not use more than one disk image',
            str(context_manager.exception))
        expected_cfg = copy.deepcopy(install.CONFIG_BUILTIN)
        expected_cfg['install']['log_file'] = self.logfile
        expected_cfg['proxy'] = {}
        expected_cfg['sources'] = {
            '00_cmdline': {
                'type': 'dd-raw',
                'uri': 'https://localhost/raw_images/centos-6-3.img'},
            '01_cmdline': {
                'type': 'dd-raw',
                'uri': 'https://localhost/cant/provide/two/images.img'}}
        expected_cfg['write_files'] = {
            'curtin_install_cfg': {
                'owner': 'root:root', 'permissions': '0400',
                'path': '/root/curtin-install-cfg.yaml',
                'content': config.dump_config(expected_cfg)}}
        # Call create_log_tarfile to collect error logs.
        self.assertEqual(
            [mock.call('/var/log/curtin/curtin-error-logs.tar', expected_cfg)],
            self.m_tar.call_args_list)
        self.assertEqual(
            [mock.call(self.logfile, target_dir, '/root/curtin-install.log')],
            self.m_copy_log.call_args_list)

    def test_curtin_error_tarfile_not_created_when_skip_error_tarfile(self):
        """When error_tarfile is None, no tarfile is created."""
        working_dir = self.tmp_path('working', _dir=self.new_root)
        ensure_dir(working_dir)
        target_dir = self.tmp_path('target', _dir=working_dir)
        # Providing two dd images raises an error
        myargs = FakeArgs(
            config={'install': {'log_file': self.logfile,
                                'error_tarfile': None}},
            source=['dd-raw:https://localhost/raw_images/centos-6-3.img',
                    'dd-raw:https://localhost/cant/provide/two/images.img'],
            reportstack=FakeReportStack())
        self.add_patch(
            'curtin.commands.collect_logs.create_log_tarfile', 'm_tar')
        self.add_patch(
            'curtin.commands.install.copy_install_log', 'm_copy_log')
        self.add_patch(
            'curtin.commands.install.tempfile.mkdtemp', 'm_mkdtemp')
        self.m_mkdtemp.return_value = working_dir
        with self.assertRaises(ValueError) as context_manager:
            install.cmd_install(myargs)
        self.assertEqual(
            'You may not use more than one disk image',
            str(context_manager.exception))
        expected_cfg = copy.deepcopy(install.CONFIG_BUILTIN)
        expected_cfg['install'] = {
            'log_file': self.logfile, 'error_tarfile': None}
        expected_cfg['proxy'] = {}
        expected_cfg['sources'] = {
            '00_cmdline': {
                'type': 'dd-raw',
                'uri': 'https://localhost/raw_images/centos-6-3.img'},
            '01_cmdline': {
                'type': 'dd-raw',
                'uri': 'https://localhost/cant/provide/two/images.img'}}
        expected_cfg['write_files'] = {
            'curtin_install_cfg': {
                'owner': 'root:root', 'permissions': '0400',
                'path': '/root/curtin-install-cfg.yaml',
                'content': config.dump_config(expected_cfg)}}
        # Call create_log_tarfile not called to create tarfile
        self.assertEqual([], self.m_tar.call_args_list)
        self.assertEqual(
            [mock.call(self.logfile, target_dir, '/root/curtin-install.log')],
            self.m_copy_log.call_args_list)


class TestWorkingDir(CiTestCase):
    def test_target_dir_may_exist(self):
        """WorkingDir supports existing empty target directory."""
        tmp_d = self.tmp_dir()
        work_d = self.tmp_path("work_d", tmp_d)
        target_d = self.tmp_path("target_d", tmp_d)
        ensure_dir(work_d)
        ensure_dir(target_d)
        with mock.patch("curtin.commands.install.tempfile.mkdtemp",
                        return_value=work_d) as m_mkdtemp:
            workingdir = install.WorkingDir({'install': {'target': target_d}})
        self.assertEqual(1, m_mkdtemp.call_count)
        self.assertEqual(target_d, workingdir.target)
        self.assertEqual(target_d, workingdir.env().get('TARGET_MOUNT_POINT'))

    def test_target_dir_with_content_raises_error(self):
        """WorkingDir raises ValueError on populated target_d."""
        tmp_d = self.tmp_dir()
        work_d = self.tmp_path("work_d", tmp_d)
        target_d = self.tmp_path("target_d", tmp_d)
        ensure_dir(work_d)
        ensure_dir(target_d)
        write_file(self.tmp_path("somefile.txt", target_d), "sometext")
        with mock.patch("curtin.commands.install.tempfile.mkdtemp",
                        return_value=work_d):
            with self.assertRaises(ValueError):
                install.WorkingDir({'install': {'target': target_d}})

    def test_target_dir_by_default_is_under_workd(self):
        """WorkingDir does not require target in config."""
        tmp_d = self.tmp_dir()
        work_d = self.tmp_path("work_d", tmp_d)
        ensure_dir(work_d)
        with mock.patch("curtin.commands.install.tempfile.mkdtemp",
                        return_value=work_d) as m_mkdtemp:
            wd = install.WorkingDir({})
        self.assertEqual(1, m_mkdtemp.call_count)
        self.assertTrue(wd.target.startswith(work_d + "/"))
