from . import VMBaseClass
from .releases import centos_base_vm_classes as relbase

import textwrap


# FIXME: should eventually be integrated with the real TestBasic
class CentosTestBasicAbs(VMBaseClass):
    __test__ = False
    conf_file = "examples/tests/centos_basic.yaml"
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"
    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        """)]
    fstab_expected = {
        'LABEL=cloudimg-rootfs': '/',
    }

    def test_dname(self):
        pass

    def test_interfacesd_eth0_removed(self):
        pass

    def test_output_files_exist(self):
        self.output_files_exist(["fstab"])


# FIXME: this naming scheme needs to be replaced
class Centos70FromXenialTestBasic(relbase.centos70fromxenial,
                                  CentosTestBasicAbs):
    __test__ = True


class Centos66FromXenialTestBasic(relbase.centos66fromxenial,
                                  CentosTestBasicAbs):
    __test__ = False
    # FIXME: test is disabled because the grub config script in target
    #        specifies drive using hd(1,0) syntax, which breaks when the
    #        installation medium is removed. other than this, the install works
