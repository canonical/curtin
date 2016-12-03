from unittest import TestCase
from mock import patch, call
import copy

from curtin.commands import apply_net
from curtin import util


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
        self.mock_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.mock_net_renderstate.called)
        self.mock_legacy.assert_called_with(self.target)
        self.mock_ipv6_priv.assert_called_with(self.target)
        self.mock_ipv6_mtu.assert_called_with(self.target)


class TestApplyNetPatchIfupdown(ApplyNetTestBase):

    @patch('curtin.util.write_file')
    def test_apply_ipv6_mtu_hook(self, mock_write):
        target = 'mytarget'
        prehookfn = 'if-pre-up.d/mtuipv6'
        posthookfn = 'if-up.d/mtuipv6'
        mode = 0o755

        apply_net._patch_ifupdown_ipv6_mtu_hook(target,
                                                prehookfn=prehookfn,
                                                posthookfn=posthookfn)

        precfg = util.target_path(target, path=prehookfn)
        postcfg = util.target_path(target, path=posthookfn)
        precontents = apply_net.IFUPDOWN_IPV6_MTU_PRE_HOOK
        postcontents = apply_net.IFUPDOWN_IPV6_MTU_POST_HOOK

        hook_calls = [
            call(precfg, precontents, mode=mode),
            call(postcfg, postcontents, mode=mode),
        ]
        mock_write.assert_has_calls(hook_calls)
