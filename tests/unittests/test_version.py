from unittest import TestCase
import mock
import subprocess
import os

from curtin import version
from curtin import __version__ as old_version


class CurtinVersionBase(TestCase):
    def setUp(self):
        super(CurtinVersionBase, self).setUp()

    def add_patch(self, target, attr):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = mock.patch(target, autospec=True)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class TestCurtinVersion(CurtinVersionBase):

    def setUp(self):
        self.add_patch('subprocess.check_output', 'mock_subp')
        self.add_patch('os.path', 'mock_path')

    @mock.patch.object(os, 'getcwd')
    def test_packaged_version(self, mock_getcwd):
        original_pkg_string = version._PACKAGED_VERSION
        test_pkg_version = '9.8.7-curtin-0ubuntu12'
        version._PACKAGED_VERSION = test_pkg_version

        ver_string = version.version_string()

        # check we got the packaged version string set
        self.assertEqual(test_pkg_version, ver_string)
        # make sure we didn't take any other path
        self.assertEqual([], self.mock_path.call_args_list)
        self.assertEqual([], mock_getcwd.call_args_list)
        self.assertEqual([], self.mock_subp.call_args_list)

        version._PACKAGED_VERSION = original_pkg_string

    def test_bzr_revno_version(self):
        self.mock_path.exists.return_value = True
        bzr_revno = "999"
        self.mock_subp.return_value = bzr_revno.encode("utf-8")

        ver_string = version.version_string()
        self.assertEqual(old_version + "~bzr" + bzr_revno, ver_string)

    @mock.patch.object(os, 'getcwd')
    def test_bzr_revno_version_exception(self, mock_getcwd):
        self.mock_path.exists.return_value = True
        mock_getcwd.return_value = "/tmp/foo"
        self.mock_subp.side_effect = subprocess.CalledProcessError(1, 'foo')

        ver_string = version.version_string()
        self.assertEqual(old_version, ver_string)

    def test_dpkg_version_exception(self):
        self.mock_path.exists.return_value = True
        self.mock_subp.side_effect = subprocess.CalledProcessError(1, '')

        ver_string = version.version_string()
        self.assertEqual(old_version, ver_string)

    def test_old_version(self):
        self.mock_path.exists.return_value = False
        self.mock_subp.return_value = "".encode('utf-8')

        ver_string = version.version_string()

        self.assertEqual(old_version, ver_string)


# vi: ts=4 expandtab syntax=python
