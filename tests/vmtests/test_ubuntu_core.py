# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import ubuntu_core_base_vm_classes as relbase

import textwrap


class TestUbuntuCoreAbs(VMBaseClass):
    target_ftype = "root-image.xz"
    interactive = False
    conf_file = "examples/tests/ubuntu_core.yaml"
    extra_collect_scripts = VMBaseClass.extra_collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        snap list > snap_list
        cp -a /run/cloud-init ./run_cloud_init |:
        cp -a /etc/cloud ./etc_cloud |:
        cp -a /home . |:
        cp -a /var/lib/extrausers . |:
        """)]

    def test_ubuntu_core_snaps_installed(self):
        self.output_files_exist(["snap_list"])
        snap_list = self.load_collect_file('snap_list')
        print(snap_list)
        for snap in ['core', 'pc', 'pc-kernel', 'hello',
                     'part-cython', 'part-numpy']:
            print('check for "%s"' % snap)
            self.assertIn(snap, snap_list)

    def test_ubuntu_core_extrausers(self):
        extrausers_passwd = self.load_collect_file('extrausers/passwd')
        self.assertIn('ubuntu', extrausers_passwd)

    def test_ubuntu_core_ds_identify(self):
        run_ci_config = self.load_collect_file('run_cloud_init/cloud.cfg')
        expected_config = "datasource_list: [ NoCloud, None ]\n"
        self.assertEqual(expected_config, run_ci_config)


class UbuntuCore16TestUbuntuCore(relbase.uc16fromxenial, TestUbuntuCoreAbs):
    __test__ = False

# vi: ts=4 expandtab syntax=python
