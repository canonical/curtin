from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkStaticAbs(TestNetworkBaseTestsAbs):
    """ Static network testing with ipv4
    """
    conf_file = "examples/tests/basic_network_static.yaml"


class PreciseHWETTestNetworkStatic(relbase.precise_hwe_t,
                                   TestNetworkStaticAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkStatic(relbase.trusty, TestNetworkStaticAbs):
    __test__ = True


class TrustyHWEUTestNetworkStatic(relbase.trusty_hwe_u,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkStatic(relbase.trusty_hwe_v,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkStatic(relbase.trusty_hwe_w,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkStatic(relbase.xenial, TestNetworkStaticAbs):
    __test__ = True


class YakketyTestNetworkStatic(relbase.yakkety, TestNetworkStaticAbs):
    __test__ = True
