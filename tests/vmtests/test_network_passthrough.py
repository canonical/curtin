from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkPassthroughAbs(TestNetworkBaseTestsAbs):
    """ Multi-ip address network testing
    """
    conf_file = "examples/tests/network_passthrough.yaml"


class PreciseHWETTestNetworkPassthrough(relbase.precise_hwe_t,
                                        TestNetworkPassthroughAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = True


class TrustyTestNetworkPassthrough(relbase.trusty, TestNetworkPassthroughAbs):
    __test__ = True


class TrustyHWEUTestNetworkPassthrough(relbase.trusty_hwe_u,
                                       TrustyTestNetworkPassthrough):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkPassthrough(relbase.trusty_hwe_v,
                                       TrustyTestNetworkPassthrough):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkPassthrough(relbase.trusty_hwe_w,
                                       TrustyTestNetworkPassthrough):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkPassthrough(relbase.xenial, TestNetworkPassthroughAbs):
    __test__ = True


class YakketyTestNetworkPassthrough(relbase.yakkety,
                                    TestNetworkPassthroughAbs):
    __test__ = True
