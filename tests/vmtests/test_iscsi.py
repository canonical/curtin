from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestBasicIscsiAbs(VMBaseClass):
    interactive = False
    iscsi_disks = [
        {'size': '3G'},
        {'size': '4G', 'auth': 'user:passw0rd'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'},
        {'size': '6G', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/basic_iscsi.yaml"

    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        cat /mnt/iscsi1/testfile > testfile1
        cat /mnt/iscsi2/testfile > testfile2
        cat /mnt/iscsi3/testfile > testfile3
        cat /mnt/iscsi4/testfile > testfile4
        """)]

    def test_output_files_exist(self):
        # add check by SN or UUID that the iSCSI disks are attached?
        self.output_files_exist(["fstab", "testfile1", "testfile2",
                                 "testfile3", "testfile4"])


class PreciseTestIscsiBasic(relbase.precise, TestBasicIscsiAbs):
    __test__ = True


class TrustyTestIscsiBasic(relbase.trusty, TestBasicIscsiAbs):
    __test__ = True


class XenialTestIscsiBasic(relbase.xenial, TestBasicIscsiAbs):
    __test__ = True


class YakketyTestIscsiBasic(relbase.yakkety, TestBasicIscsiAbs):
    __test__ = True


class ZestyTestIscsiBasic(relbase.zesty, TestBasicIscsiAbs):
    __test__ = True
