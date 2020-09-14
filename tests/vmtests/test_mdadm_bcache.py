# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
import re
import textwrap
from unittest import SkipTest


class TestMdadmAbs(VMBaseClass):
    interactive = False
    test_type = 'storage'
    active_mdadm = "1"
    dirty_disks = True
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        mdadm --detail --scan > mdadm_status
        mdadm --detail --scan | grep -c ubuntu > mdadm_active1
        grep -c active /proc/mdstat > mdadm_active2
        ls /dev/disk/by-dname > ls_dname
        cat /proc/mdstat | tee mdstat
        ls -1 /sys/class/block | tee sys_class_block
        ls -1 /dev/md* | tee dev_md
        ls -al /sys/fs/bcache/* > lsal_sys_fs_bcache_star
        ls -al /dev/bcache* > lsal_dev_bcache_star
        ls -al /dev/bcache/by-uuid/ | cat >ls_al_bcache_byuuid
        ls -al /dev/bcache/by-label/ | cat >ls_al_bcache_bylabel
        ls -al /dev/md/* | cat >ls_al_dev_md

        exit 0
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
    dirty_disks = True
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
                     ('md0', 0)]
    bcache_dnames = [('cached_array', 0),
                     ('cached_array_2', 0),
                     ('cached_array_3', 0)]
    extra_disks = ['4G', '4G', '4G', '4G', '4G']
    extra_collect_scripts = TestMdadmAbs.extra_collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda6 > bcache_super_vda6
        bcache-super-show /dev/vda7 > bcache_super_vda7
        bcache-super-show /dev/md0 > bcache_super_md0
        ls /sys/fs/bcache > bcache_ls
        cat /sys/block/bcache0/bcache/cache_mode > bcache_cache_mode
        cat /sys/block/bcache1/bcache/cache_mode >> bcache_cache_mode
        cat /sys/block/bcache2/bcache/cache_mode >> bcache_cache_mode

        exit 0
        """)]

    def get_fstab_expected(self):
        rootdev = self._serial_to_kname('disk-a')
        data_kname = self._dname_to_kname('cached_array')
        normal_kname = self._dname_to_kname('cached_array_2')
        fulldisk_kname = self._dname_to_kname('cached_array_3')
        return [
            (self._kname_to_byuuid(rootdev + '2'), '/', 'defaults'),
            (self._bcache_to_byuuid(data_kname), '/media/data', 'defaults'),
            (self._bcache_to_byuuid(normal_kname),
             '/media/bcache_normal', 'defaults'),
            (self._bcache_to_byuuid(fulldisk_kname),
             '/media/bcachefoo_fulldiskascache_storage', 'defaults'),
        ]

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
            for line in self.load_collect_file(bcache_super).splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
                    if bcache_cset_uuid in found:
                        found[bcache_cset_uuid].append(bcache_super)
                    else:
                        found[bcache_cset_uuid] = [bcache_super]
            self.assertIsNotNone(bcache_cset_uuid)
            self.assertTrue(bcache_cset_uuid in
                            self.load_collect_file("bcache_ls").splitlines())

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

    def test_bcache_dnames(self):
        self.test_dname(disk_to_check=self.bcache_dnames)


class XenialGATestMdadmBcache(relbase.xenial_ga, TestMdadmBcacheAbs):
    __test__ = True


class XenialHWETestMdadmBcache(relbase.xenial_hwe, TestMdadmBcacheAbs):
    __test__ = True


class XenialEdgeTestMdadmBcache(relbase.xenial_edge, TestMdadmBcacheAbs):
    __test__ = True


class BionicTestMdadmBcache(relbase.bionic, TestMdadmBcacheAbs):
    __test__ = True


class FocalTestMdadmBcache(relbase.focal, TestMdadmBcacheAbs):
    __test__ = True

    @TestMdadmBcacheAbs.skip_by_date("1861941", fixby="2020-09-15")
    def test_fstab(self):
        return super().test_fstab()


class GroovyTestMdadmBcache(relbase.groovy, TestMdadmBcacheAbs):
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

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('md-uuid', 'md0'), '/', 'defaults')
        ]


class Centos70TestMirrorboot(centos_relbase.centos70_xenial,
                             TestMirrorbootAbs):
    __test__ = True


class XenialGATestMirrorboot(relbase.xenial_ga, TestMirrorbootAbs):
    __test__ = True


class XenialHWETestMirrorboot(relbase.xenial_hwe, TestMirrorbootAbs):
    __test__ = True


class XenialEdgeTestMirrorboot(relbase.xenial_edge, TestMirrorbootAbs):
    __test__ = True


class BionicTestMirrorboot(relbase.bionic, TestMirrorbootAbs):
    __test__ = True


class FocalTestMirrorboot(relbase.focal, TestMirrorbootAbs):
    __test__ = True


class GroovyTestMirrorboot(relbase.groovy, TestMirrorbootAbs):
    __test__ = True


class TestMirrorbootPartitionsAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/mirrorboot-msdos-partition.yaml"
    # initialize secondary disk
    extra_disks = ['10G']
    disk_to_check = [('main_disk', 1),
                     ('second_disk', 1),
                     ('md0', 2)]

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('md-uuid', 'md0p1'), '/', 'defaults')
        ]


class Centos70TestMirrorbootPartitions(centos_relbase.centos70_xenial,
                                       TestMirrorbootPartitionsAbs):
    __test__ = True


class XenialGATestMirrorbootPartitions(relbase.xenial_ga,
                                       TestMirrorbootPartitionsAbs):
    __test__ = True


class XenialHWETestMirrorbootPartitions(relbase.xenial_hwe,
                                        TestMirrorbootPartitionsAbs):
    __test__ = True


class XenialEdgeTestMirrorbootPartitions(relbase.xenial_edge,
                                         TestMirrorbootPartitionsAbs):
    __test__ = True


class BionicTestMirrorbootPartitions(relbase.bionic,
                                     TestMirrorbootPartitionsAbs):
    __test__ = True


class FocalTestMirrorbootPartitions(relbase.focal,
                                    TestMirrorbootPartitionsAbs):
    __test__ = True


class GroovyTestMirrorbootPartitions(relbase.groovy,
                                     TestMirrorbootPartitionsAbs):
    __test__ = True


class TestMirrorbootPartitionsUEFIAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/mirrorboot-uefi.yaml"
    # initialize secondary disk
    extra_disks = ['10G']
    disk_to_check = [('main_disk', 2),
                     ('second_disk', 3),
                     ('md0', 0),
                     ('md1', 0)]
    active_mdadm = "2"
    uefi = True
    nr_cpus = 2
    dirty_disks = True
    GRUB_RE = r'(?P<pkg>grub-pc)\s(?P<var>\S+)\smultiselect\s(?P<cfg>.*$)'

    extra_collect_scripts = TestMdadmAbs.extra_collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        debconf-get-selections > debconf_selections.txt
        ls -al /usr/lib/grub/* > usr_lib_grub.txt
        (cd /boot/efi && find .) | sort >  diska-part1-efi.out
        mount /dev/disk/by-id/virtio-disk-b-part1 /mnt
        (cd /mnt && find .) | sort > diskb-part1-efi.out
        umount /mnt
        exit 0
        """)]

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('md-uuid', 'md0'),
             '/', 'defaults'),
            (self._kname_to_uuid_devpath('md-uuid', 'md1'),
             '/var', 'defaults'),
        ]

    def test_grub_debconf_selections(self):
        """Verify we have grub2/efi_install_devices set correctly."""
        if self.target_distro not in ["ubuntu", "debian"]:
            raise SkipTest("debconf-selections not present in distro "
                           "%s" % self.target_release)

        selections = self.load_collect_file("debconf_selections.txt")
        found_selections = re.findall(self.GRUB_RE, selections, re.MULTILINE)
        disks_byid = ['/dev/disk/by-id/virtio-disk-a-part1',
                      '/dev/disk/by-id/virtio-disk-b-part1']
        choice = ", ".join(disks_byid)
        self.assertIn(
            ('grub-pc', 'grub-efi/install_devices', choice), found_selections)

    def test_backup_esp_matches_primary(self):
        if self.target_distro != "ubuntu":
            raise SkipTest("backup ESP supported only on Ubuntu")
        if self.target_release in [
                "trusty", "xenial", "bionic", "cosmic", "disco", "eoan"]:
            raise SkipTest("backup ESP supported only on >= Focal")
        primary_esp = self.load_collect_file("diska-part1-efi.out")
        backup_esp = self.load_collect_file("diskb-part1-efi.out")
        self.assertEqual(primary_esp, backup_esp)


class Centos70TestMirrorbootPartitionsUEFI(centos_relbase.centos70_xenial,
                                           TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class XenialGATestMirrorbootPartitionsUEFI(relbase.xenial_ga,
                                           TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class XenialHWETestMirrorbootPartitionsUEFI(relbase.xenial_hwe,
                                            TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class XenialEdgeTestMirrorbootPartitionsUEFI(relbase.xenial_edge,
                                             TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class BionicTestMirrorbootPartitionsUEFI(relbase.bionic,
                                         TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class FocalTestMirrorbootPartitionsUEFI(relbase.focal,
                                        TestMirrorbootPartitionsUEFIAbs):
    __test__ = True


class GroovyTestMirrorbootPartitionsUEFI(relbase.groovy,
                                         TestMirrorbootPartitionsUEFIAbs):
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
                     ('os-raid1', 0)]

    def get_fstab_expected(self):
        kname = self._mdname_to_kname('os-raid1')
        return [
            (self._kname_to_uuid_devpath('md-uuid', kname),
             '/',
             'defaults'),
        ]


class Centos70TestRaid5boot(centos_relbase.centos70_xenial, TestRaid5bootAbs):
    __test__ = True


class XenialGATestRaid5boot(relbase.xenial_ga, TestRaid5bootAbs):
    __test__ = True


class XenialHWETestRaid5boot(relbase.xenial_hwe, TestRaid5bootAbs):
    __test__ = True


class XenialEdgeTestRaid5boot(relbase.xenial_edge, TestRaid5bootAbs):
    __test__ = True


class BionicTestRaid5boot(relbase.bionic, TestRaid5bootAbs):
    __test__ = True


class FocalTestRaid5boot(relbase.focal, TestRaid5bootAbs):
    __test__ = True


class GroovyTestRaid5boot(relbase.groovy, TestRaid5bootAbs):
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
    extra_collect_scripts = (
        TestMdadmAbs.extra_collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        mdadm --detail --scan > mdadm_detail

        exit 0
        """)])

    def test_raid6_output_files_exist(self):
        self.output_files_exist(
            ["mdadm_detail"])

    def test_mdadm_custom_name(self):
        # the raid6boot.yaml sets this name, check if it was set
        self.check_file_regex("mdadm_detail", r"ubuntu:foobar")

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('md-uuid', 'md0'), '/', 'defaults'),
        ]


class Centos70TestRaid6boot(centos_relbase.centos70_xenial, TestRaid6bootAbs):
    __test__ = True


class XenialGATestRaid6boot(relbase.xenial_ga, TestRaid6bootAbs):
    __test__ = True


class XenialHWETestRaid6boot(relbase.xenial_hwe, TestRaid6bootAbs):
    __test__ = True


class XenialEdgeTestRaid6boot(relbase.xenial_edge, TestRaid6bootAbs):
    __test__ = True


class BionicTestRaid6boot(relbase.bionic, TestRaid6bootAbs):
    __test__ = True


class FocalTestRaid6boot(relbase.focal, TestRaid6bootAbs):
    __test__ = True


class GroovyTestRaid6boot(relbase.groovy, TestRaid6bootAbs):
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

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('md-uuid', 'md0'), '/', 'defaults'),
        ]


class Centos70TestRaid10boot(centos_relbase.centos70_xenial,
                             TestRaid10bootAbs):
    __test__ = True


class XenialGATestRaid10boot(relbase.xenial_ga, TestRaid10bootAbs):
    __test__ = True


class XenialHWETestRaid10boot(relbase.xenial_hwe, TestRaid10bootAbs):
    __test__ = True


class XenialEdgeTestRaid10boot(relbase.xenial_edge, TestRaid10bootAbs):
    __test__ = True


class BionicTestRaid10boot(relbase.bionic, TestRaid10bootAbs):
    __test__ = True


class FocalTestRaid10boot(relbase.focal, TestRaid10bootAbs):
    __test__ = True


class GroovyTestRaid10boot(relbase.groovy, TestRaid10bootAbs):
    __test__ = True


class TestAllindataAbs(TestMdadmAbs):
    # more complex, needs more time
    # alternative config for more complex setup
    conf_file = "examples/tests/allindata.yaml"
    # we have to avoid a systemd hang due to the way it handles dmcrypt
    extra_kern_args = "--- luks=no"
    active_mdadm = "4"
    # running in dirty mode catches some race/errors with mdadm_stop
    nr_cpus = 2
    dirty_disks = True
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

    extra_collect_scripts = (
        TestMdadmAbs.extra_collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        cat /etc/crypttab > crypttab
        yes "testkey" | cryptsetup open /dev/vg1/lv3 dmcrypt0 --type luks
        ls -laF /dev/mapper/dmcrypt0 > mapper
        mkdir -p /tmp/xfstest
        mount /dev/mapper/dmcrypt0 /tmp/xfstest
        xfs_info /tmp/xfstest/ > xfs_info

        exit 0
        """)])

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

    def get_fstab_expected(self):
        return [
            (self._kname_to_uuid_devpath('dm-uuid', 'dm-0'),
             '/srv/data', 'defaults'),
            (self._kname_to_uuid_devpath('dm-uuid', 'dm-1'),
             '/srv/backup', 'defaults'),
        ]


class XenialGATestAllindata(relbase.xenial_ga, TestAllindataAbs):
    __test__ = True


class XenialHWETestAllindata(relbase.xenial_hwe, TestAllindataAbs):
    __test__ = True


class XenialEdgeTestAllindata(relbase.xenial_edge, TestAllindataAbs):
    __test__ = True


class BionicTestAllindata(relbase.bionic, TestAllindataAbs):
    __test__ = True


class FocalTestAllindata(relbase.focal, TestAllindataAbs):
    __test__ = True


class GroovyTestAllindata(relbase.groovy, TestAllindataAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
