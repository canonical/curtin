import textwrap

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestAptSrcAbs(VMBaseClass):
    """ TestAptSrcAbs
        Basic test class to test apt_sources features of curtin
    """
    conf_file = "examples/tests/apt_source.yaml"
    interactive = False
    extra_disks = []
    fstab_expected = {}
    disk_to_check = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        "Check if all output files exist"
        self.output_files_exist(
            ["fstab"])


class XenialTestAptSrc(relbase.xenial, TestAptSrcAbs):
    """ XenialTestAptSrc
       Basic Test for Xenial without HWE
       Not that for this feature we don't support/care pre-Xenial
    """
    __test__ = True
