from unittest import TestCase
import os
import shutil
import tempfile
import yaml

from curtin import net
import curtin.net.network_state as network_state
from textwrap import dedent


class TestNetParserData(TestCase):

    def test_parse_deb_config_data_ignores_comments(self):
        contents = dedent("""\
            # ignore
            # iface eth0 inet static
            #  address 192.168.1.1
            """)
        ifaces = {}
        net.parse_deb_config_data(ifaces, contents, '', '')
        self.assertEqual({}, ifaces)

    def test_parse_deb_config_data_basic(self):
        contents = dedent("""\
            iface eth0 inet static
            address 192.168.1.2
            netmask 255.255.255.0
            hwaddress aa:bb:cc:dd:ee:ff
            """)
        ifaces = {}
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'address': '192.168.1.2',
                'netmask': '255.255.255.0',
                'hwaddress': 'aa:bb:cc:dd:ee:ff',
                '_source_path': '/etc/network/interfaces',
                },
            }, ifaces)

    def test_parse_deb_config_data_auto(self):
        contents = dedent("""\
            auto eth0 eth1
            iface eth0 inet manual
            iface eth1 inet manual
            """)
        ifaces = {}
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
        self.assertEqual({
            'eth0': {
                'auto': True,
                'control': 'auto',
                'family': 'inet',
                'method': 'manual',
                '_source_path': '/etc/network/interfaces',
                },
            'eth1': {
                'auto': True,
                'family': 'inet',
                'control': 'auto',
                'method': 'manual',
                '_source_path': '/etc/network/interfaces',
                },
            }, ifaces)

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
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
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
                '_source_path': '/etc/network/interfaces',
                },
            }, ifaces)

    def test_parse_deb_config_data_dns(self):
        contents = dedent("""\
            iface eth0 inet static
            dns-nameservers 192.168.1.1 192.168.1.2
            dns-search curtin local
            """)
        ifaces = {}
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'dns': {
                    'nameservers': ['192.168.1.1', '192.168.1.2'],
                    'search': ['curtin', 'local'],
                    },
                '_source_path': '/etc/network/interfaces',
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
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': '/etc/network/interfaces',
                },
            'eth1': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': '/etc/network/interfaces',
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
                '_source_path': '/etc/network/interfaces',
                },
            }, ifaces)

    def test_parse_deb_config_data_bond(self):
        contents = dedent("""\
            iface eth0 inet manual
            bond-master bond0
            bond-primary eth0
            bond-mode active-backup
            iface eth1 inet manual
            bond-master bond0
            bond-primary eth0
            bond-mode active-backup
            iface bond0 inet static
            address 192.168.1.1
            netmask 255.255.255.0
            bond-slaves none
            bond-primary eth0
            bond-mode active-backup
            bond-miimon 100
            """)
        ifaces = {}
        net.parse_deb_config_data(
            ifaces, contents, '', '/etc/network/interfaces')
        self.assertEqual({
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                'bond': {
                    'master': 'bond0',
                    'primary': 'eth0',
                    'mode': 'active-backup',
                    },
                '_source_path': '/etc/network/interfaces',
                },
            'eth1': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                'bond': {
                    'master': 'bond0',
                    'primary': 'eth0',
                    'mode': 'active-backup',
                    },
                '_source_path': '/etc/network/interfaces',
                },
            'bond0': {
                'auto': False,
                'family': 'inet',
                'method': 'static',
                'address': '192.168.1.1',
                'netmask': '255.255.255.0',
                'bond': {
                    'slaves': 'none',
                    'primary': 'eth0',
                    'mode': 'active-backup',
                    'miimon': '100',
                    },
                '_source_path': '/etc/network/interfaces',
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
            net.parse_deb_config_data(ifaces, contents, '', path)
        return path, ifaces

    def test_parse_deb_config(self):
        path, data = self.make_config()
        observed = net.parse_deb_config(path)
        self.assertEqual(data, observed)

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
            '_source_path': i_path,
            }
        observed = net.parse_deb_config(i_path)
        self.assertEqual(data, observed)

    def test_parse_deb_config_source_with_glob(self):
        path, data = self.make_config(name='eth0')
        contents = dedent("""\
            source eth*
            iface eth1 inet manual
            """)
        i_path, _ = self.make_config(
            contents=contents, parse=False)
        data['eth1'] = {
            'auto': False,
            'family': 'inet',
            'method': 'manual',
            '_source_path': i_path,
            }
        observed = net.parse_deb_config(i_path)
        self.assertEqual(data, observed)

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
            '_source_path': i_path,
            }
        observed = net.parse_deb_config(i_path)
        self.assertEqual(data, observed)

    def test_parse_deb_config_source_dir_glob(self):
        subdir = os.path.join(self.target, 'interfaces0.d')
        os.mkdir(subdir)
        self.make_config(
            path=subdir, name='eth0', contents="iface eth0 inet manual")
        self.make_config(
            path=subdir, name='eth1', contents="iface eth1 inet manual")
        subdir2 = os.path.join(self.target, 'interfaces1.d')
        os.mkdir(subdir2)
        self.make_config(
            path=subdir2, name='eth2', contents="iface eth2 inet manual")
        self.make_config(
            path=subdir2, name='eth3', contents="iface eth3 inet manual")
        contents = dedent("""\
            source-directory interfaces*.d
            """)
        i_path, _ = self.make_config(
            contents=contents, parse=False)
        data = {
            'eth0': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': os.path.join(subdir, "eth0"),
                },
            'eth1': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': os.path.join(subdir, "eth1"),
                },
            'eth2': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': os.path.join(subdir2, "eth2"),
                },
            'eth3': {
                'auto': False,
                'family': 'inet',
                'method': 'manual',
                '_source_path': os.path.join(subdir2, "eth3"),
                },
        }
        observed = net.parse_deb_config(i_path)
        self.assertEqual(data, observed)

    def test_parse_deb_config_source_dir_glob_ignores_none_matching(self):
        subdir = os.path.join(self.target, 'interfaces0.d')
        os.mkdir(subdir)
        self.make_config(
            path=subdir, name='.eth0', contents="iface eth0 inet manual")
        contents = dedent("""\
            source-directory interfaces*.d
            """)
        i_path, _ = self.make_config(
            contents=contents, parse=False)
        observed = net.parse_deb_config(i_path)
        self.assertEqual({}, observed)


