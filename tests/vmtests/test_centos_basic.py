from . import VMBaseClass
from .releases import centos_base_vm_classes as relbase


# FIXME: should eventually be integrated with the real TestBasic
class CentosTestBasicAbs(VMBaseClass):
    __test__ = False
    # FIXME: get this working with a non-custom test yaml
    #       (and put it in examples/)
    conf_file = "examples/tests/centos_basic.yaml"
    collect_scripts = []

    def test_dname(self):
        pass


# FIXME: this naming scheme needs to be replaced
class Centos70FromXenialTestBasic(relbase.centos70fromxenial,
                                  CentosTestBasicAbs):
    __test__ = True
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"


class Centos66FromXenialTestBasic(relbase.centos66fromxenial,
                                  CentosTestBasicAbs):
    __test__ = True
