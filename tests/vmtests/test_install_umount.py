from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap
import yaml


class TestInstallUnmount(VMBaseClass):
    """ Test a curtin install which disabled unmonting """
    conf_file = "examples/tests/install_disable_unmount.yaml"""
    extra_nics = []
    extra_disks = []
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        sfdisk --list > sfdisk_list
        for d in /dev/[sv]d[a-z] /dev/xvd?; do
            [ -b "$d" ] || continue
            echo == $d ==
            sgdisk --print $d
        done > sgdisk_list
        blkid > blkid
        cat /proc/partitions > proc_partitions
        cp /etc/network/interfaces interfaces
        if [ -f /var/log/cloud-init-output.log ]; then
           cp /var/log/cloud-init-output.log .
        fi
        cp /var/log/cloud-init.log .
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_proc_mounts_before_unmount(self):
        """Test TARGET_MOUNT_POINT value is in ephemeral /proc/mounts"""
        self.output_files_exist([
            'root/postinst_mounts.out',
            'root/target.out'])

        # read target mp and mounts
        target_mp = self.load_collect_file('root/target.out').strip()
        curtin_mounts = self.load_collect_file('root/postinst_mounts.out')
        self.assertIn(target_mp, curtin_mounts)

    def test_install_config_has_unmount_disabled(self):
        """Test that install ran with unmount: disabled"""
        collect_curtin_cfg = 'root/curtin-install-cfg.yaml'
        self.output_files_exist([collect_curtin_cfg])
        curtin_cfg = yaml.load(self.load_collect_file(collect_curtin_cfg))

        # check that we have
        # install:
        #   unmount: disabled
        install_unmount = curtin_cfg.get('install', {}).get('unmount')
        self.assertEqual(install_unmount, "disabled")


class XenialTestInstallUnmount(relbase.xenial, TestInstallUnmount):
    __test__ = True
