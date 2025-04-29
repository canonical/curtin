# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network_vlan import (TestNetworkVlanAbs,
                                CentosTestNetworkVlanAbs)


class TestNetworkIPV6VlanAbs(TestNetworkVlanAbs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"


class CentosTestNetworkIPV6VlanAbs(CentosTestNetworkVlanAbs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"


class XenialTestNetworkIPV6Vlan(relbase.xenial, TestNetworkIPV6VlanAbs):
    __test__ = True


class BionicTestNetworkIPV6Vlan(relbase.bionic, TestNetworkIPV6VlanAbs):
    __test__ = True


class FocalTestNetworkIPV6Vlan(relbase.focal, TestNetworkIPV6VlanAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestNetworkIPV6Vlan(relbase.jammy, TestNetworkIPV6VlanAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class Centos70TestNetworkIPV6Vlan(centos_relbase.centos70_xenial,
                                  CentosTestNetworkIPV6VlanAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
