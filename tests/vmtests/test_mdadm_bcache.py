from . import VMBaseClass
from unittest import TestCase

import textwrap
import os


class TestMdadmAbs(VMBaseClass, TestCase):
    __test__ = False
    repo = "maas-daily"
    arch = "amd64"
    install_timeout = 600
    boot_timeout = 100
    interactive = False
    extra_disks = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        mdadm --detail --scan > mdadm_status
        ls /dev/disk/by-dname > ls_dname
        """)]

    def test_mdadm_status(self):
        with open(os.path.join(self.td.mnt, "mdadm_status"), "r") as fp:
            mdadm_status = fp.read()
        self.assertTrue("/dev/md/ubuntu" in mdadm_status)

    def test_mdadm_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "mdadm_status", "ls_dname"])


class TestMdadmBcacheAbs(TestMdadmAbs):
    conf_file = "examples/tests/mdadm_bcache.yaml"
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'main_disk': 3,
                     'main_disk': 4,
                     'main_disk': 5,
                     'main_disk': 6,
                     'md0': 0,
                     'cached_array': 0}

    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        bcache-super-show /dev/vda6 > bcache_super_vda6
        ls /sys/fs/bcache > bcache_ls
        """)]
    fstab_expected = {
        '/dev/bcache0': '/media/data'
    }

    def test_bcache_output_files_exist(self):
        self.output_files_exist(["bcache_super_vda6", "bcache_ls"])

    def test_bcache_status(self):
        bcache_cset_uuid = None
        with open(os.path.join(self.td.mnt, "bcache_super_vda6"), "r") as fp:
            for line in fp.read().splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        with open(os.path.join(self.td.mnt, "bcache_ls"), "r") as fp:
            self.assertTrue(bcache_cset_uuid in fp.read().splitlines())


class WilyTestMdadmBcache(TestMdadmBcacheAbs):
    __test__ = True
    release = "wily"


class VividTestMdadmBcache(TestMdadmBcacheAbs):
    __test__ = True
    release = "vivid"


class TestMirrorbootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/mirrorboot.yaml"
    # initialize secondary disk
    extra_disks = ['4G']
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'second_disk': 1,
                     'md0': 0}


class WilyTestMirrorboot(TestMirrorbootAbs):
    __test__ = True
    release = "wily"


class VividTestMirrorboot(TestMirrorbootAbs):
    __test__ = True
    release = "vivid"


class TestRaid5bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid5boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G']
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'second_disk': 1,
                     'third_disk': 1,
                     'md0': 0}


class WilyTestRaid5boot(TestRaid5bootAbs):
    __test__ = True
    release = "wily"


class VividTestRaid5boot(TestRaid5bootAbs):
    __test__ = True
    release = "vivid"


class TestRaid6bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid6boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G', '4G']
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'second_disk': 1,
                     'third_disk': 1,
                     'fourth_disk': 1,
                     'md0': 0}


class WilyTestRaid6boot(TestRaid6bootAbs):
    __test__ = True
    release = "wily"


class VividTestRaid6boot(TestRaid6bootAbs):
    __test__ = True
    release = "vivid"


class TestRaid10bootAbs(TestMdadmAbs):
    # alternative config for more complex setup
    conf_file = "examples/tests/raid10boot.yaml"
    # initialize secondary disk
    extra_disks = ['4G', '4G', '4G']
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'second_disk': 1,
                     'third_disk': 1,
                     'fourth_disk': 1,
                     'md0': 0}


class WilyTestRaid10boot(TestRaid10bootAbs):
    __test__ = True
    release = "wily"


class VividTestRaid10boot(TestRaid10bootAbs):
    __test__ = True
    release = "vivid"


class TestAllindataAbs(TestMdadmBcacheAbs):
    # more complex, needs more time
    install_timeout = 900
    boot_timeout = 200
    # alternative config for more complex setup
    conf_file = "examples/tests/allindata.yaml"
    # we have to avoid a systemd hang due to the way it handles dmcrypt
    extra_kern_args = "luks=no"
    # initialize secondary disk
    extra_disks = ['5G', '5G', '5G']
    disk_to_check = {'main_disk': 1,
                     'main_disk': 2,
                     'main_disk': 3,
                     'main_disk': 4,
                     'main_disk': 5,
                     'second_disk': 1,
                     'second_disk': 2,
                     'second_disk': 3,
                     'second_disk': 4,
                     'third_disk': 1,
                     'third_disk': 2,
                     'third_disk': 3,
                     'third_disk': 4,
                     'fourth_disk': 1,
                     'fourth_disk': 2,
                     'fourth_disk': 3,
                     'fourth_disk': 4,
                     'md0': 0,
                     'md1': 0,
                     'md2': 0,
                     'md3': 0,
                     'vg1-lv1': 0,
                     'vg1-lv2': 0}
    collect_scripts = TestMdadmAbs.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        pvdisplay -C --separator = -o vg_name,pv_name --noheadings > pvs
        lvdisplay -C --separator = -o lv_name,vg_name --noheadings > lvs
        cat /etc/crypttab > crypttab
        yes "testkey" | cryptsetup open /dev/md0 dmcrypt0 --type luks
        ls -laF /dev/mapper/dmcrypt0 | echo wrong > mapper
        mkdir -p /tmp/xfstest
        mount /dev/mapper/dmcrypt0 /tmp/xfstest
        xfs_info /tmp/xfstest/ > xfsinfo
        """)]
    fstab_expected = {
        '/dev/vg1/lv1': '/srv/data',
        '/dev/vg1/lv2': '/srv/backup',
    }

    def test_output_files_exist(self):
        self.output_files_exist(["pvs", "lvs", "crypttab", "mapper",
                                 "xfsinfo"])

    def test_lvs(self):
        self.check_file_content("lvs", "lv1=vg1")
        self.check_file_content("lvs", "lv2=vg1")

    def test_pvs(self):
        self.check_file_content("pvs", "vg1=/dev/vda5")
        self.check_file_content("pvs", "vg1=/dev/vda6")

    def test_dmcrypt(self):
        self.check_file_content("crypttab", "dmcrypt0")
        self.check_file_content("crypttab", "luks")
        self.check_file_content("mapper", "dmcrypt0: symbolic link")
        self.check_file_content("xfsinfo", "meta-data")


class WilyTestAllindata(TestAllindataAbs):
    __test__ = True
    release = "wily"


class VividTestAllindata(TestAllindataAbs):
    __test__ = True
    release = "vivid"
