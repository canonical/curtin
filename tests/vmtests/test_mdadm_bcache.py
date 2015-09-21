from . import VMBaseClass
from unittest import TestCase

import textwrap
import os


class TestMdadmBcacheAbs(VMBaseClass):
    __test__ = False
    conf_file = "examples/tests/mdadm_bcache.yaml"
    install_timeout = 600
    boot_timeout = 100
    interactive = False
    extra_disks = []
    user_data = textwrap.dedent("""\
        #cloud-config
        password: passw0rd
        chpasswd: { expire: False }
        bootcmd:
          - mkdir -p /media/output
        runcmd:
          - cat /etc/fstab > /media/output/fstab
          - mdadm --detail --scan > /media/output/mdadm_status
          - bcache-super-show /dev/vda6 > /media/output/bcache_super_vda6
          - ls /sys/fs/bcache > /media/output/bcache_ls
          - ls /dev/disk/by-dname > /media/output/ls_dname
          - [tar, -C, /media/output, -cf, /dev/vdb, .]
        power_state:
          mode: poweroff
        """)

    def test_fstab(self):
        with open(os.path.join(self.td.mnt, "fstab")) as fp:
            fstab_lines = fp.readlines()
        fstab_entry = None
        for line in fstab_lines:
            if "/dev/bcache0" in line:
                fstab_entry = line
                break
        self.assertIsNotNone(fstab_entry)
        self.assertEqual(fstab_entry.split(' ')[1], "/media/data")

    def test_mdadm_status(self):
        with open(os.path.join(self.td.mnt, "mdadm_status"), "r") as fp:
            mdadm_status = fp.read()
        self.assertTrue("/dev/md/ubuntu" in mdadm_status)

    def test_output_files_exist(self):
        self.output_files_exist(
            ["fstab", "mdadm_status", "bcache_super_vda6", "bcache_ls"])

    def test_dname(self):
        with open(os.path.join(self.td.mnt, "ls_dname"), "r") as fp:
            contents = fp.read().splitlines()
        for link in list(("main_disk-part%s" % i for i in range(1, 6))):
            self.assertIn(link, contents)
        self.assertIn("md0", contents)
        self.assertIn("cached_array", contents)
        self.assertIn("main_disk", contents)

    def test_bcache_status(self):
        bcache_cset_uuid = None
        with open(os.path.join(self.td.mnt, "bcache_super_vda6"), "r") as fp:
            for line in fp.read().splitlines():
                if line != "" and line.split()[0] == "cset.uuid":
                    bcache_cset_uuid = line.split()[-1].rstrip()
        self.assertIsNotNone(bcache_cset_uuid)
        with open(os.path.join(self.td.mnt, "bcache_ls"), "r") as fp:
            self.assertTrue(bcache_cset_uuid in fp.read().splitlines())


class WilyTestMdadmBcache(TestMdadmBcacheAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestMdadmBcache(TestMdadmBcacheAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"
