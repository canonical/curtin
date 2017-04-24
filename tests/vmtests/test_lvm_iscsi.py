from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestLvmIscsiAbs(VMBaseClass):
    interactive = False
    iscsi_disks = [
        {'size': '6G'}]
    conf_file = "examples/tests/lvm_iscsi.yaml"

    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        cat /mnt/iscsi1/testfile > testfile1
        cat /mnt/iscsi2/testfile > testfile2
        """)]

    def test_output_files_exist(self):
        # add check by SN or UUID that the iSCSI disks are attached?
        self.output_files_exist(["fstab", "testfile1", "testfile2"])


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
