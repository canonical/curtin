from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkPassthroughAbs(TestNetworkBaseTestsAbs):
    """ Multi-ip address network testing
    """
    conf_file = "examples/tests/network_passthrough.yaml"

    # FIXME: cloud-init and curtin eni rendering differ
    def test_etc_network_interfaces(self):
        pass


class PreciseHWETTestNetworkPassthrough(relbase.precise_hwe_t,
                                        TestNetworkPassthroughAbs):
    # cloud-init too old
    __test__ = False


class TrustyTestNetworkPassthrough(relbase.trusty, TestNetworkPassthroughAbs):
    # cloud-init too old
    __test__ = False


class XenialTestNetworkPassthrough(relbase.xenial, TestNetworkPassthroughAbs):
    __test__ = True


class YakketyTestNetworkPassthrough(relbase.yakkety,
                                    TestNetworkPassthroughAbs):
    __test__ = True


class ZestyTestNetworkPassthrough(relbase.zesty, TestNetworkPassthroughAbs):
    __test__ = True
