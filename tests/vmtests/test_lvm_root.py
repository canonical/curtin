# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import json
import os
import textwrap


class TestLvmRootAbs(VMBaseClass):
    conf_file = "examples/tests/lvmroot.yaml"
    test_type = 'storage'
    interactive = False
    rootfs_uuid = '04836770-e989-460f-8774-8e277ddcb40f'
    extra_disks = []
    dirty_disks = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        lsblk --json --fs -o KNAME,MOUNTPOINT,UUID,FSTYPE > lsblk.json
        lsblk --fs -P -o KNAME,MOUNTPOINT,UUID,FSTYPE > lsblk.out
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        pvdisplay > pvdisplay
        vgdisplay > vgdisplay
        lvdisplay > lvdisplay
        ls -al /dev/root_vg/ > dev_root_vg

        exit 0
        """)]
    conf_replace = {}

    def get_fstab_output(self):
        rootvg = self._dname_to_kname('root_vg-lv1_root')
        return [
            (self._kname_to_uuid_devpath('dm-uuid', rootvg), '/', 'defaults')
        ]

    def test_output_files_exist(self):
        self.output_files_exist(["fstab"])

    def test_rootfs_format(self):
        self.output_files_exist(["lsblk.json"])
        if os.path.getsize(self.collect_path('lsblk.json')) > 0:
            lsblk_data = json.load(open(self.collect_path('lsblk.json')))
            print(json.dumps(lsblk_data, indent=4))
            [entry] = [entry for entry in lsblk_data.get('blockdevices')
                       if entry['mountpoint'] == '/']
            print(entry)
            self.assertEqual(self.conf_replace['__ROOTFS_FORMAT__'],
                             entry['fstype'])
        else:
            # no json output on older releases
            self.output_files_exist(["lsblk.out"])
            lsblk_data = open(self.collect_path('lsblk.out')).readlines()
            print(lsblk_data)
            [root] = [line.strip() for line in lsblk_data
                      if 'MOUNTPOINT="/"' in line]
            print(root)
            [fstype] = [val.replace('"', '').split("=")[1]
                        for val in root.split() if 'FSTYPE' in val]
            print(fstype)
            self.assertEqual(self.conf_replace['__ROOTFS_FORMAT__'], fstype)


class Centos70XenialTestLvmRootExt4(centos_relbase.centos70_xenial,
                                    TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class Centos70XenialTestLvmRootXfs(centos_relbase.centos70_xenial,
                                   TestLvmRootAbs):
    __test__ = False
    conf_replace = {
        '__ROOTFS_FORMAT__': 'xfs',
    }


class XenialTestLvmRootExt4(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class FocalTestLvmRootExt4(relbase.focal, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class GroovyTestLvmRootExt4(relbase.groovy, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class XenialTestLvmRootXfs(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'xfs',
    }


class TestUefiLvmRootAbs(TestLvmRootAbs):
    conf_file = "examples/tests/uefi_lvmroot.yaml"
    uefi = True


class Centos70XenialTestUefiLvmRootExt4(centos_relbase.centos70_xenial,
                                        TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'ext4',
    }


class Centos70XenialTestUefiLvmRootXfs(centos_relbase.centos70_xenial,
                                       TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'xfs',
    }


class XenialTestUefiLvmRootExt4(relbase.xenial, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'ext4',
    }


class FocalTestUefiLvmRootExt4(relbase.focal, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'ext4',
    }


class GroovyTestUefiLvmRootExt4(relbase.groovy, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'ext4',
    }


class XenialTestUefiLvmRootXfs(relbase.xenial, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'xfs',
    }


@VMBaseClass.skip_by_date("1652822", fixby="2020-06-01", install=False)
class XenialTestUefiLvmRootXfsBootXfs(relbase.xenial, TestUefiLvmRootAbs):
    """This tests xfs root and xfs boot with uefi.

    It is known broken (LP: #1652822) and unlikely to be fixed without pushing,
    so we skip-by for a long time."""
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'xfs',
        '__ROOTFS_FORMAT__': 'xfs',
    }

# vi: ts=4 expandtab syntax=python
