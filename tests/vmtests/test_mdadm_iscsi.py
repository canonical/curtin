from .releases import base_vm_classes as relbase
from .test_mdadm_bcache import TestMdadmAbs
from .test_iscsi import TestBasicIscsiAbs

import textwrap


class TestMdadmIscsiAbs(TestMdadmAbs, TestBasicIscsiAbs):
    interactive = False
    iscsi_disks = [
        {'size': '5G', 'auth': 'user:passw0rd'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'},
        {'size': '5G', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/mdadm_iscsi.yaml"
    nr_testfiles = 1

    collect_scripts = TestMdadmAbs.collect_scripts
    collect_scripts += TestBasicIscsiAbs.collect_scripts + [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        ls -al /sys/class/block/md*/slaves/  > md_slaves
        """)]


class TrustyTestIscsiMdadm(relbase.trusty, TestMdadmIscsiAbs):
    __test__ = True


class XenialTestIscsiMdadm(relbase.xenial, TestMdadmIscsiAbs):
    __test__ = True


class ZestyTestIscsiMdadm(relbase.zesty, TestMdadmIscsiAbs):
    __test__ = True


class ArtfulTestIscsiMdadm(relbase.artful, TestMdadmIscsiAbs):
    __test__ = True
