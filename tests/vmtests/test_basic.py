from . import (
    VMBaseClass,
    get_apt_proxy)
from .releases import base_vm_classes as relbase

import os
import re
import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    conf_file = "examples/tests/basic.yaml"
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    disk_to_check = [('main_disk_with_in---valid--dname', 1),
                     ('main_disk_with_in---valid--dname', 2)]
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        btrfs-show-super /dev/vdd > btrfs_show_super_vdd
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd

        v=""
        out=$(apt-config shell v Acquire::HTTP::Proxy)
        eval "$out"
        echo "$v" > apt-proxy
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "btrfs_show_super_vdd", "fstab", "ls_dname", "ls_uuid",
             "proc_partitions"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_vda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

    def test_partition_numbers(self):
        # vde should have partitions 1 and 10
        disk = "vde"
        proc_partitions_path = os.path.join(self.td.collect,
                                            'proc_partitions')
        self.assertTrue(os.path.exists(proc_partitions_path))
        found = []
        with open(proc_partitions_path, 'r') as fp:
            for line in fp.readlines():
                if disk in line:
                    found.append(line.split()[3])
        # /proc/partitions should have 3 lines with 'vde' in them.
        expected = [disk + s for s in ["", "1", "10"]]
        self.assertEqual(found, expected)

    def test_partitions(self):
        with open(os.path.join(self.td.collect, "fstab")) as fp:
            fstab_lines = fp.readlines()
        print("\n".join(fstab_lines))
        # Test that vda1 is on /
        blkid_info = self.get_blkid_data("blkid_output_vda1")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/")

        # Test that vda2 is on /home
        blkid_info = self.get_blkid_data("blkid_output_vda2")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/home")

        # Test whole disk vdd is mounted at /btrfs
        fstab_entry = None
        for line in fstab_lines:
            if "/dev/vdd" in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/btrfs")

    def test_whole_disk_format(self):
        # confirm the whole disk format is the expected device
        with open(os.path.join(self.td.collect,
                  "btrfs_show_super_vdd"), "r") as fp:
            btrfs_show_super = fp.read()

        with open(os.path.join(self.td.collect, "ls_uuid"), "r") as fp:
            ls_uuid = fp.read()

        # extract uuid from btrfs superblock
        btrfs_fsid = [line for line in btrfs_show_super.split('\n')
                      if line.startswith('fsid\t\t')]
        self.assertEqual(len(btrfs_fsid), 1)
        btrfs_uuid = btrfs_fsid[0].split()[1]
        self.assertTrue(btrfs_uuid is not None)

        # extract uuid from /dev/disk/by-uuid on /dev/vdd
        # parsing ls -al output on /dev/disk/by-uuid:
        # lrwxrwxrwx 1 root root   9 Dec  4 20:02
        #  d591e9e9-825a-4f0a-b280-3bfaf470b83c -> ../../vdg
        vdd_uuid = [line.split()[8] for line in ls_uuid.split('\n')
                    if 'vdd' in line]
        self.assertEqual(len(vdd_uuid), 1)
        vdd_uuid = vdd_uuid.pop()
        self.assertTrue(vdd_uuid is not None)

        # compare them
        self.assertEqual(vdd_uuid, btrfs_uuid)

    def test_proxy_set(self):
        expected = get_apt_proxy()
        with open(os.path.join(self.td.collect, "apt-proxy")) as fp:
            apt_proxy_found = fp.read().rstrip()
        if expected:
            # the proxy should have gotten set through
            self.assertIn(expected, apt_proxy_found)
        else:
            # no proxy, so the output of apt-config dump should be empty
            self.assertEqual("", apt_proxy_found)


