# This file is part of curtin. See LICENSE file for copyright and license info.

import os
from pathlib import Path
import tempfile

from .helpers import CiTestCase

from curtin import config
from curtin.commands import install_bls


USE_BLS = ['bls']
ROOT_DEV = '/dev/sda1'
MACHINE = 'x86_64'


class TestInstallBls(CiTestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(suffix='-curtin')
        self.target = self.tmpdir.name

        versions = ['6.8.0-40', '5.15.0-127', '6.8.0-48']
        boot = os.path.join(self.target, 'boot')
        Path(f'{boot}').mkdir()
        for ver in versions:
            Path(f'{boot}/config-{ver}-generic').touch()
            Path(f'{boot}/initrd.img-{ver}-generic').touch()
            Path(f'{boot}/vmlinuz-{ver}-generic').touch()

        # Create /etc/machine-id in target
        etc = os.path.join(self.target, 'etc')
        Path(etc).mkdir()
        with open(os.path.join(etc, 'machine-id'), 'w') as f:
            f.write('abc123\n')

        Path(f'{self.target}/empty-dir').mkdir()
        self.maxDiff = None

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_loader_conf(self):
        """loader.conf should contain a timeout"""
        out = install_bls.build_loader_conf()
        self.assertIn('timeout 50', out)

    def test_loader_conf_custom_timeout(self):
        """loader.conf should accept a custom timeout"""
        out = install_bls.build_loader_conf(timeout=10)
        self.assertIn('timeout 10', out)

    def test_entry_default(self):
        """A default entry should have quiet option"""
        out = install_bls.build_entry(
            '/boot', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV)
        self.assertIn('title Linux 6.8.0-48-generic\n', out)
        self.assertIn('version 6.8.0-48-generic\n', out)
        self.assertIn('linux /boot/vmlinuz-6.8.0-48-generic\n', out)
        self.assertIn(
            'initrd /boot/initrd.img-6.8.0-48-generic\n', out)
        self.assertIn(
            f'options root={ROOT_DEV} ro quiet\n', out)
        self.assertNotIn('single', out)

    def test_entry_machine_id(self):
        """An entry should include machine-id when provided"""
        out = install_bls.build_entry(
            '/boot', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV, machine_id='abc123')
        self.assertIn('machine-id abc123\n', out)

    def test_entry_architecture(self):
        """An entry should include architecture when provided"""
        out = install_bls.build_entry(
            '/boot', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV, architecture='x86-64')
        self.assertIn('architecture x86-64\n', out)

    def test_entry_no_machine_id(self):
        """An entry should omit machine-id when not provided"""
        out = install_bls.build_entry(
            '/boot', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV)
        self.assertNotIn('machine-id', out)

    def test_entry_rescue(self):
        """A rescue entry should have single and no quiet"""
        out = install_bls.build_entry(
            '/boot', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV, rescue=True)
        self.assertIn('(rescue target)', out)
        self.assertIn(
            f'options root={ROOT_DEV} ro single\n', out)
        self.assertNotIn('quiet', out)

    def test_entry_separate_boot(self):
        """Separate /boot partition uses empty fw_boot_dir"""
        out = install_bls.build_entry(
            '', 'vmlinuz-6.8.0-48-generic',
            'initrd.img-6.8.0-48-generic',
            '6.8.0-48-generic', ROOT_DEV)
        self.assertIn('linux /vmlinuz-6.8.0-48-generic\n', out)
        self.assertIn(
            'initrd /initrd.img-6.8.0-48-generic\n', out)

    def test_build_entries_empty(self):
        """No kernels should produce no entries"""
        entries = install_bls.build_entries(
            config.BootCfg(USE_BLS),
            f'{self.target}/empty-dir', '', ROOT_DEV, MACHINE)
        self.assertEqual([], entries)

    def test_build_entries_normal(self):
        """Normal config should produce default and rescue entries"""
        entries = install_bls.build_entries(
            config.BootCfg(USE_BLS),
            self.target, '/boot', ROOT_DEV, MACHINE)
        # 3 kernels * 2 alternatives = 6 entries
        self.assertEqual(6, len(entries))
        fnames = [e[0] for e in entries]
        self.assertIn('l0-6.8.0-48-generic.conf', fnames)
        self.assertIn('l0r-6.8.0-48-generic.conf', fnames)
        self.assertIn('l1-6.8.0-40-generic.conf', fnames)
        self.assertIn('l2-5.15.0-127-generic.conf', fnames)
        # Check machine-id and architecture are present
        content = entries[0][1]
        self.assertIn('machine-id abc123\n', content)
        self.assertIn('architecture ', content)

    def test_build_entries_no_rescue(self):
        """Config without rescue should only produce default entries"""
        cfg = config.BootCfg(USE_BLS, alternatives=['default'])
        entries = install_bls.build_entries(
            cfg, self.target, '/boot', ROOT_DEV, MACHINE)
        self.assertEqual(3, len(entries))
        fnames = [e[0] for e in entries]
        self.assertNotIn('l0r-6.8.0-48-generic.conf', fnames)

    def test_build_entries_no_default(self):
        """Config without default should only produce rescue entries"""
        cfg = config.BootCfg(USE_BLS, alternatives=['rescue'])
        entries = install_bls.build_entries(
            cfg, self.target, '/boot', ROOT_DEV, MACHINE)
        self.assertEqual(3, len(entries))
        fnames = [e[0] for e in entries]
        self.assertIn('l0r-6.8.0-48-generic.conf', fnames)
        self.assertNotIn('l0-6.8.0-48-generic.conf', fnames)

    def test_install(self):
        """Install should create loader.conf and entry files"""
        bootcfg = config.BootCfg(USE_BLS)
        install_bls.install_bls(
            bootcfg, self.target, '/boot', ROOT_DEV, MACHINE)

        loader_conf = os.path.join(
            self.target, 'boot/loader/loader.conf')
        self.assertTrue(os.path.exists(loader_conf))

        entries_dir = os.path.join(
            self.target, 'boot/loader/entries')
        self.assertTrue(os.path.isdir(entries_dir))

        entry_files = sorted(os.listdir(entries_dir))
        self.assertEqual(6, len(entry_files))
        self.assertIn('l0-6.8.0-48-generic.conf', entry_files)

    def test_install_separate_boot(self):
        """Install with separate /boot should use empty fw_boot_dir"""
        bootcfg = config.BootCfg(USE_BLS)
        install_bls.install_bls(
            bootcfg, self.target, '', ROOT_DEV, MACHINE)

        entry_path = os.path.join(
            self.target,
            'boot/loader/entries/l0-6.8.0-48-generic.conf')
        with open(entry_path) as f:
            content = f.read()
        self.assertIn('linux /vmlinuz-6.8.0-48-generic', content)
