from .releases import base_vm_classes as relbase
from .test_lvm import TestLvmAbs
from .test_iscsi import TestBasicIscsiAbs

import textwrap


class TestLvmIscsiAbs(TestLvmAbs, TestBasicIscsiAbs):
    interactive = False
    iscsi_disks = [
        {'size': '6G'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/lvm_iscsi.yaml"
    nr_testfiles = 4

    collect_scripts = TestLvmAbs.collect_scripts
    collect_scripts += TestBasicIscsiAbs.collect_scripts + [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        ls -al /sys/class/block/dm*/slaves/  > dm_slaves
        """)]

    fstab_expected = {
        'UUID=6de56115-9500-424b-8151-221b270ec708': '/mnt/iscsi1',
        'UUID=9604e4c4-e5ae-40dd-ab1f-940de6b59047': '/mnt/iscsi2',
        'UUID=18bec31c-09a8-4a02-91c6-e9bf6efb6fad': '/mnt/iscsi3',
        'UUID=a98f706b-b064-4682-8eb2-6c2c1284060c': '/mnt/iscsi4',
    }
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 5),
                     ('main_disk', 6),
                     ('vg1-lv1', 0),
                     ('vg1-lv2', 0),
                     ('vg2-lv3', 0),
                     ('vg2-lv4', 0)]

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv1=vg1")
        self.check_file_strippedline("lvs", "lv2=vg1")
        self.check_file_strippedline("lvs", "lv3=vg2")
        self.check_file_strippedline("lvs", "lv4=vg2")

    def test_pvs(self):
        self.check_file_strippedline("pvs", "vg1=/dev/sda5")
        self.check_file_strippedline("pvs", "vg1=/dev/sda6")
        self.check_file_strippedline("pvs", "vg2=/dev/sdb5")
        self.check_file_strippedline("pvs", "vg2=/dev/sdb6")


class TrustyTestIscsiLvm(relbase.trusty, TestLvmIscsiAbs):
    __test__ = True


class XenialTestIscsiLvm(relbase.xenial, TestLvmIscsiAbs):
    __test__ = True


class ZestyTestIscsiLvm(relbase.zesty, TestLvmIscsiAbs):
    __test__ = True


class ArtfulTestIscsiLvm(relbase.artful, TestLvmIscsiAbs):
    __test__ = True


class BionicTestIscsiLvm(relbase.bionic, TestLvmIscsiAbs):
    __test__ = True
