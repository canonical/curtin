# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
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
    extra_collect_scripts = TestNetworkBaseTestsAbs.extra_collect_scripts + [
        textwrap.dedent("""
        grep . -r /sys/class/net/bond0/ > sysfs_bond0 || :
        grep . -r /sys/class/net/bond0.108/ > sysfs_bond0.108 || :
        grep . -r /sys/class/net/bond0.208/ > sysfs_bond0.208 || :
        """)]


class CentosTestNetworkIPV6Abs(TestNetworkIPV6Abs):
    extra_collect_scripts = TestNetworkIPV6Abs.extra_collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
        """)]

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


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


class BionicTestNetworkIPV6(relbase.bionic, TestNetworkIPV6Abs):
    __test__ = True


class CosmicTestNetworkIPV6(relbase.cosmic, TestNetworkIPV6Abs):
    __test__ = True


class Centos66TestNetworkIPV6(centos_relbase.centos66_xenial,
                              CentosTestNetworkIPV6Abs):
    __test__ = True


class Centos70TestNetworkIPV6(centos_relbase.centos70_xenial,
                              CentosTestNetworkIPV6Abs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
