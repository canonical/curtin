from unittest import TestCase
from mock import patch, call
import copy
import os

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

        basepath = 'curtin.commands.apply_net.'
        self.add_patch(basepath + '_maybe_remove_legacy_eth0', 'm_legacy')
        self.add_patch(basepath + '_disable_ipv6_privacy_extensions',
                       'm_ipv6_priv')
        self.add_patch(basepath + '_patch_ifupdown_ipv6_mtu_hook',
                       'm_ipv6_mtu')
        self.add_patch('curtin.net.netconfig_passthrough_available',
                       'm_netpass_avail')
        self.add_patch('curtin.net.render_netconfig_passthrough',
                       'm_netpass_render')
        self.add_patch('curtin.net.parse_net_config_data',
                       'm_net_parsedata')
        self.add_patch('curtin.net.render_network_state',
                       'm_net_renderstate')
        self.add_patch('curtin.net.network_state.from_state_file',
                       'm_ns_from_file')
        self.add_patch('curtin.config.load_config', 'm_load_config')

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

    def test_apply_net_notarget(self):
        self.assertRaises(Exception,
                          apply_net.apply_net, None, "", "")

    def test_apply_net_nostate_or_config(self):
        self.assertRaises(Exception,
                          apply_net.apply_net, "")

    def test_apply_net_target_and_state(self):
        self.m_ns_from_file.return_value = self.ns

        self.assertRaises(ValueError,
                          apply_net.apply_net, self.target,
                          network_state=self.ns, network_config=None)

    def test_apply_net_target_and_config(self):
        self.m_load_config.return_value = self.network_config
        self.m_netpass_avail.return_value = False
        self.m_net_parsedata.return_value = self.ns

        apply_net.apply_net(self.target, network_state=None,
                            network_config=self.network_config)

        self.m_netpass_avail.assert_called_with(self.target)

        self.m_net_renderstate.assert_called_with(target=self.target,
                                                     network_state=self.ns)
        self.m_legacy.assert_called_with(self.target)
        self.m_ipv6_priv.assert_called_with(self.target)
        self.m_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough(self):
        self.m_load_config.return_value = self.network_config
        self.m_netpass_avail.return_value = True

        netcfg = "network_config.yaml"
        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.m_ns_from_file.called)
        self.m_load_config.assert_called_with(netcfg)
        self.m_netpass_avail.assert_called_with(self.target)
        nc = self.network_config
        self.m_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.m_net_renderstate.called)
        self.m_legacy.assert_called_with(self.target)
        self.m_ipv6_priv.assert_called_with(self.target)
        self.m_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_nonet(self):
        nc = {'storage': {}}
        self.m_load_config.return_value = nc
        self.m_netpass_avail.return_value = True

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.m_ns_from_file.called)
        self.m_load_config.assert_called_with(netcfg)
        self.m_netpass_avail.assert_called_with(self.target)
        self.m_netpass_render.assert_called_with(self.target, netconfig=nc)

        self.assertFalse(self.m_net_renderstate.called)
        self.m_legacy.assert_called_with(self.target)
        self.m_ipv6_priv.assert_called_with(self.target)
        self.m_ipv6_mtu.assert_called_with(self.target)

    def test_apply_net_target_and_config_passthrough_v2_not_available(self):
        nc = copy.deepcopy(self.network_config)
        nc['network']['version'] = 2
        self.m_load_config.return_value = nc
        self.m_netpass_avail.return_value = False
        self.m_net_parsedata.return_value = self.ns

        netcfg = "network_config.yaml"

        apply_net.apply_net(self.target, network_state=None,
                            network_config=netcfg)

        self.assertFalse(self.m_ns_from_file.called)
        self.m_load_config.assert_called_with(netcfg)
        self.m_netpass_avail.assert_called_with(self.target)
        self.assertFalse(self.m_netpass_render.called)
        self.m_net_parsedata.assert_called_with(nc['network'])

        self.m_net_renderstate.assert_called_with(
            target=self.target, network_state=self.ns)
        self.m_legacy.assert_called_with(self.target)
        self.m_ipv6_priv.assert_called_with(self.target)
        self.m_ipv6_mtu.assert_called_with(self.target)


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

    @patch('curtin.util.write_file')
    def test_apply_ipv6_mtu_hook_write_fail(self, mock_write):
        target = 'mytarget'
        prehookfn = 'if-pre-up.d/mtuipv6'
        posthookfn = 'if-up.d/mtuipv6'
        mock_write.side_effect = (Exception)

        self.assertRaises(Exception,
                          apply_net._patch_ifupdown_ipv6_mtu_hook,
                          target,
                          prehookfn=prehookfn,
                          posthookfn=posthookfn)

    @patch('curtin.util.write_file')
    def test_apply_ipv6_mtu_hook_invalid_target(self, mock_write):
        """ Test that an invalid target will fail to build a
            proper path for util.write_file
        """
        target = {}
        prehookfn = 'if-pre-up.d/mtuipv6'
        posthookfn = 'if-up.d/mtuipv6'
        mock_write.side_effect = (Exception)

        self.assertRaises(ValueError,
                          apply_net._patch_ifupdown_ipv6_mtu_hook,
                          target,
                          prehookfn=prehookfn,
                          posthookfn=posthookfn)

    @patch('curtin.util.write_file')
    def test_apply_ipv6_mtu_hook_invalid_prepost_fn(self, mock_write):
        """ Test that invalid prepost filenames will fail to build a
            proper path for util.write_file
        """
        target = "mytarget"
        prehookfn = {'a': 1}
        posthookfn = {'b': 2}
        mock_write.side_effect = (Exception)

        self.assertRaises(ValueError,
                          apply_net._patch_ifupdown_ipv6_mtu_hook,
                          target,
                          prehookfn=prehookfn,
                          posthookfn=posthookfn)


