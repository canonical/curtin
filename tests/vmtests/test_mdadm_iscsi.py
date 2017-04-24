from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestMdadmIscsiAbs(VMBaseClass):
    interactive = False
    iscsi_disks = [
        {'size': '5G', 'auth': 'user:passw0rd'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'},
        {'size': '5G', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/mdadm_iscsi.yaml"

    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        cat /mnt/iscsi1/testfile > testfile1
        """)]

    def test_output_files_exist(self):
        # add check by SN or UUID that the iSCSI disks are attached?
        self.output_files_exist(["fstab", "testfile1"])


class PreciseTestIscsiMdadm(relbase.precise, TestMdadmIscsiAbs):
    __test__ = True


class TrustyTestIscsiMdadm(relbase.trusty, TestMdadmIscsiAbs):
    __test__ = True


class XenialTestIscsiMdadm(relbase.xenial, TestMdadmIscsiAbs):
    __test__ = True


class YakketyTestIscsiMdadm(relbase.yakkety, TestMdadmIscsiAbs):
    __test__ = True


class ZestyTestIscsiMdadm(relbase.zesty, TestMdadmIscsiAbs):
    __test__ = True
