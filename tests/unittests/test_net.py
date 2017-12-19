from unittest import TestCase
import os
import shutil
import tempfile

from curtin import net
from textwrap import dedent


class TestNetParserData(TestCase):

    def test_parse_deb_config_data_ignores_comments(self):
        contents = dedent("""\
            # ignore
            # iface eth0 inet static
            #  address 192.168.1.1
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({}, ifaces)

    def test_parse_deb_config_data_basic(self):
        contents = dedent("""\
            iface eth0 inet static
            address 192.168.1.2
            netmask 255.255.255.0
            hwaddress aa:bb:cc:dd:ee:ff
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'address': '192.168.1.2',
                'netmask': '255.255.255.0',
                'hwaddress': 'aa:bb:cc:dd:ee:ff',
                },
            }, ifaces)

    def test_parse_deb_config_data_auto(self):
        contents = dedent("""\
            auto eth0 eth1
            iface eth0 inet manual
            iface eth1 inet manual
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({
            'eth0': {
                'auto': True,
                'family': 'inet',
                'method': 'manual',
                },
            'eth1': {
                'auto': True,
                'family': 'inet',
                'method': 'manual',
                },
            }, ifaces)

    def test_parse_deb_config_data_error_on_redefine(self):
        contents = dedent("""\
            iface eth0 inet static
            address 192.168.1.2
            iface eth0 inet static
            address 192.168.1.3
            """)
        ifaces = {}
        self.assertRaises(
            net.ParserError,
            net.parse_deb_config_data, ifaces, contents, '')

    def test_parse_deb_config_data_commands(self):
        contents = dedent("""\
            iface eth0 inet manual
            pre-up preup1
            pre-up preup2
            up up1
            post-up postup1
            pre-down predown1
            down down1
            down down2
            post-down postdown1
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                'pre-up': ['preup1', 'preup2'],
                'up': ['up1'],
                'post-up': ['postup1'],
                'pre-down': ['predown1'],
                'down': ['down1', 'down2'],
                'post-down': ['postdown1'],
                },
            }, ifaces)

    def test_parse_deb_config_data_dns(self):
        contents = dedent("""\
            iface eth0 inet static
            dns-nameservers 192.168.1.1 192.168.1.2
            dns-search curtin local
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'dns': {
                    'nameservers': ['192.168.1.1', '192.168.1.2'],
                    'search': ['curtin', 'local'],
                    },
                },
            }, ifaces)

    def test_parse_deb_config_data_bridge(self):
        contents = dedent("""\
            iface eth0 inet manual
            iface eth1 inet manual
            iface br0 inet static
            address 192.168.1.1
            netmask 255.255.255.0
            bridge_maxwait 30
            bridge_ports eth0 eth1
            bridge_pathcost eth0 1
            bridge_pathcost eth1 2
            bridge_portprio eth0 0
            bridge_portprio eth1 1
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                },
            'eth1': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                },
            'br0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'address': '192.168.1.1',
                'netmask': '255.255.255.0',
                'bridge': {
                    'maxwait': '30',
                    'ports': ['eth0', 'eth1'],
                    'pathcost': {
                        'eth0': '1',
                        'eth1': '2',
                        },
                    'portprio': {
                        'eth0': '0',
                        'eth1': '1'
                        },
                    },
                },
            }, ifaces)


class TestNetParser(TestCase):

    def setUp(self):
        self.target = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.target)

    def make_config(self, path=None, name=None, contents=None,
                    parse=True):
        if path is None:
            path = self.target
        if name is None:
            name = 'interfaces'
        path = os.path.join(path, name)
        if contents is None:
            contents = dedent("""\
                auto eth0
                iface eth0 inet static
                address 192.168.1.2
                netmask 255.255.255.0
                hwaddress aa:bb:cc:dd:ee:ff
                """)
        with open(path, 'w') as stream:
            stream.write(contents)
        ifaces = None
        if parse:
            ifaces = {}
            net.parse_deb_config_data(ifaces, contents, '')
        return path, ifaces

    def test_parse_deb_config(self):
        path, data = self.make_config()
        expected = net.parse_deb_config(path)
        self.assertEqual(data, expected)

    def test_parse_deb_config_source(self):
        path, data = self.make_config(name='interfaces2')
        contents = dedent("""\
            source interfaces2
            iface eth1 inet manual
            """)
        i_path, _ = self.make_config(
            contents=contents, parse=False)
        data['eth1'] = {
            'auto': False,
            'family': 'inet',
            'method': 'manual',
            }
        expected = net.parse_deb_config(i_path)
        self.assertEqual(data, expected)

    def test_parse_deb_config_source_dir(self):
        subdir = os.path.join(self.target, 'interfaces.d')
        os.mkdir(subdir)
        path, data = self.make_config(
            path=subdir, name='interfaces2')
        contents = dedent("""\
            source-directory interfaces.d
            source interfaces2
            iface eth1 inet manual
            """)
        i_path, _ = self.make_config(
            contents=contents, parse=False)
        data['eth1'] = {
            'auto': False,
            'family': 'inet',
            'method': 'manual',
            }
        expected = net.parse_deb_config(i_path)
        self.assertEqual(data, expected)

# vi: ts=4 expandtab syntax=python
