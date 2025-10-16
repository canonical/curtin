# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path
from unittest.mock import patch, Mock


from curtin import nvme_tcp
from curtin.util import ProcessExecutionError
from .helpers import CiTestCase

import yaml


class TestNVMeTCP(CiTestCase):
    def test_no_nvme_controller(self):
        with patch('curtin.block.nvme.get_nvme_controllers_from_config',
                   return_value=[]):
            self.assertFalse(
                    nvme_tcp.get_nvme_stas_controller_directives(None))
            self.assertFalse(nvme_tcp.get_nvme_commands(None))

    def test_pcie_controller(self):
        controllers = [{'type': 'nvme_controller', 'transport': 'pcie'}]
        with patch('curtin.block.nvme.get_nvme_controllers_from_config',
                   return_value=controllers):
            self.assertFalse(
                    nvme_tcp.get_nvme_stas_controller_directives(None))
            self.assertFalse(nvme_tcp.get_nvme_commands(None))

    def test_tcp_controller(self):
        stas_expected = {
            'controller = transport=tcp;traddr=1.2.3.4;trsvcid=1111',
        }
        cmds_expected = [(
            "nvme", "connect-all",
            "--transport", "tcp",
            "--traddr", "1.2.3.4",
            "--trsvcid", "1111",
            ),
        ]
        controllers = [{
            "type": "nvme_controller",
            "transport": "tcp",
            "tcp_addr": "1.2.3.4",
            "tcp_port": "1111",
        }]

        with patch('curtin.block.nvme.get_nvme_controllers_from_config',
                   return_value=controllers):
            stas_result = nvme_tcp.get_nvme_stas_controller_directives(None)
            cmds_result = nvme_tcp.get_nvme_commands(None)
        self.assertEqual(stas_expected, stas_result)
        self.assertEqual(cmds_expected, cmds_result)

    def test_three_nvme_controllers(self):
        stas_expected = {
            "controller = transport=tcp;traddr=1.2.3.4;trsvcid=1111",
            "controller = transport=tcp;traddr=4.5.6.7;trsvcid=1212",
        }
        cmds_expected = [(
            "nvme", "connect-all",
            "--transport", "tcp",
            "--traddr", "1.2.3.4",
            "--trsvcid", "1111",
            ), (
            "nvme", "connect-all",
            "--transport", "tcp",
            "--traddr", "4.5.6.7",
            "--trsvcid", "1212",
            ),
        ]
        controllers = [
            {
                "type": "nvme_controller",
                "transport": "tcp",
                "tcp_addr": "1.2.3.4",
                "tcp_port": "1111",
            }, {
                "type": "nvme_controller",
                "transport": "tcp",
                "tcp_addr": "4.5.6.7",
                "tcp_port": "1212",
            }, {
                "type": "nvme_controller",
                "transport": "pcie",
            },
        ]

        with patch('curtin.block.nvme.get_nvme_controllers_from_config',
                   return_value=controllers):
            stas_result = nvme_tcp.get_nvme_stas_controller_directives(None)
            cmds_result = nvme_tcp.get_nvme_commands(None)
        self.assertEqual(stas_expected, stas_result)
        self.assertEqual(cmds_expected, cmds_result)

    def test_get_ip_commands__ethernet_static(self):
        netcfg = """\
# This is the network config written by 'subiquity'
network:
  ethernets:
    ens3:
     addresses:
     - 10.0.2.15/24
     nameservers:
       addresses:
       - 8.8.8.8
       - 8.4.8.4
       search:
       - foo
       - bar
     routes:
     - to: default
       via: 10.0.2.2
  version: 2"""

        cfg = {
            "write_files": {
                "etc_netplan_installer": {
                    "content": netcfg,
                    "path": "etc/netplan/00-installer-config.yaml",
                    "permissions": "0600",
                },
            },
        }
        expected = [
            ("ip", "address", "add", "10.0.2.15/24", "dev", "ens3"),
            ("ip", "link", "set", "ens3", "up"),
            ("ip", "route", "add", "default", "via", "10.0.2.2"),
        ]
        self.assertEqual(expected, nvme_tcp.get_ip_commands(cfg))

    def test_get_ip_commands__ethernet_dhcp4(self):
        netcfg = """\
# This is the network config written by 'subiquity'
network:
  ethernets:
    ens3:
     dhcp4: true
  version: 2"""

        cfg = {
            "write_files": {
                "etc_netplan_installer": {
                    "content": netcfg,
                    "path": "etc/netplan/00-installer-config.yaml",
                    "permissions": "0600",
                },
            },
        }
        expected = [
            ("dhcpcd", "-4", "ens3"),
        ]
        self.assertEqual(expected, nvme_tcp.get_ip_commands(cfg))

    def test_need_network_in_initramfs__usr_is_netdev(self):
        self.assertTrue(nvme_tcp.need_network_in_initramfs({
            "storage": {
                "config": [
                    {
                        "type": "mount",
                        "path": "/usr",
                        "options": "default,_netdev",
                    }, {
                        "type": "mount",
                        "path": "/",
                    }, {
                        "type": "mount",
                        "path": "/boot",
                    },
                ],
            },
        }))

    def test_need_network_in_initramfs__rootfs_is_netdev(self):
        self.assertTrue(nvme_tcp.need_network_in_initramfs({
            "storage": {
                "config": [
                    {
                        "type": "mount",
                        "path": "/",
                        "options": "default,_netdev",
                    }, {
                        "type": "mount",
                        "path": "/boot",
                    },
                ],
            },
        }))

    def test_need_network_in_initramfs__only_home_is_netdev(self):
        self.assertFalse(nvme_tcp.need_network_in_initramfs({
            "storage": {
                "config": [
                    {
                        "type": "mount",
                        "path": "/home",
                        "options": "default,_netdev",
                    }, {
                        "type": "mount",
                        "path": "/",
                    },
                ],
            },
        }))

    def test_need_network_in_initramfs__empty_conf(self):
        self.assertFalse(nvme_tcp.need_network_in_initramfs({}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs(
            {"storage": False}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs(
            {"storage": {}}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs({
            "storage": {
                "config": "disabled",
            },
        }))

    def test_requires_firmware_support__root_on_remote(self):
        self.assertTrue(nvme_tcp.requires_firmware_support({
            "storage": {
                "config": [
                    {
                        "type": "mount",
                        "path": "/",
                        "options": "default,_netdev",
                    },
                ],
            },
        }))
        self.assertFalse(nvme_tcp.requires_firmware_support({
            "storage": {
                "config": [
                    {
                        "type": "mount",
                        "path": "/boot",
                    }, {
                        "type": "mount",
                        "path": "/",
                        "options": "default,_netdev",
                    },
                ],
            },
        }))

    def test_requires_firmware_support__empty_conf(self):
        self.assertFalse(nvme_tcp.requires_firmware_support({}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs(
            {"storage": False}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs(
            {"storage": {}}))
        self.assertFalse(nvme_tcp.need_network_in_initramfs({
            "storage": {
                "config": "disabled",
            },
        }))

    def test_dracut_add_systemd_network_cmdline(self):
        target = self.tmp_dir()
        nvme_tcp.dracut_add_systemd_network_cmdline(target=Path(target))
        mod_name = "35curtin-systemd-network-cmdline"
        cmdline_sh = Path(
            f"{target}/usr/lib/dracut/modules.d/{mod_name}/networkd-cmdline.sh"
        )
        setup_sh = Path(
            f"{target}/usr/lib/dracut/modules.d/{mod_name}/module-setup.sh"
        )
        self.assertTrue(cmdline_sh.exists())
        self.assertTrue(setup_sh.exists())

    def test_initramfs_tools_configure_no_firmware_support(self):
        target = self.tmp_dir()

        nvme_cmds = [
            ('nvme', 'connect-all', '--transport', 'tcp', '--traddr',
             '172.16.82.77', '--trsvcid', '4420'),
        ]

        ip_cmds = [
            ('dhcpcd', '-4', 'ens3'),
        ]

        get_nvme_cmds_sym = "curtin.nvme_tcp.get_nvme_commands"
        get_ip_cmds_sym = "curtin.nvme_tcp.get_ip_commands"

        with (patch(get_nvme_cmds_sym, return_value=nvme_cmds),
              patch(get_ip_cmds_sym, return_value=ip_cmds)):
            nvme_tcp.initramfs_tools_configure_no_firmware_support(
                    {}, target=Path(target))

        init_premount_dir = 'etc/initramfs-tools/scripts/init-premount'

        hook = Path(target + '/etc/initramfs-tools/hooks/curtin-nvme-over-tcp')
        bootscript = Path(
            f'{target}/{init_premount_dir}/curtin-nvme-over-tcp')
        netup_script = Path(target + '/etc/curtin-nvme-over-tcp/network-up')
        connect_nvme_script = Path(
                target + '/etc/curtin-nvme-over-tcp/connect-nvme')

        self.assertTrue(hook.exists())
        self.assertTrue(bootscript.exists())

        netup_expected_contents = '''\
#!/bin/sh

# This file was created by curtin.
# If you make modifications to it, please remember to regenerate the initramfs
# using the command `update-initramfs -u`.

dhcpcd -4 ens3
'''
        self.assertEqual(netup_expected_contents, netup_script.read_text())
        connect_nvme_expected_contents = '''\
#!/bin/sh

# This file was created by curtin.
# If you make modifications to it, please remember to regenerate the initramfs
# using the command `update-initramfs -u`.

nvme connect-all --transport tcp --traddr 172.16.82.77 --trsvcid 4420
'''
        self.assertEqual(connect_nvme_expected_contents,
                         connect_nvme_script.read_text())

    def test_configure_nvme_stas(self):
        target = self.tmp_dir()

        directives = [
            'controller = transport=tcp;traddr=172.16.82.77;trsvcid=4420',
        ]

        with patch('curtin.nvme_tcp.get_nvme_stas_controller_directives',
                   return_value=directives):
            nvme_tcp.configure_nvme_stas({}, target=Path(target))

        stafd = Path(target + '/etc/stas/stafd.conf')

        stafd_expected_contents = '''\
# This file was created by curtin.

[Controllers]
controller = transport=tcp;traddr=172.16.82.77;trsvcid=4420
'''
        self.assertEqual(stafd_expected_contents, stafd.read_text())

    def test__iproute2(self):
        out = '''\
[{"priority":0,"src":"all","table":"local"},{"priority":32766,\
"src":"all","table":"main"},{"priority":32767,"src":"all","table":"default"}]
'''
        json_value = Mock()

        with patch('curtin.nvme_tcp.util.subp',
                   return_value=(out, '')) as m_subp:
            with patch('curtin.nvme_tcp.json.loads', return_value=json_value):
                data = nvme_tcp._iproute2(['rule', 'show'])

        m_subp.assert_called_once_with(['ip', '-j', 'rule', 'show'],
                                       capture=True)
        # Ensure the value of json.loads is forwarded to the caller.
        self.assertIs(json_value, data)

    def test_get_route_dest_ifname(self):
        rv = [
            {"dst": "1.2.3.4", "gateway": "192.168.0.1", "dev": "enp1s0",
             "prefsrc": "192.168.0.14", "flags": [], "uid": 1000, "cache": []},
        ]
        with patch('curtin.nvme_tcp._iproute2', return_value=rv) as m_iproute2:
            self.assertEqual(
                    'enp1s0', nvme_tcp.get_route_dest_ifname('1.2.3.4'))
        m_iproute2.assert_called_once_with(['route', 'get', '1.2.3.4'])

    def test_get_route_dest_ifname__no_route(self):
        err = '''\
RTNETLINK answers: Network is unreachable
'''
        pee = ProcessExecutionError(stdout='', stderr=err, exit_code=2, cmd=[])

        with patch('curtin.nvme_tcp._iproute2', side_effect=pee) as m_subp:
            with self.assertRaises(nvme_tcp.NetRuntimeError):
                nvme_tcp.get_route_dest_ifname('1.2.3.4')
        m_subp.assert_called_once_with(['route', 'get', '1.2.3.4'])

    def test_get_iface_hw_addr(self):
        rv = [
            {"ifindex": 3, "ifname": "enp1s0",
             "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
             "mtu": 1500, "qdisc": "fq_codel", "operstate": "UP",
             "linkmode": "DEFAULT", "group": "default", "txqlen": 1000,
             "link_type": "ether", "address": "4a:25:e2:5b:dc:2e",
             "broadcast": "ff:ff:ff:ff:ff:ff"}
        ]
        with patch('curtin.nvme_tcp._iproute2', return_value=rv) as m_iproute2:
            self.assertEqual(
                    '4a:25:e2:5b:dc:2e', nvme_tcp.get_iface_hw_addr('enp1s0'))
        m_iproute2.assert_called_once_with(['link', 'show', 'dev', 'enp1s0'])

    def test_get_iface_hw_addr__no_iface(self):
        err = '''\
Device "enp1s0" does not exist.
'''
        pee = ProcessExecutionError(stdout='', stderr=err, exit_code=1, cmd=[])
        with patch('curtin.nvme_tcp.util.subp', side_effect=pee) as m_subp:
            with self.assertRaises(nvme_tcp.NetRuntimeError):
                nvme_tcp.get_iface_hw_addr('enp1s0')
        m_subp.assert_called_once_with(
            ['ip', '-j', 'link', 'show', 'dev', 'enp1s0'],
            capture=True)

    def test_dracut_adapt_netplan_config__ens3(self):
        content = '''\
# This is the network config written by 'subiquity'
network:
  ethernets:
    ens3:
      addresses:
      - 10.0.2.15/24
      nameservers:
        addresses:
        - 8.8.8.8
        - 8.4.8.4
        search:
        - foo
        - bar
        routes:
        - to: default
          via: 10.0.2.2
  version: 2
'''
        cfg = {
            'storage': {
                'config': [{
                    'type': 'nvme_controller',
                    'id': 'nvme-controller-nvme0',
                    'transport': 'tcp',
                    'tcp_addr': '10.0.2.144',
                    'tcp_port': 4420,
                }],
            }, 'write_files': {
                'etc_netplan_installer': {
                    'path': 'etc/netplan/installer.yaml'}
            }
        }

        target = Path(self.tmp_dir())
        netplan_conf_path = target / 'etc/netplan/installer.yaml'
        netplan_conf_path.parent.mkdir(parents=True)
        netplan_conf_path.write_text(content)

        p_route_ifname = patch('curtin.nvme_tcp.get_route_dest_ifname',
                               return_value='ens3')
        p_hw_addr = patch('curtin.nvme_tcp.get_iface_hw_addr',
                          return_value='aa:bb:cc:dd:ee:ff')
        with p_route_ifname, p_hw_addr:
            nvme_tcp.dracut_adapt_netplan_config(cfg, target=target)

        new_content = yaml.safe_load(netplan_conf_path.read_text())
        new_ens3_content = new_content['network']['ethernets']['ens3']

        self.assertEqual(
                new_ens3_content['match']['macaddress'], 'aa:bb:cc:dd:ee:ff')
        self.assertTrue(new_ens3_content['critical'])

    def test_dracut_adapt_netplan_config_25_10(self):
        content = '''\
# This is the network config written by 'subiquity'
network:
  ethernets:
    enp1s0:
      dhcp4: true
      dhcp6: true
      match:
        macaddress: 52:54:00:6a:b9:8d
      set-name: enp1s0
  version: 2
'''
        cfg = {
            'storage': {
                'config': [{
                    'type': 'nvme_controller',
                    'id': 'nvme-controller-nvme0',
                    'transport': 'tcp',
                    'tcp_addr': '10.0.2.144',
                    'tcp_port': 4420,
                }],
            }, 'write_files': {
                'etc_netplan_installer': {
                    'path': 'etc/netplan/installer.yaml'}
            }
        }

        target = Path(self.tmp_dir())
        netplan_conf_path = target / 'etc/netplan/installer.yaml'
        netplan_conf_path.parent.mkdir(parents=True)
        netplan_conf_path.write_text(content)

        p_route_ifname = patch('curtin.nvme_tcp.get_route_dest_ifname',
                               return_value='enp1s0')
        p_hw_addr = patch('curtin.nvme_tcp.get_iface_hw_addr',
                          return_value='52:54:00:6a:b9:8d')
        with p_route_ifname, p_hw_addr:
            nvme_tcp.dracut_adapt_netplan_config(cfg, target=target)

        new_content = yaml.safe_load(netplan_conf_path.read_text())
        new_enp1s0_content = new_content['network']['ethernets']['enp1s0']

        self.assertEqual(
                new_enp1s0_content['match']['macaddress'], '52:54:00:6a:b9:8d')
        self.assertTrue(new_enp1s0_content['critical'])
        self.assertNotIn('set-name', new_enp1s0_content)

    def test_dracut_adapt_netplan_config__no_config(self):
        content = '''\
# This is the network config written by 'subiquity'
network:
  ethernets: {}
  version: 2
'''
        nvme_tcp.dracut_adapt_netplan_config({}, target=Path('/target'))
        nvme_tcp.dracut_adapt_netplan_config(
                {'write_files': {
                    'etc_netplan_installer': {
                        'content': content}}}, target=Path('/target'))
