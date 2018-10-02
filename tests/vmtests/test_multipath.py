# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap


class TestMultipathBasicAbs(VMBaseClass):
    conf_file = "examples/tests/multipath.yaml"
    test_type = 'storage'
    multipath = True
    disk_driver = 'scsi-hd'
    extra_disks = []
    nvme_disks = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        multipath -ll > multipath_ll
        multipath -v3 -ll > multipath_v3_ll
        multipath -r > multipath_r
        cp -a /etc/multipath* .
        readlink -f /sys/class/block/sda/holders/dm-0 > holders_sda
        readlink -f /sys/class/block/sdb/holders/dm-0 > holders_sdb
        """)]

    def test_multipath_disks_match(self):
        sda_data = self.load_collect_file("holders_sda")
        print('sda holders:\n%s' % sda_data)
        sdb_data = self.load_collect_file("holders_sdb")
        print('sdb holders:\n%s' % sdb_data)
        self.assertEqual(sda_data, sdb_data)


class Centos70TestMultipathBasic(centos_relbase.centos70_xenial,
                                 TestMultipathBasicAbs):
    __test__ = True


class TrustyTestMultipathBasic(relbase.trusty, TestMultipathBasicAbs):
    __test__ = True


class TrustyHWEXTestMultipathBasic(relbase.trusty_hwe_x,
                                   TestMultipathBasicAbs):
    __test__ = True


class XenialGATestMultipathBasic(relbase.xenial_ga, TestMultipathBasicAbs):
    __test__ = True


class XenialHWETestMultipathBasic(relbase.xenial_hwe, TestMultipathBasicAbs):
    __test__ = True


class XenialEdgeTestMultipathBasic(relbase.xenial_edge, TestMultipathBasicAbs):
    __test__ = True


class BionicTestMultipathBasic(relbase.bionic, TestMultipathBasicAbs):
    __test__ = True


class CosmicTestMultipathBasic(relbase.cosmic, TestMultipathBasicAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
