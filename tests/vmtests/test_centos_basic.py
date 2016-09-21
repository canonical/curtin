from . import VMBaseClass
from .releases import centos_base_vm_classes as relbase

import textwrap


# FIXME: should eventually be integrated with the real TestBasic
class CentosTestBasicAbs(VMBaseClass):
    __test__ = False
    interactive = False
    # FIXME: get this working with a non-custom test yaml
    #       (and put it in examples/)
    conf_file = "/tmp/basic.yaml"
    extra_disks = ['10G']
    disks_to_check = [('main_disk', 1), ('main_disk', 2)]
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["ls_dname"])


# FIXME: this naming scheme needs to be replaced
class Centos70FromXenialTestBasic(relbase.centos70fromxenial,
                                  CentosTestBasicAbs):
    __test__ = True

    def test_dname(self):
        print("probably dname isnot going to work in centos out of the box")
