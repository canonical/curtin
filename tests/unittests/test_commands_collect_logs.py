from collections import namedtuple
import copy
from datetime import datetime
import json
import mock
import os
from textwrap import dedent

from curtin.commands import collect_logs
from curtin.commands.install import CONFIG_BUILTIN
from curtin.util import ensure_dir, write_file
from .helpers import CiTestCase


# FakeArgs for providing cmdline params to collect_logs_main
FakeArgs = namedtuple('FakeArgs', ['output'])


class TestCollectLogs(CiTestCase):

    def setUp(self):
        super(TestCollectLogs, self).setUp()
        self.new_root = self.tmp_dir()
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.mock_subp.return_value = ('', '')
        self.tmpdir = self.tmp_path('mytemp', _dir=self.new_root)
        ensure_dir(self.tmpdir)  # Create it because we mock mkdtemp
        self.add_patch(
            'tempfile.mkdtemp', 'm_mkdtemp', return_value=self.tmpdir)

    def test_collect_logs_main_works_in_a_temporary_directory(self):
        """collect_logs_main creates its tarfile content within a temp dir.

        That directory is cleaned upon exit. A warning is emitted when using
        builtin configuration.
        """
        myargs = FakeArgs('custom.tar')
        self.add_patch('shutil.rmtree', 'm_rmtree')
        with mock.patch('sys.stderr') as m_stderr:
            with self.assertRaises(SystemExit) as context_manager:
                collect_logs.collect_logs_main(myargs)
        self.assertEqual('0', str(context_manager.exception))
        self.assertEqual(
            [mock.call(self.tmpdir)], self.m_rmtree.call_args_list)
        self.assertIn(mock.call(
            'Warning: no configuration file found in'
            ' /root/curtin-install-cfg.yaml or /curtin/configs.\n'
            'Using builtin configuration.'),
            m_stderr.write.call_args_list)
        self.assertIn(mock.call('Wrote: custom.tar\n'),
                      m_stderr.write.call_args_list)

    def test_collect_logs_main_sources_config_from_save_install_config(self):
        """collect_logs_main uses /root/curtin-install-cfg.yaml config."""
        savefile = self.tmp_path('curtin-install-cfg.log', _dir=self.new_root)
        write_file(savefile, 'install:\n  log_file: /tmp/savefile.log\n')
        packdir = self.tmp_path('configs', _dir=self.new_root)
        ensure_dir(packdir)
        unusedcfg = os.path.join(packdir, 'config-001.yaml')
        write_file(unusedcfg, 'install:\n  log_file: /tmp/unused.log\n')
        utcnow = datetime.utcnow()
        datestr = utcnow.strftime('%Y-%m-%d-%H-%M')
        tardir = self.tmp_path('curtin-logs-%s' % datestr, _dir=self.tmpdir)
        curtin_config = self.tmp_path('curtin-config', _dir=tardir)

        self.assertEqual(
            '/curtin/configs', collect_logs.CURTIN_PACK_CONFIG_DIR)
        self.add_patch(
            'curtin.commands.collect_logs.SAVE_INSTALL_CONFIG', '_idir',
            new=savefile, autospec=None)
        self.add_patch(
            'curtin.commands.collect_logs.CURTIN_PACK_CONFIG_DIR', '_cdir',
            new=packdir, autospec=None)
        self.add_patch('shutil.rmtree', 'm_rmtree')
        with mock.patch('sys.stderr'):
            with mock.patch('curtin.commands.collect_logs.datetime') as m_dt:
                with self.assertRaises(SystemExit) as context_manager:
                    m_dt.utcnow.return_value = utcnow
                    collect_logs.collect_logs_main(FakeArgs('my.tar'))
        self.assertEqual('0', str(context_manager.exception))
        expected_cfg = {'install': {'log_file': '/tmp/savefile.log'}}
        with open(curtin_config, 'r') as f:
            self.assertEqual(expected_cfg, json.loads(f.read()))

    def test_collect_logs_main_sources_config_from_pack_configs(self):
        """collect_logs_main sources all configs from /curtin/configs dir."""
        savefile = self.tmp_path('absentinstall.log', _dir=self.new_root)
        packdir = self.tmp_path('configs', _dir=self.new_root)
        utcnow = datetime.utcnow()
        datestr = utcnow.strftime('%Y-%m-%d-%H-%M')
        tardir = self.tmp_path('curtin-logs-%s' % datestr, _dir=self.tmpdir)
        ensure_dir(packdir)
        cfg1 = os.path.join(packdir, 'config-001.yaml')
        cfg2 = os.path.join(packdir, 'config-002.yaml')
        write_file(cfg1, 'install:\n  log_file: /tmp/my.log\n')
        write_file(cfg2, 'install:\n  post_files: [/tmp/post.log]\n')

        self.assertEqual(
            '/curtin/configs', collect_logs.CURTIN_PACK_CONFIG_DIR)
        self.add_patch(
            'curtin.commands.collect_logs.SAVE_INSTALL_CONFIG', '_idir',
            new=savefile, autospec=None)
        self.add_patch(
            'curtin.commands.collect_logs.CURTIN_PACK_CONFIG_DIR', '_cdir',
            new=packdir, autospec=None)
        self.add_patch('shutil.rmtree', 'm_rmtree')
        with mock.patch('sys.stderr'):
            with mock.patch('curtin.commands.collect_logs.datetime') as m_dt:
                with self.assertRaises(SystemExit) as context_manager:
                    m_dt.utcnow.return_value = utcnow
                    collect_logs.collect_logs_main(FakeArgs('my.tar'))
        self.assertEqual('0', str(context_manager.exception))
        self.assertEqual(['config-001.yaml', 'config-002.yaml'],
                         sorted(os.listdir(packdir)))
        curtin_config = self.tmp_path('curtin-config', _dir=tardir)
        # Config parts are merged with CONFIG_BUILTIN
        expected_cfg = copy.deepcopy(CONFIG_BUILTIN)
        expected_cfg['install'] = {
            'log_file': '/tmp/my.log',
            'post_files': ['/tmp/post.log', '/tmp/my.log'],
            'error_tarfile': '/var/log/curtin/curtin-error-logs.tar'}
        with open(curtin_config, 'r') as f:
            self.assertEqual(expected_cfg, json.loads(f.read()))

    def test_wb_collect_system_info_gets_curtin_version(self):
        """_collect_system_info stores curtin version in target_dir."""
        with mock.patch('curtin.version.version_string') as m_version:
            m_version.return_value = '17.999'
            collect_logs._collect_system_info(self.new_root, config={})
        version = self.tmp_path('version', _dir=self.new_root)
        with open(version, 'r') as f:
            self.assertEqual(f.read(), '17.999')

    def test_wb_collect_system_info_writes_curtin_config(self):
        """_collect_system_info saves curtin config json-formatted."""
        config = {"install": {"log_file": "/var/log/curtin/install.log"},
                  "late_commands": {"builtin": []}}
        collect_logs._collect_system_info(self.new_root, config=config)
        curtin_config = self.tmp_path('curtin-config', _dir=self.new_root)
        with open(curtin_config, 'r') as f:
            self.assertEqual(f.read(),
                             json.dumps(config, indent=1, sort_keys=True,
                                        separators=(',', ': ')))

    def test_wb_collect_system_info_copies_system_files(self):
        """_collect_system_info copies system files into in target_dir.

        Expected files are minimally /etc/os-release, /proc/cmdline and
        /proc/partitions. Since os-release cmdline files are read-only chmod
        copied files 0o644.
        """
        with mock.patch('curtin.commands.collect_logs.os.chmod') as m_chmod:
            with mock.patch('shutil.copy') as m_copy:
                collect_logs._collect_system_info(self.new_root, config={})
        self.assertEqual(
            [mock.call('/etc/os-release', self.new_root),
             mock.call('/proc/cmdline', self.new_root),
             mock.call('/proc/partitions', self.new_root)],
            m_copy.call_args_list)
        for fname in ('os-release', 'cmdline', 'partitions'):
            self.assertIn(
                mock.call(os.path.join(self.new_root, 'os-release'), 0o644),
                m_chmod.call_args_list)

    def test_wb_collect_system_info_writes_lshw(self):
        """_collect_system_info saves lshw details in target_dir."""

        def fake_subp(cmd, capture=False, combine_capture=False):
            if cmd == ['sudo', 'lshw'] and capture:
                return ('lshw output', '')
            return ('', '')

        self.mock_subp.side_effect = fake_subp
        collect_logs._collect_system_info(self.new_root, config={})
        lshw = self.tmp_path('lshw', _dir=self.new_root)
        with open(lshw, 'r') as f:
            self.assertEqual(f.read(), 'lshw output')

    def test_wb_collect_system_info_writes_uname(self):
        """_collect_system_info saves uname details in target_dir."""

        def fake_subp(cmd, capture=False, combine_capture=False):
            if cmd == ['uname', '-a'] and capture:
                return ('Linux myhost 4.4.0-104-generic', '')
            return ('', '')

        self.mock_subp.side_effect = fake_subp
        collect_logs._collect_system_info(self.new_root, config={})
        uname = self.tmp_path('uname', _dir=self.new_root)
        with open(uname, 'r') as f:
            self.assertEqual(f.read(), 'Linux myhost 4.4.0-104-generic')

    def test_wb_collect_system_info_writes_network_info(self):
        """_collect_system_info saves network details in target_dir."""

        ipv4_addr = '1: lo    inet 127.0.0.1/8 scope host lo'
        ipv6_addr = '1: lo    inet6 ::1/128 scope host'
        ipv4_route = 'default via 192.168.2.1 dev wlp3s0'
        ipv6_route = 'fe80::/64 dev lxdbr0  proto kernel'
        expected = dedent("""\
            === ip --oneline address list ===
            {ipv4_addr}
            === ip --oneline -6 address list ===
            {ipv6_addr}
            === ip --oneline route list ===
            {ipv4_route}
            === ip --oneline -6 route list ===
            {ipv6_route}""".format(
                ipv4_addr=ipv4_addr, ipv6_addr=ipv6_addr,
                ipv4_route=ipv4_route, ipv6_route=ipv6_route))

        def fake_subp(cmd, capture=False, combine_capture=False):
            if cmd[0] == 'ip':
                assert combine_capture, (
                    'combine_capture not set for cmd %s' % cmd)
            else:
                assert capture, 'capture not set True for cmd %s' % cmd
            if cmd == ['ip', '--oneline', 'address', 'list']:
                return ipv4_addr, ''
            if cmd == ['ip', '--oneline', '-6', 'address', 'list']:
                return ipv6_addr, ''
            if cmd == ['ip', '--oneline', 'route', 'list']:
                return ipv4_route, ''
            if cmd == ['ip', '--oneline', '-6', 'route', 'list']:
                return ipv6_route, ''
            return ('', '')

        self.mock_subp.side_effect = fake_subp
        collect_logs._collect_system_info(self.new_root, config={})
        network = self.tmp_path('network', _dir=self.new_root)
        with open(network, 'r') as f:
            self.assertEqual(f.read(), expected)


