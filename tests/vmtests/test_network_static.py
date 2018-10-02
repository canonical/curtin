# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkStaticAbs(TestNetworkBaseTestsAbs):
    """ Static network testing with ipv4
    """
    conf_file = "examples/tests/basic_network_static.yaml"


class CentosTestNetworkStaticAbs(TestNetworkStaticAbs):

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


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


class TrustyHWEXTestNetworkStatic(relbase.trusty_hwe_x,
                                  TrustyTestNetworkStatic):
    __test__ = True


class XenialTestNetworkStatic(relbase.xenial, TestNetworkStaticAbs):
    __test__ = True


class BionicTestNetworkStatic(relbase.bionic, TestNetworkStaticAbs):
    __test__ = True


class CosmicTestNetworkStatic(relbase.cosmic, TestNetworkStaticAbs):
    __test__ = True


class Centos66TestNetworkStatic(centos_relbase.centos66_xenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True


class Centos70TestNetworkStatic(centos_relbase.centos70_xenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
