from . import VMBaseClass
from .releases import base_vm_classes as relbase

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
        dmsetup ls > dmsetup_ls
        dmsetup info > dmsetup_info
        cat /proc/partitions > proc_partitions
        multipath -ll > multipath_ll
        multipath -v3 -ll > multipath_v3_ll
        multipath -r > multipath_r
        cp -a /etc/multipath* .
        ls -al /dev/disk/by-uuid/ > ls_uuid
        ls -al /dev/disk/by-id/ > ls_disk_id
        readlink -f /sys/class/block/sda/holders/dm-0 > holders_sda
        readlink -f /sys/class/block/sdb/holders/dm-0 > holders_sdb
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_multipath_disks_match(self):
        sda_data = self.load_collect_file("holders_sda")
        print('sda holders:\n%s' % sda_data)
        sdb_data = self.load_collect_file("holders_sdb")
        print('sdb holders:\n%s' % sdb_data)
        self.assertEqual(sda_data, sdb_data)


class TrustyTestMultipathBasic(relbase.trusty, TestMultipathBasicAbs):
    __test__ = True


class TrustyHWEXTestMultipathBasic(relbase.trusty_hwe_x,
                                   TestMultipathBasicAbs):
    __test__ = True


class XenialTestMultipathBasic(relbase.xenial, TestMultipathBasicAbs):
    __test__ = True


class YakketyTestMultipathBasic(relbase.yakkety, TestMultipathBasicAbs):
    __test__ = True


class ZestyTestMultipathBasic(relbase.zesty, TestMultipathBasicAbs):
    __test__ = True
