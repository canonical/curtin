from . import VMBaseClass
from .releases import base_vm_classes as relbase

import os
import textwrap


class TestMultipathBasicAbs(VMBaseClass):
    conf_file = "examples/tests/multipath.yaml"
    multipath = True
    disk_driver = 'scsi-hd'
    extra_disks = []
    nvme_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/sda > blkid_output_sda
        blkid -o export /dev/sda1 > blkid_output_sda1
        blkid -o export /dev/sda2 > blkid_output_sda2
        blkid -o export /dev/sdb > blkid_output_sdb
        blkid -o export /dev/sdb1 > blkid_output_sdb1
        blkid -o export /dev/sdb2 > blkid_output_sdb2
        cat /proc/partitions > proc_partitions
        multipath -ll > multipath_ll
        multipath -v3 -ll > multipath_v3_ll
        multipath -r > multipath_r
        cp -a /etc/multipath* .
        ls -al /dev/disk/by-uuid/ > ls_uuid
        ls -al /dev/disk/by-id/ > ls_disk_id
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_multipath_disks_match(self):
        sda = os.path.join(self.td.collect, 'blkid_output_sda')
        sdb = os.path.join(self.td.collect, 'blkid_output_sdb')

        self.assertTrue(os.path.exists(sda))
        self.assertTrue(os.path.exists(sdb))
        with open(sda, 'r') as fp:
            sda_data = fp.read()
            print("sda:\n%s" % sda_data)

        with open(sdb, 'r') as fp:
            sdb_data = fp.read()
            print("sdb:\n%s" % sdb_data)

        self.assertEqual(sda_data, sdb_data)


class TrustyTestMultipathBasic(relbase.trusty, TestMultipathBasicAbs):
    __test__ = True


class XenialTestMultipathBasic(relbase.xenial, TestMultipathBasicAbs):
    __test__ = True
