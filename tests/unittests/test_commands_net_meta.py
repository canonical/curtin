# This file is part of curtin. See LICENSE file for copyright and license info.

import os

from mock import MagicMock, call

from .helpers import CiTestCase, simple_mocked_open

from curtin.commands.net_meta import net_meta


class NetMetaTarget:
    def __init__(self, target, mode=None, devices=None):
        self.target = target
        self.mode = mode
        self.devices = devices


class TestNetMeta(CiTestCase):

    def setUp(self):
        super(TestNetMeta, self).setUp()

        self.add_patch('curtin.util.run_hook_if_exists', 'm_run_hook')
        self.add_patch('curtin.util.load_command_environment', 'm_command_env')
        self.add_patch('curtin.config.load_command_config', 'm_command_config')
        self.add_patch('curtin.config.dump_config', 'm_dump_config')
        self.add_patch('os.environ', 'm_os_environ')

        self.args = NetMetaTarget(
            target='net-meta-target'
        )

        self.base_network_config = {
            'network': {
                'version': 1,
                'config': {
                    'type': 'physical',
                    'name': 'interface0',
                    'mac_address': '52:54:00:12:34:00',
                    'subnets': {
                        'type': 'dhcp4'
                    }
                }
            }
        }

        self.disabled_network_config = {
            'network': {
                'version': 1,
                'config': 'disabled'
            }
        }

        self.output_network_path = self.tmp_path('my-network-config')
        self.expected_exit_code = 0
        self.m_run_hook.return_value = False
        self.m_command_env.return_value = {}
        self.m_command_config.return_value = self.base_network_config
        self.m_os_environ.get.return_value = self.output_network_path

        self.dump_content = 'yaml-format-network-config'
        self.m_dump_config.return_value = self.dump_content

    def test_net_meta_with_disabled_network(self):
        self.args.mode = 'disabled'

        with self.assertRaises(SystemExit) as cm:
            with simple_mocked_open(content='') as m_open:
                net_meta(self.args)

        self.assertEqual(self.expected_exit_code, cm.exception.code)
        self.m_run_hook.assert_called_with(
            self.args.target, 'network-config')
        self.assertEqual(1, self.m_run_hook.call_count)
        self.assertEqual(0, self.m_command_env.call_count)
        self.assertEqual(0, self.m_command_config.call_count)

        self.assertEquals(self.args.mode, 'disabled')
        self.assertEqual(0, self.m_os_environ.get.call_count)
        self.assertEqual(0, self.m_dump_config.call_count)
        self.assertFalse(os.path.exists(self.output_network_path))
        self.assertEqual(0, m_open.call_count)

    def test_net_meta_with_config_network(self):
        network_config = self.disabled_network_config
        self.m_command_config.return_value = network_config

        expected_m_command_env_calls = 2
        expected_m_command_config_calls = 2
        m_file = MagicMock()

        with self.assertRaises(SystemExit) as cm:
            with simple_mocked_open(content='') as m_open:
                m_open.return_value = m_file
                net_meta(self.args)

        self.assertEqual(self.expected_exit_code, cm.exception.code)
        self.m_run_hook.assert_called_with(
            self.args.target, 'network-config')
        self.assertEquals(self.args.mode, 'custom')
        self.assertEqual(
            expected_m_command_env_calls, self.m_command_env.call_count)
        self.assertEqual(
            expected_m_command_config_calls, self.m_command_env.call_count)
        self.m_dump_config.assert_called_with(network_config)
        self.assertEqual(
            [call(self.output_network_path, 'w')], m_open.call_args_list)
        self.assertEqual(
            [call(self.dump_content)],
            m_file.__enter__.return_value.write.call_args_list)
