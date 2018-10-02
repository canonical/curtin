# This file is part of curtin. See LICENSE file for copyright and license info.

import mock
import os

from curtin.block import iscsi
from curtin import util
from .helpers import CiTestCase


class TestBlockIscsiPortalParsing(CiTestCase):

    def test_iscsi_portal_parsing_string(self):
        with self.assertRaisesRegexp(ValueError, 'not a string'):
            iscsi.assert_valid_iscsi_portal(1234)

    def test_iscsi_portal_parsing_no_port(self):
        # port must be specified
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('192.168.1.12')
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('fe80::a634:d9ff:fe40:768a')
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('192.168.1.12:')
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('test.example.com:')

    def test_iscsi_portal_parsing_valid_ip(self):
        # IP must be in [] for IPv6, if not we misparse
        host, port = iscsi.assert_valid_iscsi_portal(
            'fe80::a634:d9ff:fe40:768a:9999')
        self.assertEquals(host, 'fe80::a634:d9ff:fe40:768a')
        self.assertEquals(port, 9999)
        # IP must not be in [] if port is specified for IPv4
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv6 address'):
            iscsi.assert_valid_iscsi_portal('[192.168.1.12]:9000')
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv6 address'):
            iscsi.assert_valid_iscsi_portal('[test.example.com]:8000')

    def test_iscsi_portal_parsing_ip(self):
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv6 address'):
            iscsi.assert_valid_iscsi_portal(
                '[1200::AB00:1234::2552:7777:1313]:9999')
        # cannot distinguish between bad IP and bad hostname
        host, port = iscsi.assert_valid_iscsi_portal('192.168:9000')
        self.assertEquals(host, '192.168')
        self.assertEquals(port, 9000)

    def test_iscsi_portal_parsing_port(self):
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('192.168.1.12:ABCD')
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('[fe80::a634:d9ff:fe40:768a]:ABCD')
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('test.example.com:ABCD')

    def test_iscsi_portal_parsing_good_portals(self):
        host, port = iscsi.assert_valid_iscsi_portal('192.168.1.12:9000')
        self.assertEquals(host, '192.168.1.12')
        self.assertEquals(port, 9000)

        host, port = iscsi.assert_valid_iscsi_portal(
            '[fe80::a634:d9ff:fe40:768a]:9999')
        self.assertEquals(host, 'fe80::a634:d9ff:fe40:768a')
        self.assertEquals(port, 9999)

        host, port = iscsi.assert_valid_iscsi_portal('test.example.com:8000')
        self.assertEquals(host, 'test.example.com')
        self.assertEquals(port, 8000)

    # disk specification:
    # TARGETSPEC=host:proto:port:lun:targetname
    # root=iscsi:$TARGETSPEC
    # root=iscsi:user:password@$TARGETSPEC
    # root=iscsi:user:password:initiatoruser:initiatorpassword@$TARGETSPEC
    def test_iscsi_disk_basic(self):
        with self.assertRaisesRegexp(ValueError, 'must be specified'):
            iscsi.IscsiDisk('')

        # typo
        with self.assertRaisesRegexp(ValueError, 'must be specified'):
            iscsi.IscsiDisk('iscs:')

        # no specification
        with self.assertRaisesRegexp(ValueError, 'must be specified'):
            iscsi.IscsiDisk('iscsi:')
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:::::')

    def test_iscsi_disk_ip_valid(self):
        # these are all misparses we cannot catch trivially
        i = iscsi.IscsiDisk('iscsi:192.168::::target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:[fe80::]::::target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:test.example::::target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'target')

    def test_iscsi_disk_port(self):
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:192.168.1.12::ABCD::target')
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:[fe80::a634:d9ff:fe40:768a:6]::ABCD::'
                            'target')
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:test.example.com::ABCD::target')

    def test_iscsi_disk_target(self):
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:192.168.1.12::::')
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:[fe80::a634:d9ff:fe40:768a:6]::::')
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:test.example.com::::')

    def test_iscsi_disk_ip(self):
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:::::target')

    def test_iscsi_disk_auth(self):
        # user without password
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@192.168.1.12::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@[fe80::a634:d9ff:fe40:768a:6]::::'
                            'target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@test.example.com::::target')

        # iuser without password
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@192.168.1.12::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@'
                            '[fe80::a634:d9ff:fe40:768a:6]::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk(
                'iscsi:user:password:iuser@test.example.com::::target')

    def test_iscsi_disk_good_ipv4(self):
        i = iscsi.IscsiDisk('iscsi:192.168.1.12:6:3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:192.168.1.12::3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:192.168.1.12:::1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                            '192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, 'ipassword')
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:@'
                            '192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user::iuser:@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

    def test_iscsi_disk_good_ipv6(self):
        i = iscsi.IscsiDisk(
            'iscsi:[fe80::a634:d9ff:fe40:768a:6]:5:3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk(
            'iscsi:[fe80::a634:d9ff:fe40:768a:6]::3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password@'
                            '[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:@'
                            '[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                            '[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, 'ipassword')
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:@'
                            '[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user::iuser:@'
                            '[fe80::a634:d9ff:fe40:768a:6]:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

    def test_iscsi_disk_good_hostname(self):
        i = iscsi.IscsiDisk('iscsi:test.example.com:6:3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:test.example.com::3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:test.example.com:::1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password@test.example.com:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:@test.example.com:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                            'test.example.com:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, 'ipassword')
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:@'
                            'test.example.com:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user::iuser:@test.example.com:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

    # LP: #1679222
    def test_iscsi_target_parsing(self):
        i = iscsi.IscsiDisk(
            'iscsi:192.168.1.12::::iqn.2017-04.com.example.test:target-name')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'iqn.2017-04.com.example.test:target-name')

        i = iscsi.IscsiDisk(
            'iscsi:[fe80::a634:d9ff:fe40:768a:6]::::'
            'iqn.2017-04.com.example.test:target-name')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'iqn.2017-04.com.example.test:target-name')

        i = iscsi.IscsiDisk(
            'iscsi:test.example.com::::'
            'iqn.2017-04.com.example.test:target-name')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'test.example.com')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 0)
        self.assertEquals(i.target, 'iqn.2017-04.com.example.test:target-name')