class TestCreateTar(CiTestCase):
    """Whitebox testing of create_log_tarfile."""

    def setUp(self):
        super(TestCreateTar, self).setUp()
        self.new_root = self.tmp_dir()
        self.utcnow = datetime.utcnow()
        self.tardir = 'curtin-logs-%s' % self.utcnow.strftime('%Y-%m-%d-%H-%M')
        self.add_patch(
            'curtin.commands.collect_logs._collect_system_info', 'm_sys_info')
        self.tmpdir = self.tmp_path('mytemp', _dir=self.new_root)
        ensure_dir(self.tmpdir)  # Create it because we mock mkdtemp
        self.add_patch(
            'tempfile.mkdtemp', 'm_mkdtemp', return_value=self.tmpdir)

    def test_create_log_tarfile_stores_logs_in_dated_subdirectory(self):
        """create_log_tarfile creates a dated subdir in the created tarfile."""
        tarfile = self.tmp_path('my.tar', _dir=self.new_root)
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.mock_subp.return_value = ('', '')
        with mock.patch('sys.stderr'):
            with mock.patch('curtin.commands.collect_logs.datetime') as m_dt:
                m_dt.utcnow.return_value = self.utcnow
                collect_logs.create_log_tarfile(tarfile, config={})
        self.assertIn(
            mock.call(['tar', '-cvf', tarfile, self.tardir],
                      capture=True),
            self.mock_subp.call_args_list)
        self.m_sys_info.assert_called_with(self.tardir, {})

    def test_create_log_tarfile_creates_target_tar_directory_if_absent(self):
        """create_log_tarfile makes the tarfile's directory if needed."""
        tarfile = self.tmp_path('my.tar',
                                _dir=os.path.join(self.new_root, 'dont/exist'))
        destination_dir = os.path.dirname(tarfile)
        self.assertFalse(os.path.exists(destination_dir),
                         'Expected absent directory: %s' % destination_dir)
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.mock_subp.return_value = ('', '')
        with mock.patch('sys.stderr'):
            with mock.patch('curtin.commands.collect_logs.datetime') as m_dt:
                m_dt.utcnow.return_value = self.utcnow
                collect_logs.create_log_tarfile(tarfile, config={})
        self.assertIn(
            mock.call(['tar', '-cvf', tarfile, self.tardir],
                      capture=True),
            self.mock_subp.call_args_list)
        self.m_sys_info.assert_called_with(self.tardir, {})
        self.assertTrue(os.path.exists(destination_dir),
                        'Expected directory created: %s' % destination_dir)

    def test_create_log_tarfile_copies_configured_logs(self):
        """create_log_tarfile copies configured log_file and post_files.

        Configured log_file or post_files which don't exist are ignored.
        """
        tarfile = self.tmp_path('my.tar', _dir=self.new_root)
        log1 = self.tmp_path('some.log', _dir=self.new_root)
        write_file(log1, 'log content')
        log2 = self.tmp_path('log2.log', _dir=self.new_root)
        write_file(log2, 'log2 content')
        absent_log = self.tmp_path('log3.log', _dir=self.new_root)
        config = {
            'install': {'log_file': log1, 'post_files': [log2, absent_log]}}
        self.add_patch('shutil.copy', 'm_copy')
        with mock.patch('sys.stderr') as m_stderr:
            collect_logs.create_log_tarfile(tarfile, config=config)
        self.assertIn(
            mock.call(
                'Skipping logfile %s: file does not exist\n' % absent_log),
            m_stderr.write.call_args_list)
        self.assertIn(
            mock.call(log1, self.tardir), self.m_copy.call_args_list)
        self.assertIn(
            mock.call(log2, self.tardir), self.m_copy.call_args_list)
        self.assertNotIn(
            mock.call(absent_log, self.tardir), self.m_copy.call_args_list)

    def test_create_log_tarfile_redacts_maas_credentials(self):
        """create_log_tarfile redacts sensitive maas credentials configured."""
        tarfile = self.tmp_path('my.tar', _dir=self.new_root)
        self.add_patch(
            'curtin.commands.collect_logs._redact_sensitive_information',
            'm_redact')
        config = {
            'install': {
                'maas': {'consumer_key': 'ckey',
                         'token_key': 'tkey', 'token_secret': 'tsecret'}}}
        with mock.patch('sys.stderr'):
            with mock.patch('curtin.commands.collect_logs.datetime') as m_dt:
                m_dt.utcnow.return_value = self.utcnow
                collect_logs.create_log_tarfile(tarfile, config=config)
        self.assertEqual(
            [mock.call(self.tardir, ['ckey', 'tkey', 'tsecret'])],
            self.m_redact.call_args_list)
        self.m_sys_info.assert_called_with(self.tardir, config)


class TestWBCollectLogs(CiTestCase):
    """Whitebox testing of _redact_sensitive_information."""

    def test_wb_redact_sensitive_information(self):
        """_redact_sensitive_information replaces redact_values in any file."""
        new_root = self.tmp_dir()
        tmpdir = self.tmp_path('subdir', _dir=new_root)
        file1 = self.tmp_path('file1', _dir=new_root)
        file2 = self.tmp_path('file2', _dir=tmpdir)
        write_file(file1, 'blahsekretblah')
        write_file(file2, 'hip@sswordmom')
        collect_logs._redact_sensitive_information(
            target_dir=new_root, redact_values=('sekret', 'p@ssword'))
        with open(file1, 'r') as f:
            self.assertEqual('blah<REDACTED>blah', f.read())
        with open(file2, 'r') as f:
            self.assertEqual('hi<REDACTED>mom', f.read())
