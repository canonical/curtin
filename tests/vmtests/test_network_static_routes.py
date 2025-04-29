# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network import (TestNetworkBaseTestsAbs,
                           CentosTestNetworkBasicAbs)


class TestNetworkStaticRoutesAbs(TestNetworkBaseTestsAbs):
    """ Static network routes testing with ipv4
    """
    conf_file = "examples/tests/network_static_routes.yaml"


class CentosTestNetworkStaticRoutesAbs(CentosTestNetworkBasicAbs):
    """ Static network routes testing with ipv4
    """
    conf_file = "examples/tests/network_static_routes.yaml"


class XenialTestNetworkStaticRoutes(relbase.xenial,
                                    TestNetworkStaticRoutesAbs):
    __test__ = True


class BionicTestNetworkStaticRoutes(relbase.bionic,
                                    TestNetworkStaticRoutesAbs):
    __test__ = True


class FocalTestNetworkStaticRoutes(relbase.focal,
                                   TestNetworkStaticRoutesAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestNetworkStaticRoutes(relbase.jammy,
                                   TestNetworkStaticRoutesAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class Centos70TestNetworkStaticRoutes(centos_relbase.centos70_xenial,
                                      CentosTestNetworkStaticRoutesAbs):
    __test__ = False

# vi: ts=4 expandtab syntax=python
