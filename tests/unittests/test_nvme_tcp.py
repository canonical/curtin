# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path
from unittest.mock import patch


from curtin import nvme_tcp
from .helpers import CiTestCase


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

    def test_initramfs_tools_configure(self):
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
            nvme_tcp.initramfs_tools_configure({}, target=Path(target))

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
