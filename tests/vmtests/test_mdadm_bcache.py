from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap
import os


class TestMdadmAbs(VMBaseClass):
    interactive = False
    extra_disks = []
    active_mdadm = "1"
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        mdadm --detail --scan > mdadm_status
        mdadm --detail --scan | grep -c ubuntu > mdadm_active1
        grep -c active /proc/mdstat > mdadm_active2
        ls /dev/disk/by-dname > ls_dname
        """)]

    def test_mdadm_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "mdadm_status", "mdadm_active1", "mdadm_active2",
             "ls_dname"])

    def test_mdadm_status(self):
        # ubuntu:<ID> is the name assigned to the md array
        self.check_file_regex("mdadm_status", r"ubuntu:[0-9]*")
        self.check_file_strippedline("mdadm_active1", self.active_mdadm)
        self.check_file_strippedline("mdadm_active2", self.active_mdadm)


class TestMdadmBcacheAbs(TestMdadmAbs):
    arch_skip = [
        "s390x",  # lp:1565029
        ]
    conf_file = "examples/tests/mdadm_bcache.yaml"
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('main_disk', 3),
                     ('main_disk', 4),
                     ('main_disk', 5),
                     ('main_disk', 6),
                     ('md0', 0),
                     ('cached_array', 0),
                     ('cached_array_2', 0)]
    extra_disks = ['4G', '4G']
    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda6 > bcache_super_vda6
        bcache-super-show /dev/vda7 > bcache_super_vda7
        bcache-super-show /dev/md0 > bcache_super_md0
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        cat /sys/block/bcache1/bcache/cache_mode >> bcache_cache_mode
        cat /sys/block/bcache2/bcache/cache_mode >> bcache_cache_mode
        cat /proc/mounts > proc_mounts
        """)]
    fstab_expected = {
        '/dev/vda1': '/media/sda1',
        '/dev/vda7': '/boot',
        '/dev/bcache1': '/media/data',
        '/dev/bcache0': '/media/bcache_normal',
        '/dev/bcache2': '/media/bcachefoo_fulldiskascache_storage'
    }

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_vda6",
                                 "bcache_super_vda7",
                                 "bcache_super_md0",
                                 "bcache_ls",
                                 "bcache_cache_mode"])

    def test_bcache_status(self):
        bcache_supers = [
            "bcache_super_vda6",
            "bcache_super_vda7",
            "bcache_super_md0",
        ]
        bcache_cset_uuid = None
        found = {}
        for bcache_super in bcache_supers:
            with open(os.path.join(self.td.collect, bcache_super), "r") as fp:
                for line in fp.read().splitlines():
                    if line != "" and line.split()[0] == "cset.uuid":
                        bcache_cset_uuid = line.split()[-1].rstrip()
                        if bcache_cset_uuid in found:
                            found[bcache_cset_uuid].append(bcache_super)
                        else:
                            found[bcache_cset_uuid] = [bcache_super]
            self.assertIsNotNone(bcache_cset_uuid)
            with open(os.path.join(self.td.collect, "bcache_ls"), "r") as fp:
                self.assertTrue(bcache_cset_uuid in fp.read().splitlines())

        # one cset.uuid for all devices
        self.assertEqual(len(found), 1)

        # three devices with same cset.uuid
        self.assertEqual(len(found[bcache_cset_uuid]), 3)

        # check the cset.uuid in the dict
        self.assertEqual(list(found.keys()).pop(),
                         bcache_cset_uuid)

    def test_bcache_cachemode(self):
        # definition is on order 0->back,1->through,2->around
        # but after reboot it can be anything since order is not guaranteed
        # until we find a way to redetect the order we just check that all
        # three are there
        self.check_file_regex("bcache_cache_mode", r"\[writeback\]")
        self.check_file_regex("bcache_cache_mode", r"\[writethrough\]")
        self.check_file_regex("bcache_cache_mode", r"\[writearound\]")


class TrustyTestMdadmBcache(relbase.trusty, TestMdadmBcacheAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestMdadmBcache(relbase.trusty_hwe_u, TrustyTestMdadmBcache):
    __test__ = True


class VividTestMdadmBcache(relbase.vivid, TestMdadmBcacheAbs):
    __test__ = True


class WilyTestMdadmBcache(relbase.wily, TestMdadmBcacheAbs):
    __test__ = True


class XenialTestMdadmBcache(relbase.xenial, TestMdadmBcacheAbs):
    __test__ = True


class TestMirrorbootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/mirrorboot.yaml"
    # initialize secondary disk
    extra_disks = ['4G']
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('second_disk', 1),
                     ('md0', 0)]


class TrustyTestMirrorboot(relbase.trusty, TestMirrorbootAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestMirrorboot(relbase.trusty_hwe_u, TrustyTestMirrorboot):
    # This tests kernel upgrade in target
    __test__ = True


class VividTestMirrorboot(relbase.vivid, TestMirrorbootAbs):
    __test__ = True


class WilyTestMirrorboot(relbase.wily, TestMirrorbootAbs):
    __test__ = True


class XenialTestMirrorboot(relbase.xenial, TestMirrorbootAbs):
    __test__ = True


class TestRaid5bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid5boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G']
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('second_disk', 1),
                     ('third_disk', 1),
                     ('md0', 0)]


