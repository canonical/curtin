from unittest import TestCase
from curtin.block import iscsi


class TestBlockIscsiPortalParsing(TestCase):
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

        i = iscsi.IscsiDisk('iscsi:fe80:::::target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.host, 'fe80:')
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
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::ABCD::target')
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:test.example.com::ABCD::target')

    def test_iscsi_disk_target(self):
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:192.168.1.12::::')
        with self.assertRaisesRegexp(ValueError, 'Both host and targetname'):
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::::')
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
            iscsi.IscsiDisk('iscsi:user@fe80::a634:d9ff:fe40:768a:6::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@test.example.com::::target')

        # iuser without password
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@192.168.1.12::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@'
                            'fe80::a634:d9ff:fe40:768a:6::::target')
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

# vi: ts=4 expandtab syntax=python
