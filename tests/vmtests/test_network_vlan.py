from . import logger
from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

import textwrap
import yaml


class TestNetworkVlanAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/vlan_network.yaml"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
             cd OUTPUT_COLLECT_D
             dpkg-query -W -f '${Status}' vlan > vlan_installed
             ip -d link show interface1.2667 > ip_link_show_interface1.2667
             ip -d link show interface1.2668 > ip_link_show_interface1.2668
             ip -d link show interface1.2669 > ip_link_show_interface1.2669
             ip -d link show interface1.2670 > ip_link_show_interface1.2670
             """)]

    def get_vlans(self):
        network_state = self.get_network_state()
        logger.debug('get_vlans ns:\n%s', yaml.dump(network_state,
                                                    default_flow_style=False,
                                                    indent=4))
        interfaces = network_state.get('interfaces')
        return [iface for iface in interfaces.values()
                if iface['type'] == 'vlan']

    def test_output_files_exist_vlan(self):
        link_files = ["ip_link_show_%s" % vlan['name']
                      for vlan in self.get_vlans()]
        self.output_files_exist(["vlan_installed"] + link_files)

    def test_vlan_installed(self):
        status = self.load_collect_file("vlan_installed").strip()
        logger.debug('vlan installed?: %s', status)
        self.assertEqual('install ok installed', status)

    def test_vlan_enabled(self):

        # we must have at least one
        self.assertGreaterEqual(len(self.get_vlans()), 1)

        # did they get configured?
        for vlan in self.get_vlans():
            link_file = "ip_link_show_" + vlan['name']
            vlan_msg = "vlan protocol 802.1Q id " + str(vlan['vlan_id'])
            self.check_file_regex(link_file, vlan_msg)


class PreciseTestNetworkVlan(relbase.precise, TestNetworkVlanAbs):
    __test__ = True

    # precise ip -d link show output is different (of course)
    def test_vlan_enabled(self):

        # we must have at least one
        self.assertGreaterEqual(len(self.get_vlans()), 1)

        # did they get configured?
        for vlan in self.get_vlans():
            link_file = "ip_link_show_" + vlan['name']
            vlan_msg = "vlan id " + str(vlan['vlan_id'])
            self.check_file_regex(link_file, vlan_msg)


class TrustyTestNetworkVlan(relbase.trusty, TestNetworkVlanAbs):
    __test__ = True


class TrustyHWEXTestNetworkVlan(relbase.trusty_hwe_x, TestNetworkVlanAbs):
    __test__ = True


class XenialTestNetworkVlan(relbase.xenial, TestNetworkVlanAbs):
    __test__ = True


class YakketyTestNetworkVlan(relbase.yakkety, TestNetworkVlanAbs):
    __test__ = True