class TestBlockIscsiVolPath(CiTestCase):
    # non-iscsi backed disk returns false
    # regular iscsi-backed disk returns true
    # layered setup without an iscsi member returns false
    # layered setup with an iscsi member returns true

    def setUp(self):
        super(TestBlockIscsiVolPath, self).setUp()
        self.add_patch('curtin.block.iscsi.get_device_slave_knames',
                       'mock_get_device_slave_knames')
        self.add_patch('curtin.block.iscsi.path_to_kname',
                       'mock_path_to_kname')
        self.add_patch('curtin.block.iscsi.kname_is_iscsi',
                       'mock_kname_is_iscsi')

    def test_volpath_is_iscsi_false(self):
        volume_path = '/dev/wark'
        kname = 'wark'
        slaves = []
        self.mock_get_device_slave_knames.return_value = slaves
        self.mock_path_to_kname.return_value = kname
        self.mock_kname_is_iscsi.return_value = 'iscsi' in kname

        is_iscsi = iscsi.volpath_is_iscsi(volume_path)

        self.assertFalse(is_iscsi)
        self.mock_get_device_slave_knames.assert_called_with(volume_path)
        self.mock_path_to_kname.assert_called_with(volume_path)
        self.mock_kname_is_iscsi.assert_called_with(kname)

    def test_volpath_is_iscsi_true(self):
        volume_path = '/dev/wark'
        kname = 'wark-iscsi-lun-2'
        slaves = []
        self.mock_get_device_slave_knames.return_value = slaves
        self.mock_path_to_kname.return_value = kname
        self.mock_kname_is_iscsi.return_value = 'iscsi' in kname

        is_iscsi = iscsi.volpath_is_iscsi(volume_path)

        self.assertTrue(is_iscsi)
        self.mock_get_device_slave_knames.assert_called_with(volume_path)
        self.mock_path_to_kname.assert_called_with(volume_path)
        self.mock_kname_is_iscsi.assert_called_with(kname)

    def test_volpath_is_iscsi_layered_true(self):
        volume_path = '/dev/wark'
        slaves = ['wark', 'bzoink', 'super-iscsi-lun-27']
        self.mock_get_device_slave_knames.return_value = slaves
        self.mock_path_to_kname.side_effect = lambda x: x
        self.mock_kname_is_iscsi.side_effect = lambda x: 'iscsi' in x

        is_iscsi = iscsi.volpath_is_iscsi(volume_path)

        self.assertTrue(is_iscsi)
        self.mock_get_device_slave_knames.assert_called_with(volume_path)
        self.mock_path_to_kname.assert_called_with(volume_path)
        self.mock_kname_is_iscsi.assert_has_calls([
            mock.call(x) for x in slaves])

    def test_volpath_is_iscsi_layered_false(self):
        volume_path = '/dev/wark'
        slaves = ['wark', 'bzoink', 'nvmen27p47']
        self.mock_get_device_slave_knames.return_value = slaves
        self.mock_path_to_kname.side_effect = lambda x: x
        self.mock_kname_is_iscsi.side_effect = lambda x: 'iscsi' in x

        is_iscsi = iscsi.volpath_is_iscsi(volume_path)

        self.assertFalse(is_iscsi)
        self.mock_get_device_slave_knames.assert_called_with(volume_path)
        self.mock_path_to_kname.assert_called_with(volume_path)
        self.mock_kname_is_iscsi.assert_has_calls([
            mock.call(x) for x in slaves])

    def test_volpath_is_iscsi_missing_param(self):
        with self.assertRaises(ValueError):
            iscsi.volpath_is_iscsi(None)


