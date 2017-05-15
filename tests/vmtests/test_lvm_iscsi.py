from .releases import base_vm_classes as relbase
from .test_lvm import TestLvmAbs
from .test_iscsi import TestBasicIscsiAbs

import textwrap


class TestLvmIscsiAbs(TestBasicIscsiAbs, TestLvmAbs):
    interactive = False
    iscsi_disks = [
        {'size': '6G'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/lvm_iscsi.yaml"

    collect_scripts = TestBasicIscsiAbs.collect_scripts + [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        ls -al /sys/class/block/dm*/slaves/  > dm_slaves
        """)]


class PreciseTestIscsiLvm(relbase.precise, TestLvmIscsiAbs):
    __test__ = True


class TrustyTestIscsiLvm(relbase.trusty, TestLvmIscsiAbs):
    __test__ = True


class XenialTestIscsiLvm(relbase.xenial, TestLvmIscsiAbs):
    __test__ = True


class YakketyTestIscsiLvm(relbase.yakkety, TestLvmIscsiAbs):
    __test__ = True


class ZestyTestIscsiLvm(relbase.zesty, TestLvmIscsiAbs):
    __test__ = True
