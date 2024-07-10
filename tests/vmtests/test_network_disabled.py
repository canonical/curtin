# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

from unittest import SkipTest

import os


class CurtinDisableNetworkRendering(TestNetworkBaseTestsAbs):
    """ Test that curtin does not passthrough network config when
    networking is disabled."""
    conf_file = "examples/tests/network_disabled.yaml"

    def test_cloudinit_network_not_created(self):
        cc_passthrough = "cloud.cfg.d/50-curtin-networking.cfg"

        pt_file = os.path.join(self.td.collect, 'etc_cloud',
                               cc_passthrough)
        self.assertFalse(os.path.exists(pt_file))

    def test_cloudinit_network_passthrough(self):
        raise SkipTest('not available on %s' % self.__class__)

    def test_static_routes(self):
        raise SkipTest('not available on %s' % self.__class__)

    def test_ip_output(self):
        raise SkipTest('not available on %s' % self.__class__)

    def test_etc_resolvconf(self):
        raise SkipTest('not available on %s' % self.__class__)


TestKlass1 = CurtinDisableNetworkRendering


class CurtinDisableCloudInitNetworking(TestNetworkBaseTestsAbs):
    """ Test curtin can disable cloud-init networking in the target system """
    conf_file = "examples/tests/network_config_disabled.yaml"

    def test_etc_resolvconf(self):
        raise SkipTest('not available on %s' % self.__class__)

    def test_ip_output(self):
        raise SkipTest('not available on %s' % self.__class__)


TestKlass2 = CurtinDisableCloudInitNetworking


class CurtinDisableCloudInitNetworkingVersion1(TestKlass2):
    """ Test curtin can disable cloud-init networking in the target system
    with version key. """
    conf_file = "examples/tests/network_config_disabled_with_version.yaml"


TestKlass3 = CurtinDisableCloudInitNetworkingVersion1


class FocalCurtinDisableNetworkRendering(relbase.focal, TestKlass1):
    __test__ = True


class HirsuteCurtinDisableNetworkRendering(relbase.hirsute, TestKlass1):
    __test__ = True


class ImpishCurtinDisableNetworkRendering(relbase.impish, TestKlass1):
    __test__ = True


class JammyCurtinDisableNetworkRendering(relbase.jammy, TestKlass1):
    __test__ = True


class FocalCurtinDisableCloudInitNetworking(relbase.focal, TestKlass2):
    __test__ = True


class HirsuteCurtinDisableCloudInitNetworking(relbase.hirsute, TestKlass2):
    __test__ = True


class ImpishCurtinDisableCloudInitNetworking(relbase.impish, TestKlass2):
    __test__ = True


class JammyCurtinDisableCloudInitNetworking(relbase.jammy, TestKlass2):
    __test__ = True


class FocalCurtinDisableCloudInitNetworkingVersion1(relbase.focal, TestKlass3):
    __test__ = True


class HirsuteCurtinDisableCloudInitNetworkingVersion1(relbase.hirsute,
                                                      TestKlass3):
    __test__ = True


class ImpishCurtinDisableCloudInitNetworkingVersion1(relbase.impish,
                                                     TestKlass3):
    __test__ = True


class JammyCurtinDisableCloudInitNetworkingVersion1(relbase.jammy,
                                                    TestKlass3):
    __test__ = True


# vi: ts=4 expandtab syntax=python
