from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import textwrap


class TestLvmRootAbs(VMBaseClass):
    conf_file = "examples/tests/lvmroot.yaml"
    interactive = False
    rootfs_uuid = '04836770-e989-460f-8774-8e277ddcb40f'
    extra_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        lsblk --json --fs -o KNAME,MOUNTPOINT,UUID,FSTYPE > lsblk.json
        ls -al /dev/disk/by-dname > ls_al_dname
        ls -al /dev/disk/by-id > ls_al_byid
        ls -al /dev/disk/by-uuid > ls_al_byuuid
        ls -al /dev/mapper > ls_al_dev_mapper
        find /etc/network/interfaces.d > find_interfacesd
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        pvdisplay > pvdisplay
        vgdisplay > vgdisplay
        lvdisplay > lvdisplay
        ls -al /dev/root_vg/ > dev_root_vg
        """)]
    fstab_expected = {
        'UUID=04836770-e989-460f-8774-8e277ddcb40f': '/',
    }

    def test_output_files_exist(self):
        self.output_files_exist( ["fstab"])

    def test_rootfs_format(self):
        self.output_files_exist(["lsblk.json"])
        lsblk_data = json.load(open(self.collect_path('lsblk.json')))
        print(json.dumps(lsblk_data, indent=4))
        [entry] = [entry for entry in lsblk_data.get('blockdevices')
                   if entry['mountpoint'] == '/']
        print(entry)
        self.assertEqual(self.rootfs_format, entry['fstype'])


class XenialTestLvmRootExt4(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'ext4'


class XenialTestLvmRootXfs(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'xfs'


class ArtfulTestLvmRootExt4(relbase.artful, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'ext4'


class ArtfulTestLvmRootXfs(relbase.artful, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'xfs'


class TestUefiLvmRootAbs(TestLvmRootAbs):
    conf_file = "examples/tests/uefi_lvmroot.yaml"
    uefi = True


class XenialTestUefiLvmRootExt4(relbase.xenial, TestUefiLvmRootAbs):
    __test__ = True
    rootfs_format = 'ext4'


class XenialTestUefiLvmRootXfs(relbase.xenial, TestUefiLvmRootAbs):
    __test__ = True
    rootfs_format = 'xfs'


class ArtfulTestUefiLvmRootExt4(relbase.artful, TestUefiLvmRootAbs):
    __test__ = True
    rootfs_format = 'ext4'


class ArtfulTestUefiLvmRootXfs(relbase.artful, TestUefiLvmRootAbs):
    __test__ = True
    rootfs_format = 'xfs'
