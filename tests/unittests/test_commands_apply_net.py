from unittest import TestCase
from mock import patch
import copy

from curtin.commands import apply_net


class ApplyNetTestBase(TestCase):
    def setUp(self):
        super(ApplyNetTestBase, self).setUp()

    def add_patch(self, target, attr):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = patch(target, autospec=True)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class TestApplyNet(ApplyNetTestBase):
    def setUp(self):
        super(TestApplyNet, self).setUp()
        # self.target = tempfile.mkdtemp()

        basepath = 'curtin.commands.apply_net.'
        self.add_patch(basepath + '_maybe_remove_legacy_eth0', 'mock_legacy')
        self.add_patch(basepath + '_disable_ipv6_privacy_extensions',
                       'mock_ipv6_priv')
        self.add_patch(basepath + '_patch_ifupdown_ipv6_mtu_hook',
                       'mock_ipv6_mtu')
        self.add_patch('curtin.net.netconfig_passthrough_available',
                       'mock_netpass_avail')
        self.add_patch('curtin.net.netconfig_passthrough_v2_available',
                       'mock_netpass_v2_avail')
        self.add_patch('curtin.net.render_netconfig_passthrough',
                       'mock_netpass_render')
        self.add_patch('curtin.net.parse_net_config_data',
                       'mock_net_parsedata')
        self.add_patch('curtin.net.render_network_state',
                       'mock_net_renderstate')
        self.add_patch('curtin.net.network_state.from_state_file',
                       'mock_ns_from_file')
        self.add_patch('curtin.config.load_config', 'mock_load_config')

        self.target = "my_target"
        self.network_config = {
            'network': {
                'version': 1,
                'config': {},
            }
        }
        self.ns = {
            'interfaces': {},
            'routes': [],
            'dns': {
                'nameservers': [],
                'search': [],
            }
        }

    # def tearDown(self):
    #    shutil.rmtree(self.target)

    def test_apply_net_notarget(self):
        self.assertRaises(Exception,
                          apply_net.apply_net, None, "", "")

    def test_apply_net_nostate_or_config(self):
        self.assertRaises(Exception,
                          apply_net.apply_net, "")

    def test_apply_net_target_and_state(self):
        self.mock_ns_from_file.return_value = self.ns

        apply_net.apply_net(self.target, network_state=self.ns,
                            network_config=None)

        self.mock_net_renderstate.assert_called_with(target=self.target,
                                                     network_state=self.ns)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config(self):
        self.mock_load_config.return_value = self.network_config
        self.mock_netpass_avail.return_value = False
        self.mock_net_parsedata.return_value = self.ns

        apply_net.apply_net(self.target, network_state=None,
                            network_config=self.network_config)

        self.mock_netpass_avail.assert_called_with(self.target)
        self.assertFalse(self.mock_netpass_v2_avail.called)

        self.mock_net_renderstate.assert_called_with(target=self.target,
                                                     network_state=self.ns)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough(self):
        self.mock_load_config.return_value = self.network_config
        self.mock_netpass_avail.return_value = True

        netcfg = "network_config.yaml"
        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.mock_netpass_avail.assert_called_with(self.target)
        self.assertFalse(self.mock_netpass_v2_avail.called)
        nc = self.network_config
        self.mock_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_force(self):
        cfg = copy.deepcopy(self.network_config)
        cfg['network']['passthrough'] = True
        self.mock_load_config.return_value = cfg
        self.mock_netpass_avail.return_value = False

        netcfg = "network_config.yaml"
        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.assertFalse(self.mock_netpass_avail.called)
        self.assertFalse(self.mock_netpass_v2_avail.called)
        self.mock_netpass_render.assert_called_with(self.target, netconfig=cfg)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_nonet(self):
        nc = {'storage': {}}
        self.mock_load_config.return_value = nc
        self.mock_netpass_avail.return_value = True

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.mock_netpass_avail.assert_called_with(self.target)
        self.assertFalse(self.mock_netpass_v2_avail.called)
        self.mock_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_v2(self):
        nc = copy.deepcopy(self.network_config)
        nc['network']['version'] = 2
        self.mock_load_config.return_value = nc
        self.mock_netpass_avail.return_value = True
        self.mock_netpass_v2_avail.return_value = True

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.mock_netpass_avail.assert_called_with(self.target)
        self.mock_netpass_v2_avail.assert_called_with(self.target)
        self.mock_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_v2_not_available(self):
        nc = copy.deepcopy(self.network_config)
        nc['network']['version'] = 2
        self.mock_load_config.return_value = nc
        self.mock_netpass_avail.return_value = True
        self.mock_netpass_v2_avail.return_value = False
        self.mock_net_parsedata.return_value = self.ns

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.mock_netpass_avail.assert_called_with(self.target)
        self.mock_netpass_v2_avail.assert_called_with(self.target)
        self.assertFalse(self.mock_netpass_render.called)
        self.mock_net_parsedata.assert_called_with(nc['network'])

        self.mock_net_renderstate.assert_called_with(
            target=self.target, network_state=self.ns)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_v2_force(self):
        nc = copy.deepcopy(self.network_config)
        nc['network']['version'] = 2
        nc['network']['passthrough'] = True
        self.mock_load_config.return_value = nc
        self.mock_netpass_avail.return_value = False
        self.mock_netpass_v2_avail.return_value = False

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.assertFalse(self.mock_netpass_avail.called)
        self.assertFalse(self.mock_netpass_v2_avail.called)
        self.mock_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_disable_passthrough(self):
        nc = copy.deepcopy(self.network_config)
        nc['network']['passthrough'] = False
        self.mock_load_config.return_value = nc
        self.mock_netpass_avail.return_value = False
        self.mock_netpass_v2_avail.return_value = False
        self.mock_net_parsedata.return_value = self.ns

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.mock_ns_from_file.called)
        self.mock_load_config.assert_called_with(netcfg)
        self.assertFalse(self.mock_netpass_avail.called)
        self.assertFalse(self.mock_netpass_v2_avail.called)
        self.assertFalse(self.mock_netpass_render.called)
        self.mock_net_parsedata.assert_called_with(nc['network'])

        self.mock_net_renderstate.assert_called_with(
            target=self.target, network_state=self.ns)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)
