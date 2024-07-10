# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network_static import (TestNetworkStaticAbs,
                                  CentosTestNetworkStaticAbs)


# reuse basic network tests but with different config (static, no dhcp)
class TestNetworkIPV6StaticAbs(TestNetworkStaticAbs):
    conf_file = "examples/tests/basic_network_static_ipv6.yaml"


class CentosTestNetworkIPV6StaticAbs(CentosTestNetworkStaticAbs):
    conf_file = "examples/tests/basic_network_static_ipv6.yaml"


class XenialTestNetworkIPV6Static(relbase.xenial, TestNetworkIPV6StaticAbs):
    __test__ = True


class BionicTestNetworkIPV6Static(relbase.bionic, TestNetworkIPV6StaticAbs):
    __test__ = True


class FocalTestNetworkIPV6Static(relbase.focal, TestNetworkIPV6StaticAbs):
    __test__ = True


class HirsuteTestNetworkIPV6Static(relbase.hirsute, TestNetworkIPV6StaticAbs):
    __test__ = True


class ImpishTestNetworkIPV6Static(relbase.impish, TestNetworkIPV6StaticAbs):
    __test__ = True


class JammyTestNetworkIPV6Static(relbase.jammy, TestNetworkIPV6StaticAbs):
    __test__ = True


class Centos70TestNetworkIPV6Static(centos_relbase.centos70_xenial,
                                    CentosTestNetworkIPV6StaticAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
