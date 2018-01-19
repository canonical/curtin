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


class TrustyTestNetworkIPV6Static(relbase.trusty, TestNetworkIPV6StaticAbs):
    __test__ = True


class TrustyHWEUTestNetworkIPV6Static(relbase.trusty_hwe_u,
                                      TestNetworkIPV6StaticAbs):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEVTestNetworkIPV6Static(relbase.trusty_hwe_v,
                                      TestNetworkIPV6StaticAbs):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEWTestNetworkIPV6Static(relbase.trusty_hwe_w,
                                      TestNetworkIPV6StaticAbs):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEXTestNetworkIPV6Static(relbase.trusty_hwe_x,
                                      TestNetworkIPV6StaticAbs):
    __test__ = True


class XenialTestNetworkIPV6Static(relbase.xenial, TestNetworkIPV6StaticAbs):
    __test__ = True


class ArtfulTestNetworkIPV6Static(relbase.artful, TestNetworkIPV6StaticAbs):
    __test__ = True


class BionicTestNetworkIPV6Static(relbase.bionic, TestNetworkIPV6StaticAbs):
    __test__ = True


class Centos66TestNetworkIPV6Static(centos_relbase.centos66fromxenial,
                                    CentosTestNetworkIPV6StaticAbs):
    __test__ = True


class Centos70TestNetworkIPV6Static(centos_relbase.centos70fromxenial,
                                    CentosTestNetworkIPV6StaticAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