class PreciseTestBasic(relbase.precise, TestBasicAbs):
    __test__ = True

    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        btrfs-show /dev/vdd > btrfs_show_super_vdd
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd

        v=""
        out=$(apt-config shell v Acquire::HTTP::Proxy)
        eval "$out"
        echo "$v" > apt-proxy
        """)]

    def test_whole_disk_format(self):
        # confirm the whole disk format is the expected device
        with open(os.path.join(self.td.collect,
                  "btrfs_show_super_vdd"), "r") as fp:
            btrfs_show_super = fp.read()

        with open(os.path.join(self.td.collect, "ls_uuid"), "r") as fp:
            ls_uuid = fp.read()

        # extract uuid from btrfs superblock
        btrfs_fsid = re.findall('.*uuid:\ (.*)\n', btrfs_show_super)

        self.assertEqual(len(btrfs_fsid), 1)
        btrfs_uuid = btrfs_fsid.pop()
        self.assertTrue(btrfs_uuid is not None)

        # extract uuid from /dev/disk/by-uuid on /dev/vdd
        # parsing ls -al output on /dev/disk/by-uuid:
        # lrwxrwxrwx 1 root root   9 Dec  4 20:02
        #  d591e9e9-825a-4f0a-b280-3bfaf470b83c -> ../../vdg
        vdd_uuid = [line.split()[8] for line in ls_uuid.split('\n')
                    if 'vdd' in line]
        self.assertEqual(len(vdd_uuid), 1)
        vdd_uuid = vdd_uuid.pop()
        self.assertTrue(vdd_uuid is not None)

        # compare them
        self.assertEqual(vdd_uuid, btrfs_uuid)

    def test_ptable(self):
        print("test_ptable does not work for Precise")

    def test_dname(self):
        print("test_dname does not work for Precise")


class TrustyTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class PreciseHWETTestBasic(relbase.precise_hwe_t, PreciseTestBasic):
    # FIXME: off due to test_whole_disk_format failing
    __test__ = False


class TrustyHWEUTestBasic(relbase.trusty_hwe_u, TrustyTestBasic):
    # off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestBasic(relbase.trusty_hwe_v, TrustyTestBasic):
    # off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestBasic(relbase.trusty_hwe_w, TrustyTestBasic):
    # off by default to safe test suite runtime, covered by bonding
    __test__ = False


class WilyTestBasic(relbase.wily, TestBasicAbs):
    __test__ = True


class XenialTestBasic(relbase.xenial, TestBasicAbs):
    __test__ = True


class YakketyTestBasic(relbase.yakkety, TestBasicAbs):
    __test__ = True


class TestBasicScsiAbs(TestBasicAbs):
    conf_file = "examples/tests/basic_scsi.yaml"
    disk_driver = 'scsi-hd'
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/sda > blkid_output_sda
        blkid -o export /dev/sda1 > blkid_output_sda1
        blkid -o export /dev/sda2 > blkid_output_sda2
        btrfs-show-super /dev/sdc > btrfs_show_super_sdc
        cat /proc/partitions > proc_partitions
        ls -al /dev/disk/by-uuid/ > ls_uuid
        ls -al /dev/disk/by-id/ > ls_disk_id
        cat /etc/fstab > fstab
        mkdir -p /dev/disk/by-dname
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd

        v=""
        out=$(apt-config shell v Acquire::HTTP::Proxy)
        eval "$out"
        echo "$v" > apt-proxy
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_sda", "blkid_output_sda1", "blkid_output_sda2",
             "btrfs_show_super_sdc", "fstab", "ls_dname", "ls_uuid",
             "ls_disk_id", "proc_partitions"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_sda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

    def test_partition_numbers(self):
        # vde should have partitions 1 and 10
        disk = "sdd"
        proc_partitions_path = os.path.join(self.td.collect,
                                            'proc_partitions')
        self.assertTrue(os.path.exists(proc_partitions_path))
        found = []
        with open(proc_partitions_path, 'r') as fp:
            for line in fp.readlines():
                if disk in line:
                    found.append(line.split()[3])
        # /proc/partitions should have 3 lines with 'vde' in them.
        expected = [disk + s for s in ["", "1", "10"]]
        self.assertEqual(found, expected)

    def test_partitions(self):
        with open(os.path.join(self.td.collect, "fstab")) as fp:
            fstab_lines = fp.readlines()
        print("\n".join(fstab_lines))
        # Test that vda1 is on /
        blkid_info = self.get_blkid_data("blkid_output_sda1")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/")

        # Test that vda2 is on /home
        blkid_info = self.get_blkid_data("blkid_output_sda2")
        fstab_entry = None
        for line in fstab_lines:
            if blkid_info['UUID'] in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/home")

        # Test whole disk sdc is mounted at /btrfs
        fstab_entry = None
        for line in fstab_lines:
            if "/dev/sdc" in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/btrfs")

    def test_whole_disk_format(self):
        # confirm the whole disk format is the expected device
        with open(os.path.join(self.td.collect,
                  "btrfs_show_super_sdc"), "r") as fp:
            btrfs_show_super = fp.read()

        with open(os.path.join(self.td.collect, "ls_uuid"), "r") as fp:
            ls_uuid = fp.read()

        # extract uuid from btrfs superblock
        btrfs_fsid = [line for line in btrfs_show_super.split('\n')
                      if line.startswith('fsid\t\t')]
        self.assertEqual(len(btrfs_fsid), 1)
        btrfs_uuid = btrfs_fsid[0].split()[1]
        self.assertTrue(btrfs_uuid is not None)

        # extract uuid from /dev/disk/by-uuid on /dev/sdc
        # parsing ls -al output on /dev/disk/by-uuid:
        # lrwxrwxrwx 1 root root   9 Dec  4 20:02
        #  d591e9e9-825a-4f0a-b280-3bfaf470b83c -> ../../vdg
        uuid = [line.split()[8] for line in ls_uuid.split('\n')
                if 'sdc' in line]
        self.assertEqual(len(uuid), 1)
        uuid = uuid.pop()
        self.assertTrue(uuid is not None)

        # compare them
        self.assertEqual(uuid, btrfs_uuid)


class XenialTestScsiBasic(relbase.xenial, TestBasicScsiAbs):
    __test__ = True
