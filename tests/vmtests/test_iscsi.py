from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestBasicIscsiAbs(VMBaseClass):
    interactive = False
    iscsi_disks = ['3G']
    conf_file = "examples/tests/basic_iscsi.yaml"

    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        cat /etc/iscsi/nodes/*/*/default > target_node
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        cat /mnt/iscsi/testfile > testfile
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["fstab", "target_node", "testfile"])


class PreciseTestIscsiBasic(relbase.precise, TestBasicIscsiAbs):
    __test__ = True


class TrustyTestIscsiBasic(relbase.trusty, TestBasicIscsiAbs):
    __test__ = True


class XenialTestIscsiBasic(relbase.xenial, TestBasicIscsiAbs):
    __test__ = True


class YakketyTestIscsiBasic(relbase.yakkety, TestBasicIscsiAbs):
    __test__ = True
