from . import logger
from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

import textwrap


class TestNetworkBondingAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/bonding_network.yaml"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        dpkg-query -W -f '${Status}' ifenslave > ifenslave_installed
        """)]

    def test_output_files_exist_ifenslave(self):
        self.output_files_exist(["ifenslave_installed"])

    def test_ifenslave_installed(self):
        status = self.load_collect_file("ifenslave_installed")
        logger.debug('ifenslave installed: {}'.format(status))
        self.assertEqual('install ok installed', status)


class PreciseHWETTestBonding(relbase.precise_hwe_t, TestNetworkBondingAbs):
    __test__ = True
    # package names on precise are different, need to check on ifenslave-2.6
    collect_scripts = TestNetworkBondingAbs.collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        dpkg-query -W -f '${Status}' ifenslave-2.6 > ifenslave_installed
        """)]


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


class WilyTestBonding(relbase.wily, TestNetworkBondingAbs):
    # EOL - 2016-07-28
    __test__ = False


class XenialTestBonding(relbase.xenial, TestNetworkBondingAbs):
    __test__ = True


class YakketyTestBonding(relbase.yakkety, TestNetworkBondingAbs):
    __test__ = True


class ZestyTestBonding(relbase.zesty, TestNetworkBondingAbs):
    __test__ = True
