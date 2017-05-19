from .releases import base_vm_classes as relbase
from .test_network_vlan import TestNetworkVlanAbs


class TestNetworkIPV6VlanAbs(TestNetworkVlanAbs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"


class PreciseTestNetworkIPV6Vlan(relbase.precise, TestNetworkIPV6VlanAbs):
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


class TrustyTestNetworkIPV6Vlan(relbase.trusty, TestNetworkIPV6VlanAbs):
    __test__ = True


class TrustyHWEXTestNetworkIPV6Vlan(relbase.trusty_hwe_x,
                                    TestNetworkIPV6VlanAbs):
    __test__ = True


class XenialTestNetworkIPV6Vlan(relbase.xenial, TestNetworkIPV6VlanAbs):
    __test__ = True


class YakketyTestNetworkIPV6Vlan(relbase.yakkety, TestNetworkIPV6VlanAbs):
    __test__ = True


class ZestyTestNetworkIPV6Vlan(relbase.zesty, TestNetworkIPV6VlanAbs):
    __test__ = True


class ArtfulTestNetworkIPV6Vlan(relbase.artful, TestNetworkIPV6VlanAbs):
    __test__ = True