class TestNetConfig(TestCase):
    def setUp(self):
        self.target = tempfile.mkdtemp()
        self.config_f = os.path.join(self.target, 'config')
        self.config = '''
# YAML example of a simple network config
network:
    version: 1
    config:
        # Physical interfaces.
        - type: physical
          name: eth0
          mac_address: "c0:d6:9f:2c:e8:80"
          subnets:
              - type: dhcp4
              - type: static
                address: 192.168.21.3/24
                dns_nameservers:
                  - 8.8.8.8
                  - 8.8.4.4
                dns_search: barley.maas sach.maas
        - type: physical
          name: eth1
          mac_address: "cf:d6:af:48:e8:80"
        - type: nameserver
          address:
            - 1.2.3.4
            - 5.6.7.8
          search:
            - wark.maas
'''

        with open(self.config_f, 'w') as fp:
            fp.write(self.config)

    def get_net_config(self, config=None):
        if config is None:
            config = self.config
        cfg = yaml.safe_load(config)
        return cfg.get('network')

    def get_net_state(self, config=None):
        net_cfg = self.get_net_config(config)
        version = net_cfg.get('version')
        config = net_cfg.get('config')
        ns = network_state.NetworkState(version=version, config=config)
        ns.parse_config()
        return ns

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_parse_net_config_data(self):
        ns = self.get_net_state()
        net_state_from_cls = ns.network_state

        net_state_from_fn = net.parse_net_config_data(self.get_net_config())
        self.assertEqual(net_state_from_cls, net_state_from_fn)

    def test_parse_net_config(self):
        ns = self.get_net_state()
        net_state_from_cls = ns.network_state

        net_state_from_fn = net.parse_net_config(self.config_f)
        self.assertEqual(net_state_from_cls, net_state_from_fn)

    def test_render_persistent_net(self):
        ns = self.get_net_state()
        udev_rules = ('# Autogenerated by curtin\n'
                      'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", '
                      'ATTR{address}=="cf:d6:af:48:e8:80", NAME="eth1"\n'
                      'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", '
                      'ATTR{address}=="c0:d6:9f:2c:e8:80", NAME="eth0"\n')
        persist_net_rules = net.render_persistent_net(ns.network_state)
        self.assertEqual(sorted(udev_rules.split('\n')),
                         sorted(persist_net_rules.split('\n')))

    def test_render_interfaces(self):
        ns = self.get_net_state()
        ifaces = dedent("""\
            auto lo
            iface lo inet loopback
                dns-nameservers 1.2.3.4 5.6.7.8
                dns-search wark.maas

            auto eth0
            iface eth0 inet dhcp
                post-up ifup eth0:1

            auto eth0:1
            iface eth0:1 inet static
                address 192.168.21.3/24
                dns-nameservers 8.8.8.8 8.8.4.4
                dns-search barley.maas sach.maas

            iface eth1 inet manual

            source /etc/network/interfaces.d/*.cfg
            """)
        net_ifaces = net.render_interfaces(ns.network_state)
        print(ns.network_state.get('interfaces'))
        self.assertEqual(sorted(ifaces.split('\n')),
                         sorted(net_ifaces.split('\n')))

    def test_render_interfaces_bonds(self):
        bond_config = open('examples/tests/bonding_network.yaml', 'r').read()

        ns = self.get_net_state(bond_config)
        ifaces = dedent("""\
            auto lo
            iface lo inet loopback

            auto interface0
            iface interface0 inet dhcp

            auto interface1
            iface interface1 inet manual
                bond-mode active-backup
                bond-master bond0

            auto interface2
            iface interface2 inet manual
                bond-mode active-backup
                bond-master bond0

            auto bond0
            iface bond0 inet static
                address 10.23.23.2/24
                bond-mode active-backup
                hwaddress 52:54:00:12:34:06
                bond-slaves none
                post-up ifup bond0:1

            auto bond0:1
            iface bond0:1 inet static
                address 10.23.24.2/24

            source /etc/network/interfaces.d/*.cfg
            """)
        net_ifaces = net.render_interfaces(ns.network_state)
        print("\n".join(list(map(str,
                                 enumerate(sorted(ifaces.split('\n')))))))
        print("\n^^ LOCAL -- RENDER vv")
        print("\n".join(list(map(str,
                                 enumerate(sorted(net_ifaces.split('\n')))))))
        print(ns.network_state.get('interfaces'))
        self.assertEqual(sorted(ifaces.split('\n')),
                         sorted(net_ifaces.split('\n')))

    def test_render_interfaces_iscsiroot(self):
        iscsi_config = open('examples/network-iscsiroot.yaml', 'r').read()

        ns = self.get_net_state(iscsi_config)
        ifaces = dedent("""\
            auto lo
            iface lo inet loopback

            # control-manual interface0
            iface interface0 inet dhcp

            auto interface1
            iface interface1 inet static
                address 192.168.14.2/24
                gateway 192.168.14.1
                mtu 1492
                post-up ifup interface1:1

            auto interface1:1
            iface interface1:1 inet static
                address 192.168.14.4/24

            allow-hotplug interface2
            iface interface2 inet static
                gateway 10.11.12.1
                address 10.11.12.13/22

            source /etc/network/interfaces.d/*.cfg
            """)
        net_ifaces = net.render_interfaces(ns.network_state)
        print("\n".join(sorted(ifaces.split('\n'))))
        print("\n^^ LOCAL -- RENDER vv")
        print("\n".join(sorted(net_ifaces.split('\n'))))
        print(ns.network_state.get('interfaces'))
        self.assertEqual(sorted(ifaces.split('\n')),
                         sorted(net_ifaces.split('\n')))

    def test_render_interfaces_ipv6_aliases(self):
        ipv6_aliases_config = '''
# YAML example of a simple network config
network:
    version: 1
    config:
        # Physical interfaces.
        - type: physical
          name: eth0
          mac_address: "c0:d6:9f:2c:e8:80"
          subnets:
              - type: static
                address: fde9:8f83:4a81:1:0:1:0:6/64
              - type: static
                address: 192.168.0.1/24
'''

        ns = self.get_net_state(ipv6_aliases_config)
        ifaces = dedent("""\
            auto lo
            iface lo inet loopback

            auto eth0
            iface eth0 inet6 static
                address fde9:8f83:4a81:1:0:1:0:6/64
                post-up ifup eth0:1

            auto eth0:1
            iface eth0:1 inet static
                address 192.168.0.1/24

            source /etc/network/interfaces.d/*.cfg
            """)
        net_ifaces = net.render_interfaces(ns.network_state)
        print("\n".join(sorted(ifaces.split('\n'))))
        print("\n^^ LOCAL -- RENDER vv")
        print("\n".join(sorted(net_ifaces.split('\n'))))
        print(ns.network_state.get('interfaces'))
        self.assertEqual(sorted(ifaces.split('\n')),
                         sorted(net_ifaces.split('\n')))


# vi: ts=4 expandtab syntax=python
