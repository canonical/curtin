from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

import textwrap


class TestNetworkIPV6Abs(TestNetworkBaseTestsAbs):
    """ IPV6 complex testing.  The configuration exercises
        - ipv4 and ipv6 address on same interface
        - bonding in LACP mode
        - unconfigured subnets on bond
        - vlans over bonds
        - all IP is static
    """
    conf_file = "examples/network-ipv6-bond-vlan.yaml"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
        grep . -r /sys/class/net/bond0/ > sysfs_bond0 || :
        grep . -r /sys/class/net/bond0.108/ > sysfs_bond0.108 || :
        grep . -r /sys/class/net/bond0.208/ > sysfs_bond0.208 || :
        """)]


class PreciseHWETTestNetwork(relbase.precise_hwe_t, TestNetworkIPV6Abs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkIPV6(relbase.trusty, TestNetworkIPV6Abs):
    __test__ = True


class TrustyHWEVTestNetworkIPV6(relbase.trusty_hwe_v, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkIPV6(relbase.trusty_hwe_w, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEXTestNetworkIPV6(relbase.trusty_hwe_x, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkIPV6(relbase.xenial, TestNetworkIPV6Abs):
    __test__ = True


class YakketyTestNetworkIPV6(relbase.yakkety, TestNetworkIPV6Abs):
    __test__ = True


class ZestyTestNetworkIPV6(relbase.zesty, TestNetworkIPV6Abs):
    __test__ = True


class ArtfulTestNetworkIPV6(relbase.artful, TestNetworkIPV6Abs):
    __test__ = True
