from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import textwrap


class TestLvmRootAbs(VMBaseClass):
    conf_file = "examples/tests/lvmroot.yaml"
    interactive = False
    rootfs_uuid = '04836770-e989-460f-8774-8e277ddcb40f'
    extra_disks = []
    dirty_disks = True
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        lsblk --json --fs -o KNAME,MOUNTPOINT,UUID,FSTYPE > lsblk.json
        lsblk --fs -P -o KNAME,MOUNTPOINT,UUID,FSTYPE > lsblk.out
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
    conf_replace = {}

    def test_output_files_exist(self):
        self.output_files_exist(["fstab"])

    def test_rootfs_format(self):
        if self.release not in ['trusty']:
            self.output_files_exist(["lsblk.json"])
            lsblk_data = json.load(open(self.collect_path('lsblk.json')))
            print(json.dumps(lsblk_data, indent=4))
            [entry] = [entry for entry in lsblk_data.get('blockdevices')
                       if entry['mountpoint'] == '/']
            print(entry)
            self.assertEqual(self.conf_replace['__ROOTFS_FORMAT__'],
                             entry['fstype'])
        else:
            # no json output on trusty
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


class TrustyTestLvmRootExt4(relbase.trusty, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class TrustyTestLvmRootXfs(relbase.trusty, TestLvmRootAbs):
    __test__ = True
    # xfs on trusty can't support uuid=
    fstab_expected = {}
    conf_replace = {
        '__ROOTFS_FORMAT__': 'xfs',
    }


class XenialTestLvmRootExt4(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class XenialTestLvmRootXfs(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'xfs',
    }


class ArtfulTestLvmRootExt4(relbase.artful, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'ext4',
    }


class ArtfulTestLvmRootXfs(relbase.artful, TestLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__ROOTFS_FORMAT__': 'xfs',
    }


class TestUefiLvmRootAbs(TestLvmRootAbs):
    conf_file = "examples/tests/uefi_lvmroot.yaml"
    uefi = True


class XenialTestUefiLvmRootExt4(relbase.xenial, TestUefiLvmRootAbs):
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


class XenialTestUefiLvmRootXfsBootXfs(relbase.xenial, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'xfs',  # Expected to fail until LP: #1652822
        '__ROOTFS_FORMAT__': 'xfs',
    }

    @classmethod
    def setUpClass(cls):
        cls.skip_by_date(cls.__name__, cls.release, "1652822",
                         fixby=(2018, 1, 20), removeby=(2018, 2, 23))
        super().setUpClass()


class ArtfulTestUefiLvmRootExt4(relbase.artful, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'ext4',
    }


class ArtfulTestUefiLvmRootXfs(relbase.artful, TestUefiLvmRootAbs):
    __test__ = True
    conf_replace = {
        '__BOOTFS_FORMAT__': 'ext4',
        '__ROOTFS_FORMAT__': 'xfs',
    }
