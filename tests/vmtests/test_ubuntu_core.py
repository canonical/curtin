from . import VMBaseClass
from .releases import ubuntu_core_base_vm_classes as relbase

import textwrap


class TestUbuntuCoreAbs(VMBaseClass):
    target_ftype = "root-image.xz"
    interactive = False
    conf_file = "examples/tests/ubuntu_core.yaml"
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        cat /etc/fstab > fstab
        find /etc/network/interfaces.d > find_interfacesd
        snap list > snap_list
        cp -a /run/cloud-init ./run_cloud_init |:
        cp -a /etc/cloud ./ect_cloud |:
        cp -a /home . |:
        cp -a /var/lib/extrausers . |:
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["snap_list"])


class UbuntuCore16TestUbuntuCore(relbase.uc16fromxenial, TestUbuntuCoreAbs):
    __test__ = True
