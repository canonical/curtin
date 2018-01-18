from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestNetworkBondingAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/bonding_network.yaml"

    def test_ifenslave_installed(self):
        self.assertIn("ifenslave", self.debian_packages,
                      "ifenslave deb not installed")


class CentosTestNetworkBondingAbs(TestNetworkBondingAbs):
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"
    collect_scripts = TestNetworkBondingAbs.collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
            rpm -qf `which ifenslave` |tee ifenslave_installed
        """)]

    def test_ifenslave_installed(self):
        status = self.load_collect_file("ifenslave_installed")
        self.logger.debug('ifenslave installed: {}'.format(status))
        self.assertTrue('iputils' in status)

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


class TrustyTestBonding(relbase.trusty, TestNetworkBondingAbs):
    __test__ = False


class TrustyHWEVTestBonding(relbase.trusty_hwe_v, TrustyTestBonding):
    # Working, but off by default to save test suite runtime
    # oldest/newest HWE-* covered above/below
    __test__ = False


class TrustyHWEWTestBonding(relbase.trusty_hwe_w, TrustyTestBonding):
    # Working, but off by default to save test suite runtime
    # oldest/newest HWE-* covered above/below
    __test__ = False


class TrustyHWEXTestBonding(relbase.trusty_hwe_x, TrustyTestBonding):
    __test__ = True


class XenialTestBonding(relbase.xenial, TestNetworkBondingAbs):
    __test__ = True


class ArtfulTestBonding(relbase.artful, TestNetworkBondingAbs):
    __test__ = True

    def test_ifenslave_installed(self):
        """Artful should not have ifenslave installed."""
        pass

    def test_ifenslave_not_installed(self):
        """Confirm that ifenslave is not installed on artful"""
        self.assertNotIn('ifenslave', self.debian_packages,
                         "ifenslave is not expected in artful: %s" %
                         self.debian_packages.get('ifenslave'))


class BionicTestBonding(relbase.bionic, TestNetworkBondingAbs):
    __test__ = True

    def test_ifenslave_installed(self):
        """Bionic should not have ifenslave installed."""
        pass

    def test_ifenslave_not_installed(self):
        """Confirm that ifenslave is not installed on bionic"""
        self.assertNotIn('ifenslave', self.debian_packages,
                         "ifenslave is not expected in bionic: %s" %
                         self.debian_packages.get('ifenslave'))


class Centos66TestNetworkBonding(centos_relbase.centos66fromxenial,
                                 CentosTestNetworkBondingAbs):
    __test__ = True


class Centos70TestNetworkBonding(centos_relbase.centos70fromxenial,
                                 CentosTestNetworkBondingAbs):
    __test__ = True
