# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_multipath import TestMultipathBasicAbs

from unittest import SkipTest
import textwrap


class TestMultipathLvmAbs(TestMultipathBasicAbs):
    conf_file = "examples/tests/multipath-lvm.yaml"
    dirty_disks = False
    test_type = 'storage'
    multipath = True
    multipath_num_paths = 4
    disk_driver = 'scsi-hd'
    extra_disks = []
    nvme_disks = []
    extra_collect_scripts = TestMultipathBasicAbs.extra_collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        pvs > pvs.out
        vgs > vgs.out
        lvs > lvs.out
        exit 0
        """)]

    def test_home_mount_unit(self):
        raise SkipTest('Test case does not have separate home mount')

    def get_fstab_expected(self):
        root = self._dname_to_kname('root_vg-lv1_root')
        boot = self._dname_to_kname('root_disk-part2')
        return [
            (self._kname_to_uuid_devpath('dm-uuid-LVM', root),
             '/', 'defaults'),
            (self._kname_to_uuid_devpath('dm-uuid-part2-mpath', boot),
             '/boot', 'defaults')]

    def test_proc_command_line_has_mp_device(self):
        cmdline = self.load_collect_file('proc_cmdline')
        root = [tok for tok in cmdline.split() if tok.startswith('root=')]
        self.assertEqual(len(root), 1)
        root = root.pop()
        root = root.split('root=')[1]
        self.assertEqual('/dev/mapper/root_vg-lv1_root', root)


class Centos70TestMultipathLvm(centos_relbase.centos70_bionic,
                               TestMultipathLvmAbs):
    __test__ = True


class BionicTestMultipathLvm(relbase.bionic, TestMultipathLvmAbs):
    __test__ = True


class FocalTestMultipathLvm(relbase.focal, TestMultipathLvmAbs):
    __test__ = True


class GroovyTestMultipathLvm(relbase.groovy, TestMultipathLvmAbs):
    __test__ = True


class TestMultipathLvmPartWipeAbs(TestMultipathLvmAbs):
    conf_file = "examples/tests/multipath-lvm-part-wipe.yaml"


class FocalTestMultipathLvmPartWipe(relbase.focal,
                                    TestMultipathLvmPartWipeAbs):
    __test__ = True


class GroovyTestMultipathLvmPartWipe(relbase.groovy,
                                     TestMultipathLvmPartWipeAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
