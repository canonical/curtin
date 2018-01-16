from . import VMBaseClass
from .releases import base_vm_classes as relbase

import os
import textwrap


class TestNvmeAbs(VMBaseClass):
    arch_skip = [
        "s390x",  # nvme is a pci device, no pci on s390x
    ]
    interactive = False
    conf_file = "examples/tests/nvme.yaml"
    extra_disks = []
    nvme_disks = ['4G', '4G']
    disk_to_check = [('main_disk', 1), ('main_disk', 2), ('main_disk', 15),
                     ('nvme_disk', 1), ('nvme_disk', 2), ('nvme_disk', 3),
                     ('second_nvme', 1)]
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/class/ > sys_class
        ls /sys/class/nvme/ > ls_nvme
        ls /dev/nvme* > ls_dev_nvme
        ls /dev/disk/by-dname/ > ls_dname
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
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
        self.output_files_exist(["ls_nvme", "ls_dname", "ls_dev_nvme"])

    def test_nvme_device_names(self):
        ls_nvme = self.collect_path('ls_nvme')
        # trusty and vivid do not have sys/class/nvme but
        # nvme devices do work
        if os.path.getsize(ls_nvme) > 0:
            self.check_file_strippedline("ls_nvme", "nvme0")
            self.check_file_strippedline("ls_nvme", "nvme1")
        else:
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme0")
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme1")


class TrustyTestNvme(relbase.trusty, TestNvmeAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEXTestNvme(relbase.trusty_hwe_x, TestNvmeAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty, so we cannot expect
    # sda-part2 to exist in /dev/disk/by-dname as we can on other releases
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class XenialGATestNvme(relbase.xenial_ga, TestNvmeAbs):
    __test__ = True


class XenialHWETestNvme(relbase.xenial_hwe, TestNvmeAbs):
    __test__ = True


class XenialEdgeTestNvme(relbase.xenial_edge, TestNvmeAbs):
    __test__ = True


class ZestyTestNvme(relbase.zesty, TestNvmeAbs):
    __test__ = True


class ArtfulTestNvme(relbase.artful, TestNvmeAbs):
    __test__ = True


class BionicTestNvme(relbase.bionic, TestNvmeAbs):
    __test__ = True


class TestNvmeBcacheAbs(VMBaseClass):
    arch_skip = [
        "s390x",  # nvme is a pci device, no pci on s390x
    ]
    interactive = False
    conf_file = "examples/tests/nvme_bcache.yaml"
    extra_disks = ['10G']
    nvme_disks = ['6G']
    uefi = True
    disk_to_check = [('sda', 1), ('sda', 2), ('sda', 3)]

    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/class/ > sys_class
        ls /sys/class/nvme/ > ls_nvme
        ls /dev/nvme* > ls_dev_nvme
        ls /dev/disk/by-dname/ > ls_dname
        ls -al /dev/bcache/by-uuid/ > ls_bcache_by_uuid |:
        blkid -o export /dev/vda > blkid_output_vda
        blkid -o export /dev/vda1 > blkid_output_vda1
        blkid -o export /dev/vda2 > blkid_output_vda2
        bcache-super-show /dev/nvme0n1p1 > bcache_super_nvme0n1p1
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
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
        self.output_files_exist(["ls_nvme", "ls_dname", "ls_dev_nvme"])

    def test_nvme_device_names(self):
        ls_nvme = self.collect_path('ls_nvme')
        # trusty and vivid do not have sys/class/nvme but
        # nvme devices do work
        if os.path.getsize(ls_nvme) > 0:
            self.check_file_strippedline("ls_nvme", "nvme0")
        else:
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme0")
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme0n1")
            self.check_file_strippedline("ls_dev_nvme", "/dev/nvme0n1p1")

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_nvme0n1p1", "bcache_ls",
                                 "bcache_cache_mode"])

    def test_bcache_status(self):
        bcache_cset_uuid = None
        bcache_super = self.load_collect_file("bcache_super_nvme0n1p1")
        for line in bcache_super.splitlines():
            if line != "" and line.split()[0] == "cset.uuid":
                bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        self.assertTrue(bcache_cset_uuid in
                        self.load_collect_file("bcache_ls").splitlines())

    def test_bcache_cachemode(self):
        self.check_file_regex("bcache_cache_mode", r"\[writeback\]")


class XenialGATestNvmeBcache(relbase.xenial_ga, TestNvmeBcacheAbs):
    __test__ = True


class XenialHWETestNvmeBcache(relbase.xenial_hwe, TestNvmeBcacheAbs):
    __test__ = True


class XenialEdgeTestNvmeBcache(relbase.xenial_edge, TestNvmeBcacheAbs):
    __test__ = True


class ZestyTestNvmeBcache(relbase.zesty, TestNvmeBcacheAbs):
    __test__ = True


class ArtfulTestNvmeBcache(relbase.artful, TestNvmeBcacheAbs):
    __test__ = True


class BionicTestNvmeBcache(relbase.bionic, TestNvmeBcacheAbs):
    __test__ = True
