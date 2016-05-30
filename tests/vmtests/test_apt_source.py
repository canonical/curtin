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
        apt-key list "F430BBA5" > key1
        apt-key list "B59D5F15 97A504B7 E2306DCA 0620BBCF 03683F77" > key2
        apt-key list "B6832E30" > key3
        cp /etc/apt/sources.list.d/byobu-ppa.list .
        cp /etc/apt/sources.list.d/my-repo2.list .
        cp /etc/apt/sources.list.d/my-repo4.list .
        ls -1 /etc/apt/sources.list.d/* > sourcelists
        """)]

    def test_output_files_exist(self):
        "Check if all output files exist"
        self.output_files_exist(
            ["fstab", "key1", "key2", "key3", "byobu-ppa.list",
             "my-repo2.list", "my-repo4.list", "sourcelists"])


class XenialTestAptSrc(relbase.xenial, TestAptSrcAbs):
    """ XenialTestAptSrc
       Basic Test for Xenial without HWE
       Not that for this feature we don't support/care pre-Xenial
    """
    __test__ = True