class TestBlockIscsiDiskFromConfig(CiTestCase):
    # Test iscsi parsing of storage config for iscsi configure disks

    def setUp(self):
        super(TestBlockIscsiDiskFromConfig, self).setUp()
        self.add_patch('curtin.block.iscsi.util.subp', 'mock_subp')

    def test_parse_iscsi_disk_from_config(self):
        """Test parsing iscsi volume path creates the same iscsi disk"""
        target = 'curtin-659d5f45-4f23-46cb-b826-f2937b896e09'
        iscsi_path = 'iscsi:10.245.168.20::20112:1:' + target
        cfg = {
            'storage': {
                'config': [{'type': 'disk',
                            'id': 'iscsidev1',
                            'path': iscsi_path,
                            'name': 'iscsi_disk1',
                            'ptable': 'msdos',
                            'wipe': 'superblock'}]
                }
        }
        expected_iscsi_disk = iscsi.IscsiDisk(iscsi_path)
        iscsi_disk = iscsi.get_iscsi_disks_from_config(cfg).pop()
        # utilize IscsiDisk str method for equality check
        self.assertEqual(str(expected_iscsi_disk), str(iscsi_disk))

        # test with cfg.get('storage') since caller may already have
        # grabbed the 'storage' value from the curtin config
        iscsi_disk = iscsi.get_iscsi_disks_from_config(
                        cfg.get('storage')).pop()
        # utilize IscsiDisk str method for equality check
        self.assertEqual(str(expected_iscsi_disk), str(iscsi_disk))

    def test_parse_iscsi_disk_from_config_no_iscsi(self):
        """Test parsing storage config with no iscsi disks included"""
        cfg = {
            'storage': {
                'config': [{'type': 'disk',
                            'id': 'ssd1',
                            'path': 'dev/slash/foo1',
                            'name': 'the-fast-one',
                            'ptable': 'gpt',
                            'wipe': 'superblock'}]
                }
        }
        expected_iscsi_disks = []
        iscsi_disks = iscsi.get_iscsi_disks_from_config(cfg)
        self.assertEqual(expected_iscsi_disks, iscsi_disks)

    def test_parse_iscsi_disk_from_config_invalid_iscsi(self):
        """Test parsing storage config with no iscsi disks included"""
        cfg = {
            'storage': {
                'config': [{'type': 'disk',
                            'id': 'iscsidev2',
                            'path': 'iscsi:garbage',
                            'name': 'noob-city',
                            'ptable': 'msdos',
                            'wipe': 'superblock'}]
                }
        }
        with self.assertRaises(ValueError):
            iscsi.get_iscsi_disks_from_config(cfg)

    def test_parse_iscsi_disk_from_config_empty(self):
        """Test parse_iscsi_disks handles empty/invalid config"""
        expected_iscsi_disks = []
        iscsi_disks = iscsi.get_iscsi_disks_from_config({})
        self.assertEqual(expected_iscsi_disks, iscsi_disks)

        cfg = {'storage': {'config': []}}
        iscsi_disks = iscsi.get_iscsi_disks_from_config(cfg)
        self.assertEqual(expected_iscsi_disks, iscsi_disks)

    def test_parse_iscsi_disk_from_config_none(self):
        """Test parse_iscsi_disks handles no config"""
        expected_iscsi_disks = []
        iscsi_disks = iscsi.get_iscsi_disks_from_config({})
        self.assertEqual(expected_iscsi_disks, iscsi_disks)

        cfg = None
        iscsi_disks = iscsi.get_iscsi_disks_from_config(cfg)
        self.assertEqual(expected_iscsi_disks, iscsi_disks)


