# This file is part of curtin. See LICENSE file for copyright and license info.

from unittest import mock

from curtin import compat
from .helpers import CiTestCase


class TestUtilLinuxVer(CiTestCase):
    @mock.patch('curtin.util.subp')
    def test_ul_ver(self, m_subp):
        m_subp.return_value = ('losetup from util-linux 2.31.1', '')
        self.assertEqual('2.31.1', compat._get_util_linux_ver())

    @mock.patch('curtin.util.subp')
    def test_ul_malformed(self, m_subp):
        m_subp.return_value = ('losetup from util-linux asdf', '')
        self.assertEqual(None, compat._get_util_linux_ver())

    @mock.patch('curtin.compat._get_util_linux_ver')
    def test_verpass(self, m_gulv):
        m_gulv.return_value = '1.23.4'
        self.assertTrue(compat._check_util_linux_ver('1.20'))

    @mock.patch('curtin.compat._get_util_linux_ver')
    def test_verfail(self, m_gulv):
        m_gulv.return_value = '1.23.4'
        self.assertFalse(compat._check_util_linux_ver('1.24'))

    @mock.patch('curtin.compat._get_util_linux_ver')
    def test_verfatal(self, m_gulv):
        m_gulv.return_value = '1.23.4'
        with self.assertRaisesRegex(RuntimeError, '.*my feature.*'):
            compat._check_util_linux_ver('1.24', 'my feature', fatal=True)
