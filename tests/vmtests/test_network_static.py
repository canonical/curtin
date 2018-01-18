from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network import TestNetworkBaseTestsAbs
import textwrap


class TestNetworkStaticAbs(TestNetworkBaseTestsAbs):
    """ Static network testing with ipv4
    """
    conf_file = "examples/tests/basic_network_static.yaml"


class CentosTestNetworkStaticAbs(TestNetworkStaticAbs):
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
        """)]

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


class TrustyTestNetworkStatic(relbase.trusty, TestNetworkStaticAbs):
    __test__ = True


class TrustyHWEUTestNetworkStatic(relbase.trusty_hwe_u,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkStatic(relbase.trusty_hwe_v,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkStatic(relbase.trusty_hwe_w,
                                  TrustyTestNetworkStatic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEXTestNetworkStatic(relbase.trusty_hwe_x,
                                  TrustyTestNetworkStatic):
    __test__ = True


class XenialTestNetworkStatic(relbase.xenial, TestNetworkStaticAbs):
    __test__ = True


class ArtfulTestNetworkStatic(relbase.artful, TestNetworkStaticAbs):
    __test__ = True


class BionicTestNetworkStatic(relbase.bionic, TestNetworkStaticAbs):
    __test__ = True


class Centos66TestNetworkStatic(centos_relbase.centos66fromxenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True


class Centos70TestNetworkStatic(centos_relbase.centos70fromxenial,
                                CentosTestNetworkStaticAbs):
    __test__ = True
