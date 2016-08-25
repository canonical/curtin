from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkAliasAbs(TestNetworkBaseTestsAbs):
    """ Multi-ip address network testing
    """
    conf_file = "examples/tests/network_alias.yaml"


class PreciseHWETTestNetworkAlias(relbase.precise_hwe_t, TestNetworkAliasAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = True


class TrustyTestNetworkAlias(relbase.trusty, TestNetworkAliasAbs):
    __test__ = True


class TrustyHWEUTestNetworkAlias(relbase.trusty_hwe_u, TrustyTestNetworkAlias):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkAlias(relbase.trusty_hwe_v, TrustyTestNetworkAlias):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkAlias(relbase.trusty_hwe_w, TrustyTestNetworkAlias):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkAlias(relbase.xenial, TestNetworkAliasAbs):
    __test__ = True


class YakketyTestNetworkAlias(relbase.yakkety, TestNetworkAliasAbs):
    __test__ = True