class TestBlockIscsiDisconnect(CiTestCase):
    # test that when disconnecting iscsi targets we
    # check that the target has an active session before
    # issuing a disconnect command

    def setUp(self):
        super(TestBlockIscsiDisconnect, self).setUp()
        self.add_patch('curtin.block.iscsi.util.subp', 'mock_subp')
        self.add_patch('curtin.block.iscsi.iscsiadm_sessions',
                       'mock_iscsi_sessions')
        # fake target_root + iscsi nodes dir
        self.target_path = self.tmp_dir()
        self.iscsi_nodes = os.path.join(self.target_path, 'etc/iscsi/nodes')
        util.ensure_dir(self.iscsi_nodes)

    def _fmt_disconnect(self, target, portal):
        return ['iscsiadm', '--mode=node', '--targetname=%s' % target,
                '--portal=%s' % portal, '--logout']

    def _setup_nodes(self, sessions, connection):
        # setup iscsi_nodes dir (<fakeroot>/etc/iscsi/nodes) with content
        for s in sessions:
            sdir = os.path.join(self.iscsi_nodes, s)
            connpath = os.path.join(sdir, connection)
            util.ensure_dir(sdir)
            util.write_file(connpath, content="")

    def test_disconnect_target_disk(self):
        """Test iscsi disconnecting multiple sessions, all present"""

        sessions = [
            'curtin-53ab23ff-a887-449a-80a8-288151208091',
            'curtin-94b62de1-c579-42c0-879e-8a28178e64c5',
            'curtin-556aeecd-a227-41b7-83d7-2bb471c574b4',
            'curtin-fd0f644b-7858-420f-9997-3ea2aefe87b9'
        ]
        connection = '10.245.168.20,16395,1'
        self._setup_nodes(sessions, connection)

        self.mock_iscsi_sessions.return_value = "\n".join(sessions)

        iscsi.disconnect_target_disks(self.target_path)

        expected_calls = []
        for session in sessions:
            (host, port, _) = connection.split(',')
            disconnect = self._fmt_disconnect(session, "%s:%s" % (host, port))
            calls = [
                mock.call(['sync']),
                mock.call(disconnect, capture=True, log_captured=True),
                mock.call(['udevadm', 'settle']),
            ]
            expected_calls.extend(calls)

        self.mock_subp.assert_has_calls(expected_calls, any_order=True)

    def test_disconnect_target_disk_skip_disconnected(self):
        """Test iscsi does not attempt to disconnect already closed sessions"""
        sessions = [
            'curtin-53ab23ff-a887-449a-80a8-288151208091',
            'curtin-94b62de1-c579-42c0-879e-8a28178e64c5',
            'curtin-556aeecd-a227-41b7-83d7-2bb471c574b4',
            'curtin-fd0f644b-7858-420f-9997-3ea2aefe87b9'
        ]
        connection = '10.245.168.20,16395,1'
        self._setup_nodes(sessions, connection)
        # Test with all sessions are already disconnected
        self.mock_iscsi_sessions.return_value = ""

        iscsi.disconnect_target_disks(self.target_path)

        self.mock_subp.assert_has_calls([], any_order=True)

    @mock.patch('curtin.block.iscsi.iscsiadm_logout')
    def test_disconnect_target_disk_raises_runtime_error(self, mock_logout):
        """Test iscsi raises RuntimeError if we fail to logout"""
        sessions = [
            'curtin-53ab23ff-a887-449a-80a8-288151208091',
        ]
        connection = '10.245.168.20,16395,1'
        self._setup_nodes(sessions, connection)
        self.mock_iscsi_sessions.return_value = "\n".join(sessions)
        mock_logout.side_effect = util.ProcessExecutionError()

        with self.assertRaises(RuntimeError):
            iscsi.disconnect_target_disks(self.target_path)

        expected_calls = []
        for session in sessions:
            (host, port, _) = connection.split(',')
            disconnect = self._fmt_disconnect(session, "%s:%s" % (host, port))
            calls = [
                mock.call(['sync']),
                mock.call(disconnect, capture=True, log_captured=True),
                mock.call(['udevadm', 'settle']),
            ]
            expected_calls.extend(calls)

        self.mock_subp.assert_has_calls([], any_order=True)

# vi: ts=4 expandtab syntax=python
