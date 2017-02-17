from . import VMBaseClass
from .releases import ubuntu_core_base_vm_classes as relbase

import textwrap


class TestUbuntuCoreAbs(VMBaseClass):
    target_ftype = "root-image.xz"
    interactive = False
    conf_file = "examples/tests/ubuntu_core.yaml"
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        snap list > snap_list
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["snap_list"])


class UbuntuCore16TestUbuntuCore(relbase.uc16fromxenial, TestUbuntuCoreAbs):
    __test__ = True
