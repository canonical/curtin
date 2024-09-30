# This file is part of curtin. See LICENSE file for copyright and license info.

from . import skip_if_flag
from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkOvsAbs(TestNetworkBaseTestsAbs):
    """ This class only needs to verify that when provided a v2 config
        that on Bionic+ openvswitch packages are installed. """
    conf_file = "examples/tests/network_v2_ovs.yaml"

    @skip_if_flag('expected_failure')
    def test_openvswitch_package_status(self):
        """openvswitch-switch is expected installed in Ubuntu >= bionic."""
        rel = self.target_release
        pkg = "openvswitch-switch"
        self.assertIn(
            pkg, self.debian_packages,
            "%s package expected in %s but not found" % (pkg, rel))

    @skip_if_flag('expected_failure')
    def test_etc_network_interfaces(self):
        pass

    @skip_if_flag('expected_failure')
    def test_ip_output(self):
        pass

    @skip_if_flag('expected_failure')
    def test_etc_resolvconf(self):
        pass

    @skip_if_flag('expected_failure')
    def test_bridge_params(self):
        pass


class BionicTestNetworkOvs(relbase.bionic, TestNetworkOvsAbs):
    __test__ = True


class FocalTestNetworkOvs(relbase.focal, TestNetworkOvsAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestNetworkOvs(relbase.jammy, TestNetworkOvsAbs):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
