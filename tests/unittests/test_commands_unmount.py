# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.commands import unmount
from curtin.util import FileMissingError
from .helpers import CiTestCase

import argparse
import mock
import os


class TestUnmount(CiTestCase):

    def setUp(self):
        super(TestUnmount, self).setUp()
        self.args = argparse.Namespace()
        self.args.target = os.environ.get('TEST_CURTIN_TARGET_MOUNT_POINT')
        self.args.disable_recursive_mounts = False
        self.add_patch('curtin.util.do_umount', 'm_umount')

    def test_unmount_notarget_raises_exception(self):
        """Check missing target raises ValueError exception"""
        self.assertRaises(ValueError, unmount.unmount_main, self.args)

    def test_unmount_target_not_found_exception(self):
        """Check target path not found raises FileNotFoundError exception"""
        self.args.target = "catch-me-if-you-can"
        self.assertRaises(FileMissingError, unmount.unmount_main, self.args)

    @mock.patch('curtin.commands.unmount.os')
    def test_unmount_target_with_path(self, mock_os):
        """Assert do_umount is called with args.target and recursive=True"""
        self.args.target = "test/path/to/my/path"
        mock_os.path.exists.return_value = True
        unmount.unmount_main(self.args)
        self.m_umount.assert_called_with(self.args.target, recursive=True)

    @mock.patch('curtin.commands.unmount.os')
    def test_unmount_target_with_path_no_recursive(self, mock_os):
        """Assert args.disable_recursive_mounts True sends recursive=False"""
        self.args.target = "test/path/to/my/path"
        self.args.disable_recursive_mounts = True
        mock_os.path.exists.return_value = True
        unmount.unmount_main(self.args)
        self.m_umount.assert_called_with(self.args.target, recursive=False)

# vi: ts=4 expandtab syntax=python
