# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestNetworkBondingAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/bonding_network.yaml"

    def test_ifenslave_package_status(self):
        """ifenslave is expected installed in Ubuntu < artful."""
        rel = self.target_release
        pkg = "ifenslave"
        if rel in ("precise", "trusty", "xenial"):
            self.assertIn(
                pkg, self.debian_packages,
                "%s package expected in %s but not found" % (pkg, rel))
        else:
            self.assertNotIn(
                pkg, self.debian_packages,
                "%s package found but not expected in %s" % (pkg, rel))


class CentosTestNetworkBondingAbs(TestNetworkBondingAbs):
    extra_collect_scripts = TestNetworkBondingAbs.extra_collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
            rpm -qf `which ifenslave` |tee ifenslave_installed

            exit 0
        """)]

    def test_ifenslave_package_status(self):
        status = self.load_collect_file("ifenslave_installed")
        self.logger.debug('ifenslave installed: {}'.format(status))
        self.assertTrue('iputils' in status)

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


class XenialTestBonding(relbase.xenial, TestNetworkBondingAbs):
    __test__ = True


class BionicTestBonding(relbase.bionic, TestNetworkBondingAbs):
    __test__ = True


class DiscoTestBonding(relbase.disco, TestNetworkBondingAbs):
    __test__ = True


class EoanTestBonding(relbase.eoan, TestNetworkBondingAbs):
    __test__ = True


class Centos66TestNetworkBonding(centos_relbase.centos66_xenial,
                                 CentosTestNetworkBondingAbs):
    __test__ = True


class Centos70TestNetworkBonding(centos_relbase.centos70_xenial,
                                 CentosTestNetworkBondingAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
