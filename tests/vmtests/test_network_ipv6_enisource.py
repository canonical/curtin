from .releases import base_vm_classes as relbase
from .test_network_enisource import TestNetworkENISource


class TestNetworkIPV6ENISource(TestNetworkENISource):
    conf_file = "examples/tests/network_source_ipv6.yaml"


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
