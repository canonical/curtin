from unittest import TestCase
import mock
import shutil
import tempfile

from curtin.commands import curthooks


class CurthooksBase(TestCase):
    def setUp(self):
        super(CurthooksBase, self).setUp()

    def add_patch(self, target, attr):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = mock.patch(target, autospec=True)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class TestCurthooksInstallKernel(CurthooksBase):

    def setUp(self):
        super(TestCurthooksInstallKernel, self).setUp()
        self.add_patch('curtin.util.has_pkg_available', 'mock_haspkg')
        self.add_patch('os.uname', 'mock_uname')
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.add_patch('curtin.util.install_packages', 'mock_instpkg')
        self.add_patch('curtin.util.get_architecture', 'mock_getarch')
        self.add_patch('curtin.util.is_uefi_bootable', 'mock_isuefi')

        self.kernel_cfg = {'kernel': {'package': 'mock-linux-kernel',
                                      'fallback-package': 'mock-fallback',
                                      'mapping': {}}}
        self.target = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_install_kernel_flash_kernel(self):
        required_packages = "foobar"
        kernel_package = self.kernel_cfg.get('kernel', {}).get('package', {})

        self.mock_isuefi.return_value = False
        self.mock_getarch.return_value = 'arm64'
        self.mock_instpkg.return_value = ("", "")
        self.mock_subp.side_effect = [
            (required_packages, ""),
            ("subp second", ""),
        ]
        curthooks.install_kernel(self.kernel_cfg, self.target)

        print('isuefi calls: %s' % self.mock_isuefi.mock_calls)
        self.mock_isuefi.assert_called_with()

        print('getarch calls: %s' % self.mock_getarch.mock_calls)
        self.mock_getarch.assert_called_with()

        # 1) install flash-kernel
        # 2) install required_packages
        # 3) install kernel_cfg.get('package')
        print('install_pkgs calls:\n%s' % self.mock_instpkg.mock_calls)
        inst_calls = [
            mock.call(['flash-kernel'], target="/"),  # install to ephemeral
            mock.call(['flash-kernel', required_packages],
                      target=self.target),  # required_packages install
            mock.call([kernel_package], target=self.target)]

        self.mock_instpkg.assert_has_calls(inst_calls)

        print('subp calls: %s' % self.mock_subp.mock_calls)
        self.assertTrue(self.mock_subp.called)

# vi: ts=4 expandtab syntax=python
