from . import logger, helpers
from .releases import base_vm_classes as relbase
from .test_network_ipv6 import TestNetworkIPV6Abs

import os
import subprocess
import textwrap
import yaml


class TestNetworkIPV6ENISource(TestNetworkIPV6Abs):
    """ Curtin now emits a source /etc/network/interfaces.d/*.cfg
        line.  This test exercises this feature by emitting additional
        network configuration in /etc/network/interfaces.d/interface2.cfg

        This relies on the network_config.yaml of the TestClass to
        define a spare nic with no configuration.  This ensures that
        a udev rule for interface2 is emitted so we can reference the interface
        in our injected configuration.

        Note, ifupdown allows multiple stanzas with the same iface name
        and combines the options together during ifup.  We rely on this
        feature allowing etc/network/interfaces to have an unconfigured
        iface interface2 inet manual line, and then defer the configuration
        to /etc/network/interfaces.d/interface2.cfg

        This testcase then uses curtin.net.deb_parse_config method to
        extract information about what curtin wrote and compare that
        with what was actually configured (which we capture via ifconfig)
    """

    conf_file = "examples/tests/network_source_ipv6.yaml"

    def test_source_cfg_exists(self):
        """Test that our curthooks wrote our injected config."""
        self.output_files_exist(["interfaces.d/interface2.cfg"])

    def test_etc_network_interfaces_source_cfg(self):
        """ Compare injected configuration as parsed by curtin matches
            how ifup configured the interface."""
        # interfaces uses absolute paths, fix for test-case
        interfaces = os.path.join(self.td.collect, "interfaces")
        cmd = ['sed', '-i.orig', '-e', 's,/etc/network/,,g',
               '{}'.format(interfaces)]
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)

        curtin_ifaces = self.parse_deb_config(interfaces)
        logger.debug('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))
        print('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.collect, "ifconfig_a")) as fp:
            ifconfig_a = fp.read()
            logger.debug('ifconfig -a:\n{}'.format(ifconfig_a))

        ifconfig_dict = helpers.ifconfig_to_dict(ifconfig_a)
        logger.debug('parsed ifconfig dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))
        print('parsed ifconfig dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))

        iface = 'interface2'
        self.assertTrue(iface in curtin_ifaces)

        expected_address = curtin_ifaces[iface].get('address', None)
        self.assertIsNotNone(expected_address)

        # handle CIDR notation
        def _nocidr(addr):
            return addr.split("/")[0]
        actual_address = ifconfig_dict[iface].get('address', "")
        self.assertEqual(_nocidr(expected_address), _nocidr(actual_address))


class PreciseTestNetworkIPV6ENISource(relbase.precise,
                                      TestNetworkIPV6ENISource):
    __test__ = False
    # not working, still debugging though; possible older ifupdown doesn't
    # like the multiple iface method.


class TrustyTestNetworkIPV6ENISource(relbase.trusty, TestNetworkIPV6ENISource):
    __test__ = True


class XenialTestNetworkIPV6ENISource(relbase.xenial, TestNetworkIPV6ENISource):
    __test__ = True


class YakketyTestNetworkIPV6ENISource(relbase.yakkety,
                                      TestNetworkIPV6ENISource):
    __test__ = True
