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
    collect_scripts = TestNetworkAliasAbs.collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
        """)]

    def test_etc_resolvconf(self):
        pass


class Centos66TestNetworkAlias(centos_relbase.centos66fromxenial,
                               CentosTestNetworkAliasAbs):
    __test__ = True


class Centos70TestNetworkAlias(centos_relbase.centos70fromxenial,
                               CentosTestNetworkAliasAbs):
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


class TrustyHWEXTestNetworkAlias(relbase.trusty_hwe_x, TrustyTestNetworkAlias):
    __test__ = True


class XenialTestNetworkAlias(relbase.xenial, TestNetworkAliasAbs):
    __test__ = True


class ArtfulTestNetworkAlias(relbase.artful, TestNetworkAliasAbs):
    __test__ = True


class BionicTestNetworkAlias(relbase.bionic, TestNetworkAliasAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
