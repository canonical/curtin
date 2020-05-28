# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import os
import textwrap


class TestLvmPreserveAbs(VMBaseClass):
    conf_file = "examples/tests/preserve-lvm.yaml"
    test_type = 'storage'
    interactive = False
    extra_disks = ['10G']
    dirty_disks = False
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
        ls / > ls-root

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
            self.assertEqual('ext4', entry['fstype'])
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
            self.assertEqual('ext4', fstype)

    def test_preserved_data_exists(self):
        self.assertIn('existing', self.load_collect_file('ls-root'))


class BionicTestLvmPreserve(relbase.bionic, TestLvmPreserveAbs):
    __test__ = True


class EoanTestLvmPreserve(relbase.eoan, TestLvmPreserveAbs):
    __test__ = True


class FocalTestLvmPreserve(relbase.focal, TestLvmPreserveAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
