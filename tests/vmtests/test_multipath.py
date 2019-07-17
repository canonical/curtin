# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

from unittest import SkipTest
import os
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
        command -v systemctl && {
            systemctl show -- home.mount > systemctl_show_home.mount;
            systemctl status --full home.mount > systemctl_status_home.mount
        }
        exit 0
        """)]

    def test_multipath_disks_match(self):
        sda_data = self.load_collect_file("holders_sda")
        print('sda holders:\n%s' % sda_data)
        sdb_data = self.load_collect_file("holders_sdb")
        print('sdb holders:\n%s' % sdb_data)
        self.assertEqual(sda_data, sdb_data)

    def test_home_mount_unit(self):
        unit_file = 'systemctl_show_home.mount'
        if not os.path.exists(self.collect_path(unit_file)):
            raise SkipTest(
                'target_release=%s does not use systemd' % self.target_release)

        # We can't use load_shell_content as systemctl show output
        # does not quote values even though it's in Key=Value format
        content = self.load_collect_file(unit_file)
        expected_results = {
            'ActiveState': 'active',
            'Result': 'success',
            'SubState': 'mounted',
        }
        show = {key: value for key, value in
                [line.split('=') for line in content.splitlines()
                 if line.split('=')[0] in expected_results.keys()]}

        self.assertEqual(sorted(expected_results), sorted(show))


class Centos70TestMultipathBasic(centos_relbase.centos70_xenial,
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


class DiscoTestMultipathBasic(relbase.disco, TestMultipathBasicAbs):
    __test__ = True


class EoanTestMultipathBasic(relbase.eoan, TestMultipathBasicAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
