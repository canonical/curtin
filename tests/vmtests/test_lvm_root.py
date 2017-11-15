from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestLvmRootAbs(VMBaseClass):
    conf_file = "examples/tests/lvmroot.yaml"
    interactive = False
    extra_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        lsblk -f -P > lsblk_fs_info
        ls -al /dev/disk/by-dname > ls_al_dname
        find /etc/network/interfaces.d > find_interfacesd
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        pvdisplay > pvdisplay
        vgdisplay > vgdisplay
        lvdisplay > lvdisplay
        """)]
    fstab_expected = {
        '/dev/rootvg/lv1_root': '/',
    }

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "ls_dname"])


class XenialTestLvmRootExt4(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'ext4'


class XenialTestLvmRootXfs(relbase.xenial, TestLvmRootAbs):
    __test__ = True
    rootfs_format = 'xfs'
