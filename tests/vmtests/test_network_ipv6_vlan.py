from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network_vlan import (TestNetworkVlanAbs,
                                CentosTestNetworkVlanAbs)


class TestNetworkIPV6VlanAbs(TestNetworkVlanAbs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"


class CentosTestNetworkIPV6VlanAbs(CentosTestNetworkVlanAbs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"


class TrustyTestNetworkIPV6Vlan(relbase.trusty, TestNetworkIPV6VlanAbs):
    __test__ = True


class TrustyHWEXTestNetworkIPV6Vlan(relbase.trusty_hwe_x,
                                    TestNetworkIPV6VlanAbs):
    __test__ = True


class XenialTestNetworkIPV6Vlan(relbase.xenial, TestNetworkIPV6VlanAbs):
    __test__ = True


class ZestyTestNetworkIPV6Vlan(relbase.zesty, TestNetworkIPV6VlanAbs):
    __test__ = True


class ArtfulTestNetworkIPV6Vlan(relbase.artful, TestNetworkIPV6VlanAbs):
    __test__ = True


class Centos66TestNetworkIPV6Vlan(centos_relbase.centos66fromxenial,
                                  CentosTestNetworkIPV6VlanAbs):
    __test__ = True


class Centos70TestNetworkIPV6Vlan(centos_relbase.centos70fromxenial,
                                  CentosTestNetworkIPV6VlanAbs):
    __test__ = True
