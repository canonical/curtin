from . import (
    VMBaseClass,
    get_apt_proxy)
from .releases import base_vm_classes as relbase

import textwrap


class TestBasicAbs(VMBaseClass):
    interactive = False
    nr_cpus = 2
    dirty_disks = True
    conf_file = "examples/tests/basic.yaml"
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    disk_to_check = [('main_disk_with_in---valid--dname', 1),
                     ('main_disk_with_in---valid--dname', 2)]
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        f="btrfs_uuid_vdd"
        btrfs-debug-tree -r /dev/vdd | awk '/^uuid/ {print $2}' | grep "-" > $f
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

    def _kname_to_uuid(self, kname):
        # extract uuid from /dev/disk/by-uuid on /dev/<kname>
        # parsing ls -al output on /dev/disk/by-uuid:
        # lrwxrwxrwx 1 root root   9 Dec  4 20:02
        #  d591e9e9-825a-4f0a-b280-3bfaf470b83c -> ../../vdg
        ls_uuid = self.load_collect_file("ls_uuid")
        uuid = [line.split()[8] for line in ls_uuid.split('\n')
                if ("../../" + kname) in line.split()]
        self.assertEqual(len(uuid), 1)
        uuid = uuid.pop()
        self.assertTrue(uuid is not None)
        self.assertEqual(len(uuid), 36)
        return uuid

    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "btrfs_uuid_vdd", "fstab", "ls_dname", "ls_uuid",
             "proc_partitions",
             "root/curtin-install.log", "root/curtin-install-cfg.yaml"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_vda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

    def test_partition_numbers(self):
        # vde should have partitions 1 and 10
        disk = "vde"
        found = []
        proc_partitions = self.load_collect_file('proc_partitions')
        for line in proc_partitions.splitlines():
            if disk in line:
                found.append(line.split()[3])
        # /proc/partitions should have 3 lines with 'vde' in them.
        expected = [disk + s for s in ["", "1", "10"]]
        self.assertEqual(found, expected)

    def test_partitions(self):
        fstab_lines = self.load_collect_file('fstab').splitlines()
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
        uuid = self._kname_to_uuid('vdd')
        fstab_entry = None
        for line in fstab_lines:
            if uuid in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/btrfs")
        self.assertEqual(fstab_entry.split(' ')[3], "defaults,noatime")

    def test_whole_disk_format(self):
        # confirm the whole disk format is the expected device
        btrfs_uuid = self.load_collect_file('btrfs_uuid_vdd').strip()

        # extract uuid from btrfs superblock
        self.assertTrue(btrfs_uuid is not None)
        self.assertEqual(len(btrfs_uuid), 36)

        # extract uuid from ls_uuid by kname
        kname_uuid = self._kname_to_uuid('vdd')

        # compare them
        self.assertEqual(kname_uuid, btrfs_uuid)

    def test_proxy_set(self):
        expected = get_apt_proxy()
        apt_proxy_found = self.load_collect_file("apt-proxy").rstrip()
        if expected:
            # the proxy should have gotten set through
            self.assertIn(expected, apt_proxy_found)
        else:
            # no proxy, so the output of apt-config dump should be empty
            self.assertEqual("", apt_proxy_found)

    def test_curtin_install_version(self):
        installed_version = self.get_install_log_curtin_version()
        print('Install log version: %s' % installed_version)
        source_version = self.get_curtin_version()
        print('Source repo version: %s' % source_version)
        self.assertEqual(source_version, installed_version)


class TrustyTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEXTestBasic(relbase.trusty_hwe_x, TrustyTestBasic):
    __test__ = True


class XenialGATestBasic(relbase.xenial_ga, TestBasicAbs):
    __test__ = True


class XenialHWETestBasic(relbase.xenial_hwe, TestBasicAbs):
    __test__ = True


class XenialEdgeTestBasic(relbase.xenial_edge, TestBasicAbs):
    __test__ = True


class ArtfulTestBasic(relbase.artful, TestBasicAbs):
    __test__ = True


class BionicTestBasic(relbase.bionic, TestBasicAbs):
    __test__ = True


class TestBasicScsiAbs(TestBasicAbs):
    conf_file = "examples/tests/basic_scsi.yaml"
    disk_driver = 'scsi-hd'
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/sda > blkid_output_sda
        blkid -o export /dev/sda1 > blkid_output_sda1
        blkid -o export /dev/sda2 > blkid_output_sda2
        f="btrfs_uuid_sdc"
        btrfs-debug-tree -r /dev/sdc | awk '/^uuid/ {print $2}' | grep "-" > $f
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
             "btrfs_uuid_sdc", "fstab", "ls_dname", "ls_uuid",
             "ls_disk_id", "proc_partitions"])

    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_sda")
        self.assertEquals(blkid_info["PTTYPE"], "dos")

    def test_partition_numbers(self):
        # vde should have partitions 1 and 10
        disk = "sdd"
        found = []
        proc_partitions = self.load_collect_file('proc_partitions')
        for line in proc_partitions.splitlines():
            if disk in line:
                found.append(line.split()[3])
        # /proc/partitions should have 3 lines with 'vde' in them.
        expected = [disk + s for s in ["", "1", "10"]]
        self.assertEqual(found, expected)

    def test_partitions(self):
        fstab_lines = self.load_collect_file('fstab').splitlines()
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

        # Test whole disk sdc is mounted at /btrfs, and uses defaults,noatime
        uuid = self._kname_to_uuid('sdc')
        fstab_entry = None
        for line in fstab_lines:
            if uuid in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/btrfs")
        self.assertEqual(fstab_entry.split(' ')[3], "defaults,noatime")

    def test_whole_disk_format(self):
        # confirm the whole disk format is the expected device
        btrfs_uuid = self.load_collect_file("btrfs_uuid_sdc").strip()

        # extract uuid from btrfs superblock
        self.assertTrue(btrfs_uuid is not None)
        self.assertEqual(len(btrfs_uuid), 36)

        # extract uuid from ls_uuid by kname
        kname_uuid = self._kname_to_uuid('sdc')

        # compare them
        self.assertEqual(kname_uuid, btrfs_uuid)


class XenialGATestScsiBasic(relbase.xenial_ga, TestBasicScsiAbs):
    __test__ = True


class XenialHWETestScsiBasic(relbase.xenial_hwe, TestBasicScsiAbs):
    __test__ = True


class XenialEdgeTestScsiBasic(relbase.xenial_edge, TestBasicScsiAbs):
    __test__ = True


class ArtfulTestScsiBasic(relbase.artful, TestBasicScsiAbs):
    __test__ = True


class BionicTestScsiBasic(relbase.bionic, TestBasicScsiAbs):
    __test__ = True
