# This file is part of curtin. See LICENSE file for copyright and license info.

from . import (
    VMBaseClass,
    get_apt_proxy)
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

import textwrap
from unittest import SkipTest


class TestBasicAbs(VMBaseClass):
    test_type = 'storage'
    interactive = False
    nr_cpus = 2
    dirty_disks = True
    conf_file = "examples/tests/basic.yaml"
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    disk_to_check = [('main_disk_with_in---valid--dname', 1),
                     ('main_disk_with_in---valid--dname', 2)]
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/vda | cat >blkid_output_vda
        blkid -o export /dev/vda1 | cat >blkid_output_vda1
        blkid -o export /dev/vda2 | cat >blkid_output_vda2
        dev="/dev/vdd"; f="btrfs_uuid_${dev#/dev/*}";
        if command -v btrfs-debug-tree >/dev/null; then
           btrfs-debug-tree -r $dev | awk '/^uuid/ {print $2}' | grep "-"
        else
           btrfs inspect-internal dump-super $dev |
               awk '/^dev_item.fsid/ {print $2}'
        fi | cat >$f
        """)]

    def _kname_to_uuid(self, kname):
        # extract uuid from /dev/disk/by-uuid on /dev/<kname>
        # parsing ls -al output on /dev/disk/by-uuid:
        # lrwxrwxrwx 1 root root   9 Dec  4 20:02
        #  d591e9e9-825a-4f0a-b280-3bfaf470b83c -> ../../vdg
        ls_uuid = self.load_collect_file("ls_al_byuuid")
        uuid = [line.split()[8] for line in ls_uuid.split('\n')
                if ("../../" + kname) in line.split()]
        self.assertEqual(len(uuid), 1)
        uuid = uuid.pop()
        self.assertTrue(uuid is not None)
        self.assertEqual(len(uuid), 36)
        return uuid

    def _test_ptable(self, blkid_output, expected):
        if self.target_release == "trusty":
            raise SkipTest("No PTTYPE blkid output on trusty")

        if not blkid_output:
            raise RuntimeError('_test_ptable requires blkid output file')

        if not expected:
            raise RuntimeError('_test_ptable requires expected value')

        self.output_files_exist([blkid_output])
        blkid_info = self.get_blkid_data(blkid_output)
        self.assertEquals(expected, blkid_info["PTTYPE"])

    def _test_partition_numbers(self, disk, expected):
        found = []
        self.output_files_exist(["proc_partitions"])
        proc_partitions = self.load_collect_file('proc_partitions')
        for line in proc_partitions.splitlines():
            if disk in line:
                found.append(line.split()[3])
        self.assertEqual(expected, found)

    def _test_fstab_entries(self, fstab, byuuid, expected):
        """
        expected = [
            (kname, mp, fsopts),
            ...
        ]
        """
        self.output_files_exist([fstab, byuuid])
        fstab_lines = self.load_collect_file(fstab).splitlines()
        for (kname, mp, fsopts) in expected:
            uuid = self._kname_to_uuid(kname)
            if not uuid:
                raise RuntimeError('Did not find uuid for kname: %s', kname)
            for line in fstab_lines:
                if uuid in line:
                    fstab_entry = line
                    break
            self.assertIsNotNone(fstab_entry)
            self.assertEqual(mp, fstab_entry.split(' ')[1])
            self.assertEqual(fsopts, fstab_entry.split(' ')[3])

    def _test_whole_disk_uuid(self, kname, uuid_file):

        # confirm the whole disk format is the expected device
        self.output_files_exist([uuid_file])
        btrfs_uuid = self.load_collect_file(uuid_file).strip()

        # extract uuid from btrfs superblock
        self.assertTrue(btrfs_uuid is not None)
        self.assertEqual(len(btrfs_uuid), 36)

        # extract uuid from ls_uuid by kname
        kname_uuid = self._kname_to_uuid(kname)

        # compare them
        self.assertEqual(kname_uuid, btrfs_uuid)

    # class specific input
    def test_output_files_exist(self):
        self.output_files_exist(
            ["ls_al_byuuid",
             "root/curtin-install.log", "root/curtin-install-cfg.yaml"])

    def test_ptable(self):
        self._test_ptable("blkid_output_vda", "dos")

    def test_partition_numbers(self):
        # vde should have partitions 1 and 10
        disk = "vde"
        expected = [disk + s for s in ["", "1", "10"]]
        self._test_partition_numbers(disk, expected)

    def test_fstab_entries(self):
        """"
        dev=vda1 mp=/ fsopts=defaults
        dev=vda2 mp=/home fsopts=defaults
        dev=vdd  mp=/btrfs fsopts=defaults,noatime
        """
        expected = [('vda1', '/', 'defaults'),
                    ('vda2', '/home', 'defaults'),
                    ('vdd', '/btrfs', 'defaults,noatime')]
        self._test_fstab_entries('fstab', 'ls_al_byuuid', expected)

    def test_whole_disk_uuid(self):
        self._test_whole_disk_uuid("vdd", "btrfs_uuid_vdd")

    def test_proxy_set(self):
        if self.target_distro != 'ubuntu':
            raise SkipTest("No apt-proxy for non-ubuntu distros")
        self.output_files_exist(['apt-proxy'])
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


class CentosTestBasicAbs(TestBasicAbs):
    def test_centos_release(self):
        """Test this image is the centos release expected"""
        self.output_files_exist(["rpm_dist_version_major", "centos-release"])

        centos_release = self.load_collect_file("centos-release").lower()
        rpm_major_version = (
            self.load_collect_file("rpm_dist_version_major").strip())
        _, os_id, os_version = self.target_release.partition("centos")

        self.assertTrue(os_version.startswith(rpm_major_version),
                        "%s doesn't start with %s" % (os_version,
                                                      rpm_major_version))
        self.assertTrue(centos_release.startswith(os_id),
                        "%s doesn't start with %s" % (centos_release, os_id))


class Centos70XenialTestBasic(centos_relbase.centos70_xenial,
                              CentosTestBasicAbs):
    __test__ = True


class TrustyTestBasic(relbase.trusty, TestBasicAbs):
    __test__ = True


class TrustyHWEXTestBasic(relbase.trusty_hwe_x, TrustyTestBasic):
    __test__ = True


class XenialGAi386TestBasic(relbase.xenial_ga, TestBasicAbs):
    __test__ = True
    arch = 'i386'


class XenialGATestBasic(relbase.xenial_ga, TestBasicAbs):
    __test__ = True


class XenialHWETestBasic(relbase.xenial_hwe, TestBasicAbs):
    __test__ = True


class XenialEdgeTestBasic(relbase.xenial_edge, TestBasicAbs):
    __test__ = True


class BionicTestBasic(relbase.bionic, TestBasicAbs):
    __test__ = True


class CosmicTestBasic(relbase.cosmic, TestBasicAbs):
    __test__ = True


class TestBasicScsiAbs(TestBasicAbs):
    conf_file = "examples/tests/basic_scsi.yaml"
    disk_driver = 'scsi-hd'
    extra_disks = ['128G', '128G', '4G']
    nvme_disks = ['4G']
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        blkid -o export /dev/sda | cat >blkid_output_sda
        blkid -o export /dev/sda1 | cat >blkid_output_sda1
        blkid -o export /dev/sda2 | cat >blkid_output_sda2
        dev="/dev/sdc"; f="btrfs_uuid_${dev#/dev/*}";
        if command -v btrfs-debug-tree >/dev/null; then
           btrfs-debug-tree -r $dev | awk '/^uuid/ {print $2}' | grep "-"
        else
           btrfs inspect-internal dump-super $dev |
               awk '/^dev_item.fsid/ {print $2}'
        fi | cat >$f
        """)]

    def test_ptable(self):
        self._test_ptable("blkid_output_sda", "dos")

    def test_partition_numbers(self):
        # sdd should have partitions 1 and 10
        disk = "sdd"
        expected = [disk + s for s in ["", "1", "10"]]
        self._test_partition_numbers(disk, expected)

    def test_fstab_entries(self):
        """"
        dev=sda1 mp=/ fsopts=defaults
        dev=sda2 mp=/home fsopts=defaults
        dev=sdc  mp=/btrfs fsopts=defaults,noatime
        """
        expected = [('sda1', '/', 'defaults'),
                    ('sda2', '/home', 'defaults'),
                    ('sdc', '/btrfs', 'defaults,noatime')]
        self._test_fstab_entries('fstab', 'ls_al_byuuid', expected)

    def test_whole_disk_uuid(self):
        self._test_whole_disk_uuid("sdc", "btrfs_uuid_sdc")


class Centos70XenialTestScsiBasic(centos_relbase.centos70_xenial,
                                  TestBasicScsiAbs, CentosTestBasicAbs):
    __test__ = True


class XenialGATestScsiBasic(relbase.xenial_ga, TestBasicScsiAbs):
    __test__ = True


class XenialHWETestScsiBasic(relbase.xenial_hwe, TestBasicScsiAbs):
    __test__ = True


class XenialEdgeTestScsiBasic(relbase.xenial_edge, TestBasicScsiAbs):
    __test__ = True


class BionicTestScsiBasic(relbase.bionic, TestBasicScsiAbs):
    __test__ = True


class CosmicTestScsiBasic(relbase.cosmic, TestBasicScsiAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
