# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase

import glob
import textwrap


class TestBcacheCeph(VMBaseClass):
    arch_skip = [
        "s390x",  # lp:1565029
    ]
    test_type = 'storage'
    conf_file = "examples/tests/bcache-ceph-nvme.yaml"
    nr_cpus = 2
    uefi = True
    dirty_disks = True
    extra_disks = ['20G', '20G', '20G', '20G', '20G', '20G', '20G', '20G']
    nvme_disks = ['20G', '20G']
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ls /sys/fs/bcache/ > bcache_ls
        ls -al /dev/bcache/by-uuid/ > ls_al_dev_bcache_by_uuid
        ls -al /dev/bcache/by-label/ > ls_al_dev_bcache_by_label
        ls -al /sys/class/block/bcache* > ls_al_sys_block_bcache
        for bcache in /sys/class/block/bcache*; do
            for link in $(find ${bcache}/slaves -type l); do
                kname=$(basename $(readlink $link))
                outfile="bcache-super-show.$kname"
                bcache-super-show /dev/${kname} > $outfile
            done
        done
        exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_bcache_output_files_exist(self):
        self.output_files_exist([
            "bcache-super-show.vda1",
            "bcache-super-show.vdc",
            "bcache-super-show.vdd",
            "bcache-super-show.vde",
            "bcache-super-show.vdf",
            "bcache-super-show.vdh",
            "bcache-super-show.nvme0n1p2",
            "bcache-super-show.nvme1n1p2"])

    @skip_if_flag('expected_failure')
    def test_bcache_devices_cset_found(self):
        sblocks = glob.glob("%s/bcache-super-show.*")
        for superblock in sblocks:
            bcache_cset_uuid = None
            for line in self.load_collect_file(superblock).splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
            self.assertIsNotNone(bcache_cset_uuid)
            self.assertTrue(bcache_cset_uuid in
                            self.load_collect_file("bcache_ls").splitlines())


class XenialGATestBcacheCeph(relbase.xenial_ga, TestBcacheCeph):
    __test__ = True


class XenialHWETestBcacheCeph(relbase.xenial_hwe, TestBcacheCeph):
    __test__ = True


class XenialEdgeTestBcacheCeph(relbase.xenial_edge, TestBcacheCeph):
    __test__ = True


class BionicTestBcacheCeph(relbase.bionic, TestBcacheCeph):
    __test__ = True


class DiscoTestBcacheCeph(relbase.disco, TestBcacheCeph):
    __test__ = True


class EoanTestBcacheCeph(relbase.eoan, TestBcacheCeph):
    __test__ = True


class FocalTestBcacheCeph(relbase.focal, TestBcacheCeph):
    __test__ = True


class TestBcacheCephLvm(TestBcacheCeph):
    test_type = 'storage'
    nr_cpus = 2
    uefi = True
    dirty_disks = True
    extra_disks = ['20G', '20G']
    nvme_disks = ['20G']
    conf_file = "examples/tests/bcache-ceph-nvme-simple.yaml"

    @skip_if_flag('expected_failure')
    def test_bcache_output_files_exist(self):
        self.output_files_exist([
            "bcache-super-show.vda3",
            "bcache-super-show.vdc",
            "bcache-super-show.nvme0n1",
        ])


class BionicTestBcacheCephLvm(relbase.bionic, TestBcacheCephLvm):
    __test__ = True


class FocalTestBcacheCephLvm(relbase.focal, TestBcacheCephLvm):
    __test__ = True


# vi: ts=4 expandtab syntax=python
