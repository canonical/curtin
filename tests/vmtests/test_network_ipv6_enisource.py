from .releases import base_vm_classes as relbase
from .test_network_enisource import TestNetworkENISource

import unittest


class TestNetworkIPV6ENISource(TestNetworkENISource):
    conf_file = "examples/tests/network_source_ipv6.yaml"

    @unittest.skip("FIXME: cloud-init.net needs update")
    def test_etc_network_interfaces(self):
        pass


class PreciseTestNetworkIPV6ENISource(relbase.precise,
                                      TestNetworkIPV6ENISource):
    __test__ = False
    # not working, still debugging though; possible older ifupdown doesn't
    # like the multiple iface method.


class TrustyTestNetworkIPV6ENISource(relbase.trusty, TestNetworkIPV6ENISource):
    __test__ = True


class TrustyHWEXTestNetworkIPV6ENISource(relbase.trusty_hwe_x,
                                         TestNetworkIPV6ENISource):
    __test__ = True


class XenialTestNetworkIPV6ENISource(relbase.xenial, TestNetworkIPV6ENISource):
    __test__ = True

    @classmethod
    def test_ip_output(cls):
        cls.skip_by_date(cls.__name__, cls.release, bugnum="1701097",
                         fixby=(2017, 8, 16), removeby=(2017, 8, 31))


class ZestyTestNetworkIPV6ENISource(relbase.zesty, TestNetworkIPV6ENISource):
    __test__ = True

    @classmethod
    def test_ip_output(cls):
        cls.skip_by_date(cls.__name__, cls.release, bugnum="1701097",
                         fixby=(2017, 8, 16), removeby=(2017, 8, 31))


class ArtfulTestNetworkIPV6ENISource(relbase.artful, TestNetworkIPV6ENISource):
    __test__ = True

    @classmethod
    def test_ip_output(cls):
        cls.skip_by_date(cls.__name__, cls.release, bugnum="1701097",
                         fixby=(2017, 8, 16), removeby=(2017, 8, 31))
