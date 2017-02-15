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

    def test_iscsi_portal_parsing_valid_ip(self):
        # IP must be in [] for IPv6
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('fe80::a634:d9ff:fe40:768a:9999')
        # IP must not be in [] if port is specified for IPv4
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv6 address'):
            iscsi.assert_valid_iscsi_portal('[192.168.1.12]:9000')

    def test_iscsi_portal_parsing_ip(self):
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv6 address'):
            iscsi.assert_valid_iscsi_portal(
                '[1200::AB00:1234::2552:7777:1313]:9999')
        with self.assertRaisesRegexp(ValueError, 'Invalid IPv4 address'):
            iscsi.assert_valid_iscsi_portal('192.168:9000')

    def test_iscsi_portal_parsing_port(self):
        with self.assertRaisesRegexp(ValueError, 'not in the format'):
            iscsi.assert_valid_iscsi_portal('192.168.1.12:ABCD')

    def test_iscsi_portal_parsing_good_portals(self):
        ip, port = iscsi.assert_valid_iscsi_portal('192.168.1.12:9000')
        self.assertEquals(ip, '192.168.1.12')
        self.assertEquals(port, 9000)

        ip, port = iscsi.assert_valid_iscsi_portal(
            '[fe80::a634:d9ff:fe40:768a]:9999')
        self.assertEquals(ip, 'fe80::a634:d9ff:fe40:768a')
        self.assertEquals(port, 9999)

    # disk specification:
    # TARGETSPEC=ip:proto:port:lun:targetname
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
        with self.assertRaisesRegexp(ValueError, 'Both IP and targetname'):
            iscsi.IscsiDisk('iscsi:::::')

    def test_iscsi_disk_ip_valid(self):
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI IP'):
            iscsi.IscsiDisk('iscsi:192.168::::target')
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI IP'):
            iscsi.IscsiDisk('iscsi:fe80:::::target')

    def test_iscsi_disk_port(self):
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:192.168.1.12::ABCD::target')
        with self.assertRaisesRegexp(ValueError, 'Specified iSCSI port'):
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::ABCD::target')

    def test_iscsi_disk_target(self):
        with self.assertRaisesRegexp(ValueError, 'Both IP and targetname'):
            iscsi.IscsiDisk('iscsi:192.168.1.12::::')
        with self.assertRaisesRegexp(ValueError, 'Both IP and targetname'):
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::::')

    def test_iscsi_disk_ip(self):
        with self.assertRaisesRegexp(ValueError, 'Both IP and targetname'):
            iscsi.IscsiDisk('iscsi:::::target')

    def test_iscsi_disk_auth(self):
        # user without password
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@192.168.1.12::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user@fe80::a634:d9ff:fe40:768a:6::::target')

        # iuser without password
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@192.168.1.12::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:user:password:iuser@'
                            'fe80::a634:d9ff:fe40:768a:6::::target')

    def test_iscsi_disk_good(self):
        i = iscsi.IscsiDisk('iscsi:192.168.1.12:6:3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:192.168.1.12::3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:192.168.1.12:::1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, '192.168.1.12')
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
        self.assertEquals(i.ip, '192.168.1.12')
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
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user::iuser:@192.168.1.12:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.ip, '192.168.1.12')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk(
            'iscsi:fe80::a634:d9ff:fe40:768a:6:5:3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::3260:1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, None)
        self.assertEquals(i.password, None)
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password@'
                            'fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:@'
                            'fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, None)
        self.assertEquals(i.ipassword, None)
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                            'fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, 'ipassword')
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user:password:iuser:@'
                            'fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, 'password')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

        i = iscsi.IscsiDisk('iscsi:user::iuser:@'
                            'fe80::a634:d9ff:fe40:768a:6:::1:target')
        self.assertEquals(i.user, 'user')
        self.assertEquals(i.password, '')
        self.assertEquals(i.iuser, 'iuser')
        self.assertEquals(i.ipassword, '')
        self.assertEquals(i.ip, 'fe80::a634:d9ff:fe40:768a:6')
        self.assertEquals(i.proto, '6')
        self.assertEquals(i.port, 3260)
        self.assertEquals(i.lun, 1)
        self.assertEquals(i.target, 'target')

# vi: ts=4 expandtab syntax=python
