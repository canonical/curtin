from unittest import TestCase
from curtin.block import iscsi


class TestBlockIscsiPortalParsing(TestCase):
    def test_iscsi_portal_parsing(self):
        # port must be specified
        self.assertFalse(iscsi.is_valid_iscsi_portal('192.168.1.12'))
        self.assertFalse(iscsi.is_valid_iscsi_portal(
            'fe80::a634:d9ff:fe40:768a'))

        self.assertFalse(iscsi.is_valid_iscsi_portal('192.168.1.12:'))
        # IP must be in [] if port is specified for IPv6
        self.assertFalse(iscsi.is_valid_iscsi_portal(
            'fe80::a634:d9ff:fe40:768a:9999'))
        # IP must not be in [] if port is specified for IPv4
        self.assertFalse(iscsi.is_valid_iscsi_portal('[192.168.1.12]:9000'))

        self.assertTrue(iscsi.is_valid_iscsi_portal('192.168.1.12:9000'))
        self.assertTrue(iscsi.is_valid_iscsi_portal(
            '[fe80::a634:d9ff:fe40:768a]:9999'))

    def test_iscsi_disk(self):
        # disk specification:
        # TARGETSPEC=ip:proto:port:lun:targetname
        # root=iscsi:$TARGETSPEC
        # root=iscsi:user:password@$TARGETSPEC
        # root=iscsi:user:password:initiatoruser:initiatorpassword@$TARGETSPEC
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('')

        # typo
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscs:')

        # no specification
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:::::')

        # invalid ip
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:192.168::::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:fe80:::::target')

        # invalid port
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:192.168.1.12::ABCD::target')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::ABCD::target')

        # no target
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:192.168.1.12::::')
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::::')

        # no ip
        with self.assertRaises(ValueError):
            iscsi.IscsiDisk('iscsi:::::target')

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

        iscsi.IscsiDisk('iscsi:192.168.1.12:6:3260:1:target')
        iscsi.IscsiDisk('iscsi:192.168.1.12::3260:1:target')
        iscsi.IscsiDisk('iscsi:192.168.1.12:::1:target')
        iscsi.IscsiDisk('iscsi:user:password@192.168.1.12:::1:target')
        iscsi.IscsiDisk('iscsi:user:@192.168.1.12:::1:target')
        iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                        '192.168.1.12:::1:target')
        iscsi.IscsiDisk('iscsi:user:password:iuser:@192.168.1.12:::1:target')
        iscsi.IscsiDisk('iscsi:user::iuser:@192.168.1.12:::1:target')

        iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6:3260:1:target')
        iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6:3260:1:target')
        iscsi.IscsiDisk('iscsi:fe80::a634:d9ff:fe40:768a:6::1:target')
        iscsi.IscsiDisk('iscsi:user:password@'
                        'fe80::a634:d9ff:fe40:768a:6:::1:target')
        iscsi.IscsiDisk('iscsi:user:@fe80::a634:d9ff:fe40:768a:6:::1:target')
        iscsi.IscsiDisk('iscsi:user:password:iuser:ipassword@'
                        'fe80::a634:d9ff:fe40:768a:6:::1:target')
        iscsi.IscsiDisk('iscsi:user:password:iuser:@'
                        'fe80::a634:d9ff:fe40:768a:6:::1:target')
        iscsi.IscsiDisk('iscsi:user::iuser:@'
                        'fe80::a634:d9ff:fe40:768a:6:::1:target')

        # test various forms
        # test specifing user but not password
        # test user but empty password
        # test same for initiator
        # test missing colons in targetspec

# vi: ts=4 expandtab syntax=python