class TestApplyNetPatchIpv6Priv(ApplyNetTestBase):

    @patch('curtin.util.del_file')
    @patch('curtin.util.load_file')
    @patch('os.path')
    @patch('curtin.util.write_file')
    def test_disable_ipv6_priv_extentions(self, mock_write, mock_ospath,
                                          mock_load, mock_del):
        target = 'mytarget'
        path = 'etc/sysctl.d/10-ipv6-privacy.conf'
        ipv6_priv_contents = (
            'net.ipv6.conf.all.use_tempaddr = 2\n'
            'net.ipv6.conf.default.use_tempaddr = 2')
        expected_ipv6_priv_contents = '\n'.join(
            ["# IPv6 Privacy Extensions (RFC 4941)",
             "# Disabled by curtin",
             "# net.ipv6.conf.all.use_tempaddr = 2",
             "# net.ipv6.conf.default.use_tempaddr = 2"])
        mock_ospath.exists.return_value = True
        mock_load.side_effect = [ipv6_priv_contents]

        apply_net._disable_ipv6_privacy_extensions(target)

        cfg = util.target_path(target, path=path)
        mock_write.assert_called_with(cfg, expected_ipv6_priv_contents)

    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_disable_ipv6_priv_extentions_decoderror(self, mock_ospath,
                                                     mock_load):
        target = 'mytarget'
        mock_ospath.exists.return_value = True

        # simulate loading of binary data
        mock_load.side_effect = (Exception)

        self.assertRaises(Exception,
                          apply_net._disable_ipv6_privacy_extensions,
                          target)

    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_disable_ipv6_priv_extentions_notfound(self, mock_ospath,
                                                   mock_load):
        target = 'mytarget'
        path = 'foo.conf'
        mock_ospath.exists.return_value = False

        apply_net._disable_ipv6_privacy_extensions(target, path=path)

        # source file not found
        cfg = util.target_path(target, path)
        mock_ospath.exists.assert_called_with(cfg)
        mock_load.assert_not_called()


class TestApplyNetRemoveLegacyEth0(ApplyNetTestBase):

    @patch('curtin.util.del_file')
    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_remove_legacy_eth0(self, mock_ospath, mock_load, mock_del):
        target = 'mytarget'
        path = 'eth0.cfg'
        cfg = util.target_path(target, path)
        legacy_eth0_contents = (
            'auto eth0\n'
            'iface eth0 inet dhcp')

        mock_ospath.exists.return_value = True
        mock_load.side_effect = [legacy_eth0_contents]

        apply_net._maybe_remove_legacy_eth0(target, path)

        mock_del.assert_called_with(cfg)

    @patch('curtin.util.del_file')
    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_remove_legacy_eth0_nomatch(self, mock_ospath, mock_load,
                                        mock_del):
        target = 'mytarget'
        path = 'eth0.cfg'
        legacy_eth0_contents = "nomatch"
        mock_ospath.join.side_effect = os.path.join
        mock_ospath.exists.return_value = True
        mock_load.side_effect = [legacy_eth0_contents]

        self.assertRaises(Exception,
                          apply_net._maybe_remove_legacy_eth0,
                          target, path)

        mock_del.assert_not_called()

    @patch('curtin.util.del_file')
    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_remove_legacy_eth0_badload(self, mock_ospath, mock_load,
                                        mock_del):
        target = 'mytarget'
        path = 'eth0.cfg'
        mock_ospath.exists.return_value = True
        mock_load.side_effect = (Exception)

        self.assertRaises(Exception,
                          apply_net._maybe_remove_legacy_eth0,
                          target, path)

        mock_del.assert_not_called()

    @patch('curtin.util.del_file')
    @patch('curtin.util.load_file')
    @patch('os.path')
    def test_remove_legacy_eth0_notfound(self, mock_ospath, mock_load,
                                         mock_del):
        target = 'mytarget'
        path = 'eth0.conf'
        mock_ospath.exists.return_value = False

        apply_net._maybe_remove_legacy_eth0(target, path)

        # source file not found
        cfg = util.target_path(target, path)
        mock_ospath.exists.assert_called_with(cfg)
        mock_load.assert_not_called()
        mock_del.assert_not_called()
