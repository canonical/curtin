# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import yaml


class TestInstallUnmount(VMBaseClass):
    """ Test a curtin install which disabled unmonting """
    conf_file = "examples/tests/install_disable_unmount.yaml"""
    test_type = 'config'
    extra_nics = []
    extra_disks = []

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

# vi: ts=4 expandtab syntax=python
