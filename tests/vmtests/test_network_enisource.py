from . import logger, helpers
from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

import shutil
import subprocess
import yaml


class TestNetworkENISource(TestNetworkBaseTestsAbs):
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

    conf_file = "examples/tests/network_source.yaml"

    def test_source_cfg_exists(self):
        """Test that our curthooks wrote our injected config."""
        self.output_files_exist(["interfaces.d/interface2.cfg"])

    def test_etc_network_interfaces_source_cfg(self):
        """ Compare injected configuration as parsed by curtin matches
            how ifup configured the interface."""
        interfaces_orig = self.collect_path("interfaces")
        interfaces = interfaces_orig + ".test_enisource"
        # make a copy to modify
        shutil.copyfile(interfaces_orig, interfaces)

        # interfaces uses absolute paths, fix for test-case
        cmd = ['sed', '-i', '-e', 's,/etc/network/,,g',
               '{}'.format(interfaces)]
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)

        curtin_ifaces = self.parse_deb_config(interfaces)
        logger.debug('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))
        print('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))

        ip_a = self.load_collect_file("ip_a")
        logger.debug('ip a:\n{}'.format(ip_a))

        ip_a_dict = helpers.ip_a_to_dict(ip_a)
        logger.debug('parsed ip_a dict:\n{}'.format(
            yaml.dump(ip_a_dict, default_flow_style=False, indent=4)))
        print('parsed ip_a dict:\n{}'.format(
            yaml.dump(ip_a_dict, default_flow_style=False, indent=4)))

        iface = 'interface2'
        self.assertTrue(iface in curtin_ifaces)

        expected_address = curtin_ifaces[iface].get('address', None)
        self.assertIsNotNone(expected_address)

        # handle CIDR notation
        def _nocidr(addr):
            return addr.split("/")[0]

        [actual_address] = [ip.get('address') for ip in
                            ip_a_dict[iface].get('inet4', [])]
        self.assertEqual(_nocidr(expected_address), _nocidr(actual_address))


class PreciseTestNetworkENISource(relbase.precise, TestNetworkENISource):
    __test__ = False
    # not working, still debugging though; possible older ifupdown doesn't
    # like the multiple iface method.


class TrustyTestNetworkENISource(relbase.trusty, TestNetworkENISource):
    __test__ = True


class TrustyHWEXTestNetworkENISource(relbase.trusty_hwe_x,
                                     TestNetworkENISource):
    __test__ = True


class XenialTestNetworkENISource(relbase.xenial, TestNetworkENISource):
    __test__ = True


class YakketyTestNetworkENISource(relbase.yakkety, TestNetworkENISource):
    __test__ = True


class ZestyTestNetworkENISource(relbase.zesty, TestNetworkENISource):
    __test__ = True


class ArtfulTestNetworkENISource(relbase.artful, TestNetworkENISource):
    __test__ = True