class TrustyTestRaid5Boot(relbase.trusty, TestRaid5bootAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestRaid5Boot(relbase.trusty_hwe_u, TrustyTestRaid5Boot):
    # This tests kernel upgrade in target
    __test__ = True


class VividTestRaid5boot(relbase.vivid, TestRaid5bootAbs):
    __test__ = True


class WilyTestRaid5boot(relbase.wily, TestRaid5bootAbs):
    __test__ = True


class XenialTestRaid5boot(relbase.xenial, TestRaid5bootAbs):
    __test__ = True


class TestRaid6bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid6boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G', '4G']
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('second_disk', 1),
                     ('third_disk', 1),
                     ('fourth_disk', 1),
                     ('md0', 0)]
    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        mdadm --detail --scan > mdadm_detail
        """)]

    def test_raid6_output_files_exist(self):
        self.output_files_exist(
            ["mdadm_detail"])

    def test_mdadm_custom_name(self):
        # the raid6boot.yaml sets this name, check if it was set
        self.check_file_regex("mdadm_detail", r"ubuntu:foobar")


class TrustyTestRaid6boot(relbase.trusty, TestRaid6bootAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestRaid6boot(relbase.trusty_hwe_u, TrustyTestRaid6boot):
    __test__ = True


class VividTestRaid6boot(relbase.vivid, TestRaid6bootAbs):
    __test__ = True


class WilyTestRaid6boot(relbase.wily, TestRaid6bootAbs):
    __test__ = True


class XenialTestRaid6boot(relbase.xenial, TestRaid6bootAbs):
    __test__ = True


class TestRaid10bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid10boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G', '4G']
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('second_disk', 1),
                     ('third_disk', 1),
                     ('fourth_disk', 1),
                     ('md0', 0)]


class TrustyTestRaid10boot(relbase.trusty, TestRaid10bootAbs):
    __test__ = True

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestRaid10boot(relbase.trusty_hwe_u, TrustyTestRaid10boot):
    __test__ = True


class VividTestRaid10boot(relbase.vivid, TestRaid10bootAbs):
    __test__ = True


class WilyTestRaid10boot(relbase.wily, TestRaid10bootAbs):
    __test__ = True


class XenialTestRaid10boot(relbase.xenial, TestRaid10bootAbs):
    __test__ = True


class TestAllindataAbs(TestMdadmAbs):
    # more complex, needs more time
    # alternative config for more complex setup
    conf_file = "examples/tests/allindata.yaml"
    # we have to avoid a systemd hang due to the way it handles dmcrypt
    extra_kern_args = "--- luks=no"
    active_mdadm = "4"
    # initialize secondary disk
    extra_disks = ['5G', '5G', '5G']
    disk_to_check = [('main_disk', 1),
                     ('main_disk', 2),
                     ('main_disk', 3),
                     ('main_disk', 4),
                     ('main_disk', 5),
                     ('second_disk', 1),
                     ('second_disk', 2),
                     ('second_disk', 3),
                     ('second_disk', 4),
                     ('third_disk', 1),
                     ('third_disk', 2),
                     ('third_disk', 3),
                     ('third_disk', 4),
                     ('fourth_disk', 1),
                     ('fourth_disk', 2),
                     ('fourth_disk', 3),
                     ('fourth_disk', 4),
                     ('md0', 0),
                     ('md1', 0),
                     ('md2', 0),
                     ('md3', 0),
                     ('vg1-lv1', 0),
                     ('vg1-lv2', 0)]

    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        cat /etc/crypttab > crypttab
        yes "testkey" | cryptsetup open /dev/vg1/lv3 dmcrypt0 --type luks
        ls -laF /dev/mapper/dmcrypt0 > mapper
        mkdir -p /tmp/xfstest
        mount /dev/mapper/dmcrypt0 /tmp/xfstest
        xfs_info /tmp/xfstest/ > xfs_info
        """)]
    fstab_expected = {
        '/dev/vg1/lv1': '/srv/data',
        '/dev/vg1/lv2': '/srv/backup',
    }

    def test_output_files_exist(self):
        self.output_files_exist(["pvs", "lvs", "crypttab", "mapper",
                                 "xfs_info"])

    def test_lvs(self):
        self.check_file_strippedline("lvs", "lv1=vg1")
        self.check_file_strippedline("lvs", "lv2=vg1")
        self.check_file_strippedline("lvs", "lv3=vg1")

    def test_pvs(self):
        self.check_file_strippedline("pvs", "vg1=/dev/md0")
        self.check_file_strippedline("pvs", "vg1=/dev/md1")
        self.check_file_strippedline("pvs", "vg1=/dev/md2")
        self.check_file_strippedline("pvs", "vg1=/dev/md3")

    def test_dmcrypt(self):
        self.check_file_regex("crypttab", r"dmcrypt0.*luks")
        self.check_file_regex("mapper", r"^lrwxrwxrwx.*/dev/mapper/dmcrypt0")
        self.check_file_regex("xfs_info", r"^meta-data=/dev/mapper/dmcrypt0")


class TrustyTestAllindata(relbase.trusty, TestAllindataAbs):
    __test__ = False  # luks=no does not disable mounting of device

    # FIXME(LP: #1523037): dname does not work on trusty
    # when dname works on trusty, then we need to re-enable by removing line.
    def test_dname(self):
        print("test_dname does not work for Trusty")

    def test_ptable(self):
        print("test_ptable does not work for Trusty")


class TrustyHWEUTestAllindata(relbase.trusty_hwe_u, TrustyTestAllindata):
    __test__ = False  # lukes=no does not disable mounting of device


class VividTestAllindata(relbase.vivid, TestAllindataAbs):
    __test__ = True


class WilyTestAllindata(relbase.wily, TestAllindataAbs):
    __test__ = True


class XenialTestAllindata(relbase.xenial, TestAllindataAbs):
    __test__ = True
