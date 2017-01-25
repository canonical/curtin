from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkStaticRoutesAbs(TestNetworkBaseTestsAbs):
    """ Static network routes testing with ipv4
    """
    conf_file = "examples/tests/network_static_routes.yaml"


class PreciseHWETTestNetworkStaticRoutes(relbase.precise_hwe_t,
                                         TestNetworkStaticRoutesAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkStaticRoutes(relbase.trusty,
                                    TestNetworkStaticRoutesAbs):
    __test__ = True


class TrustyHWEUTestNetworkStaticRoutes(relbase.trusty_hwe_u,
                                        TrustyTestNetworkStaticRoutes):
    # Working, off by default to save test suite runtime, covered by
    # TrustyTestNetworkStaticRoutes
    __test__ = False


class TrustyHWEVTestNetworkStaticRoutes(relbase.trusty_hwe_v,
                                        TrustyTestNetworkStaticRoutes):
    # Working, off by default to save test suite runtime, covered by
    # TrustyTestNetworkStaticRoutes
    __test__ = False


class TrustyHWEWTestNetworkStaticRoutes(relbase.trusty_hwe_w,
                                        TrustyTestNetworkStaticRoutes):
    # Working, off by default to save test suite runtime, covered by
    # TrustyTestNetworkStaticRoutes
    __test__ = False


class XenialTestNetworkStaticRoutes(relbase.xenial,
                                    TestNetworkStaticRoutesAbs):
    __test__ = True


class YakketyTestNetworkStaticRoutes(relbase.yakkety,
                                     TestNetworkStaticRoutesAbs):
    __test__ = True
