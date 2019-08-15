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


class XenialTestNetworkStatic(relbase.xenial, TestNetworkStaticAbs):
    __test__ = True


class BionicTestNetworkStatic(relbase.bionic, TestNetworkStaticAbs):
    __test__ = True


class DiscoTestNetworkStatic(relbase.disco, TestNetworkStaticAbs):
    __test__ = True


class EoanTestNetworkStatic(relbase.eoan, TestNetworkStaticAbs):
    __test__ = True


class Centos66TestNetworkStatic(centos_relbase.centos66_xenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True


class Centos70TestNetworkStatic(centos_relbase.centos70_xenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
