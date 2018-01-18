from .releases import base_vm_classes as relbase
from .test_network_enisource import TestNetworkENISource

import unittest


class TestNetworkIPV6ENISource(TestNetworkENISource):
    conf_file = "examples/tests/network_source_ipv6.yaml"

    @unittest.skip("FIXME: cloud-init.net needs update")
    def test_etc_network_interfaces(self):
        pass


class TrustyTestNetworkIPV6ENISource(relbase.trusty, TestNetworkIPV6ENISource):
    __test__ = True


class TrustyHWEXTestNetworkIPV6ENISource(relbase.trusty_hwe_x,
                                         TestNetworkIPV6ENISource):
    __test__ = True


class XenialTestNetworkIPV6ENISource(relbase.xenial, TestNetworkIPV6ENISource):
    __test__ = True


# Artful and later are deliberately not present.  They do not have ifupdown.
