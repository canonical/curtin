# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network import TestNetworkBaseTestsAbs
from unittest import SkipTest
import textwrap


class TestNetworkAliasAbs(TestNetworkBaseTestsAbs):
    """ Multi-ip address network testing
    """
    conf_file = "examples/tests/network_alias.yaml"

    def test_etc_network_interfaces(self):
        reason = ("%s: cloud-init and curtin eni rendering"
                  " differ" % (self.__class__))
        raise SkipTest(reason)


class CentosTestNetworkAliasAbs(TestNetworkAliasAbs):
    extra_collect_scripts = TestNetworkAliasAbs.extra_collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init

            exit 0
        """)]

    def test_etc_resolvconf(self):
        pass


class Centos70TestNetworkAlias(centos_relbase.centos70_xenial,
                               CentosTestNetworkAliasAbs):
    __test__ = True


class XenialTestNetworkAlias(relbase.xenial, TestNetworkAliasAbs):
    __test__ = True


class BionicTestNetworkAlias(relbase.bionic, TestNetworkAliasAbs):
    __test__ = True


class FocalTestNetworkAlias(relbase.focal, TestNetworkAliasAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestNetworkAlias(relbase.jammy, TestNetworkAliasAbs):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
