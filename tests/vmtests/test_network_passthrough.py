from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs


class TestNetworkPassthroughAbs(TestNetworkBaseTestsAbs):
    """ Multi-ip address network testing
    """
    conf_file = "examples/tests/network_passthrough.yaml"

    # FIXME: cloud-init and curtin eni rendering differ
    def test_etc_network_interfaces(self):
        pass


class TestNetworkV2PassthroughAbs(TestNetworkPassthroughAbs):
    """Test network passthrough with v2 netconfig"""
    conf_file = "examples/tests/network_v2_passthrough.yaml"

    # FIXME: need methods here and in TestNetworkPassthroughAbs to verify
    #        correctness of cloud-init's network config v2 support
    # FIXME: need to create a network state object from v2 config in order to
    #        verify everything properly here
    def test_etc_resolvconf(self):
        pass

    def test_ip_output(self):
        pass


class PreciseHWETTestNetworkPassthrough(relbase.precise_hwe_t,
                                        TestNetworkPassthroughAbs):
    # cloud-init too old
    __test__ = False


class TrustyTestNetworkPassthrough(relbase.trusty, TestNetworkPassthroughAbs):
    # cloud-init too old
    __test__ = False


class XenialTestNetworkPassthrough(relbase.xenial, TestNetworkPassthroughAbs):
    __test__ = True


class YakketyTestNetworkPassthrough(relbase.yakkety,
                                    TestNetworkPassthroughAbs):
    __test__ = True


class ZestyTestNetworkPassthrough(relbase.zesty, TestNetworkPassthroughAbs):
    __test__ = True


class ArtfulTestNetworkPassthrough(relbase.artful, TestNetworkPassthroughAbs):
    __test__ = True


class XenialTestNetworkV2Passthrough(relbase.xenial,
                                     TestNetworkV2PassthroughAbs):
    __test__ = True
    required_net_ifaces = ['52:54:00:12:34:00']


class YakketyTestNetworkV2Passthrough(relbase.yakkety,
                                      TestNetworkV2PassthroughAbs):
    __test__ = True
    required_net_ifaces = ['52:54:00:12:34:00']


class ZestyTestNetworkV2Passthrough(relbase.zesty,
                                    TestNetworkV2PassthroughAbs):
    __test__ = True
    required_net_ifaces = ['52:54:00:12:34:00']


class ArtfulTestNetworkV2Passthrough(relbase.artful,
                                     TestNetworkV2PassthroughAbs):
    __test__ = True
    required_net_ifaces = ['52:54:00:12:34:00']
