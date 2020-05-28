# This file is part of curtin. See LICENSE file for copyright and license info.

from mock import call, patch
import textwrap

from curtin import gpg
from curtin import util
from .helpers import CiTestCase


class TestCurtinGpg(CiTestCase):

    @patch('curtin.util.subp')
    def test_export_armour(self, mock_subp):
        key = 'DEADBEEF'
        expected_armour = textwrap.dedent("""
        -----BEGIN PGP PUBLIC KEY BLOCK-----
        Version: GnuPG v1

        deadbeef
        -----END PGP PUBLIC KEY BLOCK----
        """)
        mock_subp.side_effect = iter([(expected_armour, "")])

        armour = gpg.export_armour(key)
        mock_subp.assert_called_with(["gpg", "--export", "--armour", key],
                                     capture=True)
        self.assertEqual(expected_armour, armour)

    @patch('curtin.util.subp')
    def test_export_armour_missingkey(self, mock_subp):
        key = 'DEADBEEF'
        mock_subp.side_effect = iter([util.ProcessExecutionError()])

        expected_armour = gpg.export_armour(key)
        mock_subp.assert_called_with(["gpg", "--export", "--armour", key],
                                     capture=True)
        self.assertEqual(None, expected_armour)

    @patch('curtin.util.subp')
    def test_recv_key(self, mock_subp):
        key = 'DEADBEEF'
        keyserver = 'keyserver.ubuntu.com'
        mock_subp.side_effect = iter([("", "")])

        gpg.recv_key(key, keyserver)
        mock_subp.assert_called_with(["gpg", "--keyserver", keyserver,
                                      "--recv", key], capture=True,
                                     retries=None)

    @patch('curtin.util.subp')
    def test_delete_key(self, mock_subp):
        key = 'DEADBEEF'
        mock_subp.side_effect = iter([("", "")])

        gpg.delete_key(key)
        mock_subp.assert_called_with(["gpg", "--batch", "--yes",
                                      "--delete-keys", key], capture=True)

    @patch('curtin.gpg.delete_key')
    @patch('curtin.gpg.recv_key')
    @patch('curtin.gpg.export_armour')
    def test_getkeybyid(self, mock_export, mock_recv, mock_del):
        key = 'DEADBEEF'
        keyserver = 'my.keyserver.xyz.co.uk'

        mock_export.side_effect = iter([
            None,
            "-----BEGIN PGP PUBLIC KEY BLOCK-----",
        ])

        gpg.getkeybyid(key, keyserver=keyserver)

        mock_export.assert_has_calls([call(key), call(key)])
        mock_recv.assert_has_calls([
            call(key, keyserver=keyserver, retries=None)])
        mock_del.assert_has_calls([call(key)])

    @patch('curtin.gpg.delete_key')
    @patch('curtin.gpg.recv_key')
    @patch('curtin.gpg.export_armour')
    def test_getkeybyid_exists(self, mock_export, mock_recv, mock_del):
        key = 'DEADBEEF'

        mock_export.side_effect = iter([
            "-----BEGIN PGP PUBLIC KEY BLOCK-----",
        ])

        gpg.getkeybyid(key)

        mock_export.assert_has_calls([call(key)])
        self.assertEqual([], mock_recv.call_args_list)
        self.assertEqual([], mock_del.call_args_list)

    @patch('curtin.gpg.delete_key')
    @patch('curtin.gpg.recv_key')
    @patch('curtin.gpg.export_armour')
    def test_getkeybyid_raises(self, mock_export, mock_recv, mock_del):
        key = 'DEADBEEF'
        keyserver = 'my.keyserver.xyz.co.uk'

        mock_export.side_effect = iter([
            None,
            "-----BEGIN PGP PUBLIC KEY BLOCK-----",
        ])
        mock_recv.side_effect = iter([
            ValueError("Failed to import key %s from server %s" %
                       (key, keyserver)),
        ])

        with self.assertRaises(ValueError):
            gpg.getkeybyid(key, keyserver=keyserver)

        mock_export.assert_has_calls([call(key)])
        mock_recv.assert_has_calls([
            call(key, keyserver=keyserver, retries=None)])
        mock_del.assert_has_calls([call(key)])


class TestCurtinGpgSubp(TestCurtinGpg):

    allowed_subp = True

    @patch('time.sleep')
    @patch('curtin.util._subp')
    def test_recv_key_retry_raises(self, mock_under_subp, mock_sleep):
        key = 'DEADBEEF'
        keyserver = 'keyserver.ubuntu.com'
        retries = (1, 2, 5, 10)
        nr_calls = 5
        mock_under_subp.side_effect = iter([
            util.ProcessExecutionError()] * nr_calls)

        with self.assertRaises(ValueError):
            gpg.recv_key(key, keyserver, retries=retries)

        print("_subp calls: %s" % mock_under_subp.call_args_list)
        print("sleep calls: %s" % mock_sleep.call_args_list)
        expected_calls = nr_calls * [
            call(["gpg", "--keyserver", keyserver, "--recv", key],
                 capture=True)]
        mock_under_subp.assert_has_calls(expected_calls)

        expected_calls = [call(1), call(2), call(5), call(10)]
        mock_sleep.assert_has_calls(expected_calls)

    @patch('time.sleep')
    @patch('curtin.util._subp')
    def test_recv_key_retry_works(self, mock_under_subp, mock_sleep):
        key = 'DEADBEEF'
        keyserver = 'keyserver.ubuntu.com'
        nr_calls = 2
        mock_under_subp.side_effect = iter([
            util.ProcessExecutionError(),  # 1
            ("", ""),
        ])

        gpg.recv_key(key, keyserver, retries=[1])

        print("_subp calls: %s" % mock_under_subp.call_args_list)
        print("sleep calls: %s" % mock_sleep.call_args_list)
        expected_calls = nr_calls * [
            call(["gpg", "--keyserver", keyserver, "--recv", key],
                 capture=True)]
        mock_under_subp.assert_has_calls(expected_calls)
        mock_sleep.assert_has_calls([call(1)])


# vi: ts=4 expandtab syntax=python
