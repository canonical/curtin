# This file is part of curtin. See LICENSE file for copyright and license info.

from unittest import skip
import mock
import curtin.commands.block_meta
from .helpers import CiTestCase

from sys import version_info
if version_info.major == 2:
    import __builtin__ as builtins
else:
    import builtins

parted = None  # FIXME: remove these tests entirely. This is here for flake8


@skip
class TestBlock(CiTestCase):
    storage_config = {
        "sda": {"id": "sda", "type": "disk", "ptable": "msdos",
                "serial": "DISK_1", "grub_device": "True"},
        "sdb": {"id": "sdb", "type": "disk", "ptable": "msdos"},
        "sda1": {"id": "sda1", "type": "partition", "number": 1,
                 "size": "8GB", "device": "sda", "flag": "boot"},
        "sda2": {"id": "sda2", "type": "partition", "number": 2,
                 "size": "1GB", "device": "sda"},
        "sda3": {"id": "sda3", "type": "partition", "number": 3,
                 "size": "2GB", "device": "sda"},
        "volgroup1": {"id": "volgroup1", "type": "lvm_volgroup", "devices":
                      ["sda3"], "name": "lvm_vg1"},
        "lvm_part1": {"id": "lvm_part1", "type": "lvm_partition", "volgroup":
                      "volgroup1", "size": "1G", "name": "lvm_p1"},
        "lvm_part2": {"id": "lvm_part2", "type": "lvm_partition", "volgroup":
                      "volgroup1", "name": "lvm_p2"},
        "bcache0": {"id": "bcache0", "type": "bcache", "backing_device":
                    "lvm_part1", "cache_device": "sdc1"},
        "crypt0_key": {"id": "crypt0", "type": "dm_crypt", "volume": "sdb1",
                       "key": "testkey"},
        "crypt0_keyfile": {"id": "crypt0", "type": "dm_crypt", "volume":
                           "sdb1", "keyfile": "testkeyfile"},
        "crypt0_key_keyfile": {"id": "crypt0", "type": "dm_crypt", "volume":
                               "sdb1", "key": "testkey", "keyfile":
                               "testkeyfile"},
        "raiddev": {"id": "raiddev", "type": "raid", "raidlevel": 1, "devices":
                    ["sdx1", "sdy1"], "spare_devices": ["sdz1"],
                    "name": "md0"},
        "fake0": {"id": "fake0", "type": "faketype"},
        "sda1_root": {"id": "sda1_root", "type": "format", "fstype": "ext4",
                      "volume": "sda1", "label": "root_part"},
        "sda2_home": {"id": "sda2_home", "type": "format", "fstype": "fat32",
                      "volume": "sda2"},
        "raid_format": {"id": "raid_format", "type": "format", "fstype":
                        "ext4", "volume": "raiddev"},
        "sda1_mount": {"id": "sda1_mount", "type": "mount", "path": "/",
                       "device": "sda1_root"},
        "sda2_mount": {"id": "sda2_mount", "type": "mount", "path": "/home",
                       "device": "sda2_home"},
        "raid_mount": {"id": "raid_mount", "type": "mount", "path":
                       "/srv/data", "device": "raid_format"}
    }

    @mock.patch("curtin.commands.block_meta.devsync")
    @mock.patch("curtin.commands.block_meta.glob")
    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.parted")
    def test_get_path_to_storage_volume(self, mock_parted, mock_block,
                                        mock_glob, mock_devsync):
        # Test disk
        mock_block.lookup_disk.side_effect = \
            lambda x: "/dev/fake/serial-%s" % x
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "sda", self.storage_config)
        self.assertEqual(path, "/dev/fake/serial-DISK_1")
        mock_devsync.assert_called_with("/dev/fake/serial-DISK_1")

        # Test partition
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "sda1", self.storage_config)
        mock_parted.getDevice.assert_called_with("/dev/fake/serial-DISK_1")
        self.assertTrue(mock_parted.newDisk.called)
        mock_devsync.assert_called_with("/dev/fake/serial-DISK_1")

        # Test lvm partition
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "lvm_part1", self.storage_config)
        self.assertEqual(path, "/dev/lvm_vg1/lvm_p1")
        mock_devsync.assert_called_with("/dev/lvm_vg1/lvm_p1")

        # Test dmcrypt
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "crypt0", self.storage_config)
        self.assertEqual(path, "/dev/mapper/crypt0")
        mock_devsync.assert_called_with("/dev/mapper/crypt0")

        # Test raid
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "raiddev", self.storage_config)
        self.assertEqual(path, "/dev/md0")
        mock_devsync.assert_called_with("/dev/md0")

        # Test bcache
        mock_glob.glob.return_value = ["/sys/block/bcache1/slaves/hd0",
                                       "/sys/block/bcache0/slaves/lvm_p1"]
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "bcache0", self.storage_config)
        self.assertEqual(path, "/dev/bcache0")

        with self.assertRaises(NotImplementedError):
            curtin.commands.block_meta.get_path_to_storage_volume(
                "fake0", self.storage_config)

    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.parted")
    def test_disk_handler(self, mock_parted, mock_get_path_to_storage_volume):
        disk_path = "/dev/sda"
        mock_get_path_to_storage_volume.return_value = disk_path

        curtin.commands.block_meta.disk_handler(self.storage_config.get("sda"),
                                                self.storage_config)

        self.assertTrue(mock_get_path_to_storage_volume.called)
        mock_parted.getDevice.assert_called_with(disk_path)
        mock_parted.freshDisk.assert_called_with(
            mock_parted.getDevice(), "msdos")

    @mock.patch("curtin.commands.block_meta.time")
    @mock.patch("curtin.commands.block_meta.os.path")
    @mock.patch("curtin.commands.block_meta.util")
    @mock.patch("curtin.commands.block_meta.parted")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    def test_partition_handler(self, mock_get_path_to_storage_volume,
                               mock_parted, mock_util, mock_path,
                               mock_time):
        mock_path.exists.return_value = True
        mock_get_path_to_storage_volume.return_value = "/dev/fake"
        mock_parted.sizeToSectors.return_value = parted.sizeToSectors(8, "GB",
                                                                      512)

        curtin.commands.block_meta.partition_handler(
            self.storage_config.get("sda1"), self.storage_config)

        mock_get_path_to_storage_volume.assert_called_with(
            "sda", self.storage_config)
        mock_parted.getDevice.assert_called_with(
            mock_get_path_to_storage_volume.return_value)
        self.assertTrue(mock_parted.newDisk.called)
        mock_parted.Geometry.assert_called_with(
            device=mock_parted.newDisk().device,
            start=2048,
            length=mock_parted.sizeToSectors.return_value)
        mock_parted.Partition().setFlag.assert_called_with(
            mock_parted.PARTITION_BOOT)

        curtin.commands.block_meta.partition_handler(
            self.storage_config.get("sda2"), self.storage_config)
        self.assertEqual(mock_parted.Partition().setFlag.call_count, 1)

        with self.assertRaises(ValueError):
            curtin.commands.block_meta.partition_handler({},
                                                         self.storage_config)

    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.util")
    def test_format_handler(self, mock_util, mock_get_path_to_storage_volume):
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"

        curtin.commands.block_meta.format_handler(
            self.storage_config.get("sda1_root"), self.storage_config)

        mock_util.subp.assert_called_with(
            ["mkfs.ext4", "-q", "-L", "root_part",
             mock_get_path_to_storage_volume.return_value])

        curtin.commands.block_meta.format_handler(
            self.storage_config.get("sda2_home"), self.storage_config)

        mock_util.subp.assert_called_with(
            ["mkfs.fat", "-F", "32",
             mock_get_path_to_storage_volume.return_value])

        curtin.commands.block_meta.format_handler(
            {"type": "format", "fstype": "invalid", "volume": "fake",
             "id": "fake1"}, self.storage_config)
        args = mock_util.subp.call_args_list
        self.assertTrue(mock.call(["which", "mkfs.invalid"]) in args)

    @mock.patch.object(builtins, "open")
    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.util")
    def test_mount_handler(self, mock_util, mock_get_path_to_storage_volume,
                           mock_block, mock_open):
        mock_util.load_command_environment.return_value = {"fstab":
                                                           "/tmp/dir/fstab",
                                                           "target":
                                                           "/tmp/mntdir"}
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"
        mock_block.get_volume_uuid.return_value = "UUID123"

        curtin.commands.block_meta.mount_handler(
            self.storage_config.get("sda2_mount"), self.storage_config)

        mock_util.ensure_dir.assert_called_with("/tmp/mntdir/home")
        mock_open.assert_called_with("/tmp/dir/fstab", "a")
        mock_util.subp.assert_called_with(["mount", "/dev/fake0",
                                          "/tmp/mntdir/home"])

        args = mock_get_path_to_storage_volume.call_args_list
        self.assertTrue(len(args) == 1)
        self.assertTrue(args[0] == mock.call("sda2", self.storage_config))
        mock_block.get_volume_uuid.assert_called_with("/dev/fake0")

        curtin.commands.block_meta.mount_handler(
            self.storage_config.get("raid_mount"), self.storage_config)

        mock_util.ensure_dir.assert_called_with("/tmp/mntdir/srv/data")
        args = mock_get_path_to_storage_volume.call_args_list
        self.assertTrue(len(args) == 3)
        self.assertTrue(args[2] == mock.call("raiddev", self.storage_config))

    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.util")
    def test_lvm_volgroup_handler(self, mock_util,
                                  mock_get_path_to_storage_volume):
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"

        curtin.commands.block_meta.lvm_volgroup_handler(
            self.storage_config.get("volgroup1"), self.storage_config)

        mock_util.subp.assert_called_with(
            ["vgcreate", "lvm_vg1",
             mock_get_path_to_storage_volume.return_value])

    @mock.patch("curtin.commands.block_meta.util")
    def test_lvm_partition_handler(self, mock_util):
        base_cmd = ["lvcreate", "lvm_vg1", "-n"]

        curtin.commands.block_meta.lvm_partition_handler(
            self.storage_config.get("lvm_part1"), self.storage_config)

        mock_util.subp.assert_called_with(base_cmd + ["lvm_p1", "-L", "1G"])

        curtin.commands.block_meta.lvm_partition_handler(
            self.storage_config.get("lvm_part2"), self.storage_config)

        mock_util.subp.assert_called_with(base_cmd + ["lvm_p2", "-l",
                                          "100%FREE"])

    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.os.remove")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.tempfile")
    @mock.patch.object(builtins, "open")
    @mock.patch("curtin.commands.block_meta.util")
    def test_dm_crypt_handler_key(self, mock_util, mock_open, mock_tempfile,
                                  mock_get_path_to_storage_volume, mock_remove,
                                  mock_block):
        tmp_path = "/tmp/tmpfile1"
        mock_util.load_command_environment.return_value = {"fstab":
                                                           "/tmp/dir/fstab"}
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"
        mock_tempfile.mkstemp.return_value = ["fp", tmp_path]
        mock_block.get_volume_uuid.return_value = "UUID123"

        curtin.commands.block_meta.dm_crypt_handler(
            self.storage_config.get("crypt0_key"), self.storage_config)

        mock_get_path_to_storage_volume.assert_called_with(
            "sdb1", self.storage_config)
        self.assertTrue(mock_tempfile.mkstemp.called)
        calls = mock_util.subp.call_args_list
        self.assertEqual(
            mock.call(["cryptsetup", "luksFormat",
                      mock_get_path_to_storage_volume.return_value, tmp_path]),
            calls[0])
        self.assertEqual(
            mock.call(["cryptsetup", "open", "--type", "luks",
                      mock_get_path_to_storage_volume.return_value, "crypt0",
                      "--key-file", tmp_path]),
            calls[1])
        mock_remove.assert_called_with(tmp_path)
        mock_open.assert_called_with("/tmp/dir/crypttab", "a")
        mock_block.get_volume_uuid.assert_called_with(
            mock_get_path_to_storage_volume.return_value)

    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.os.remove")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.tempfile")
    @mock.patch.object(builtins, "open")
    @mock.patch("curtin.commands.block_meta.util")
    def test_dm_crypt_handler_keyfile(self, mock_util, mock_open,
                                      mock_tempfile,
                                      mock_get_path_to_storage_volume,
                                      mock_remove, mock_block):
        mock_util.load_command_environment.return_value = {"fstab":
                                                           "/tmp/dir/fstab"}
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"
        mock_block.get_volume_uuid.return_value = "UUID123"

        config = self.storage_config["crypt0_keyfile"]
        curtin.commands.block_meta.dm_crypt_handler(
            config, self.storage_config)

        mock_get_path_to_storage_volume.assert_called_with(
            "sdb1", self.storage_config)
        self.assertFalse(mock_tempfile.mkstemp.called)
        calls = mock_util.subp.call_args_list
        self.assertEqual(
            mock.call(["cryptsetup", "luksFormat",
                      mock_get_path_to_storage_volume.return_value,
                      config['keyfile']]),
            calls[0])
        self.assertEqual(
            mock.call(["cryptsetup", "open", "--type", "luks",
                      mock_get_path_to_storage_volume.return_value, "crypt0",
                      "--key-file", config['keyfile']]),
            calls[1])
        self.assertFalse(mock_remove.called)
        mock_remove.assert_not_called()
        mock_block.get_volume_uuid.assert_called_with(
            mock_get_path_to_storage_volume.return_value)

    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.util")
    def test_dm_crypt_handler_key_and_keyfile(self, mock_util,
                                              mock_get_path_to_storage_volume,
                                              mock_block):
        mock_util.load_command_environment.return_value = {"fstab":
                                                           "/tmp/dir/fstab"}
        mock_get_path_to_storage_volume.return_value = "/dev/fake0"
        mock_block.get_volume_uuid.return_value = "UUID123"

        self.assertRaises(
            ValueError,
            curtin.commands.block_meta.dm_crypt_handler(
                self.storage_config.get("crypt0_key_keyfile"),
                self.storage_config))

    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch.object(builtins, "open")
    @mock.patch("curtin.commands.block_meta.util")
    def test_raid_handler(self, mock_util, mock_open,
                          mock_get_path_to_storage_volume):
        main_cmd = ["yes", "|", "mdadm", "--create", "/dev/md0", "--level=1",
                    "--raid-devices=2", "/dev/fake/sdx1", "/dev/fake/sdy1",
                    "--spare-devices=1", "/dev/fake/sdz1"]
        mock_util.load_command_environment.return_value = {"fstab":
                                                           "/tmp/dir/fstab"}
        mock_get_path_to_storage_volume.side_effect = \
            lambda x, y: "/dev/fake/%s" % x
        mock_util.subp.return_value = ("mdadm scan info", None)

        curtin.commands.block_meta.raid_handler(
            self.storage_config.get("raiddev"), self.storage_config)

        path_calls = list(args[0] for args, kwargs in
                          mock_get_path_to_storage_volume.call_args_list)
        subp_calls = mock_util.subp.call_args_list
        for path in self.storage_config.get("raiddev").get("devices") + \
                self.storage_config.get("raiddev").get("spare_devices"):
            self.assertTrue(path in path_calls)
            self.assertTrue(mock.call(["mdadm", "--zero-superblock",
                            mock_get_path_to_storage_volume.side_effect(path,
                                                                        None)])
                            in subp_calls)
        self.assertTrue(mock.call(" ".join(main_cmd), shell=True) in
                        subp_calls)
        self.assertTrue(mock.call(["mdadm", "--detail", "--scan"],
                        capture=True) in subp_calls)
        mock_open.assert_called_with("/tmp/dir/mdadm.conf", "w")

    @mock.patch.object(builtins, "open")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.util")
    def test_bcache_handler(self, mock_util, mock_get_path_to_storage_volume,
                            mock_open):
        mock_get_path_to_storage_volume.side_effect = ["/dev/fake0",
                                                       "/dev/fake1",
                                                       "/dev/fake0"]

        curtin.commands.block_meta.bcache_handler(
            self.storage_config.get("bcache0"), self.storage_config)

        calls = mock_util.subp.call_args_list
        self.assertTrue(mock.call(["modprobe", "bcache"]) == calls[0])
        self.assertTrue(mock.call(["make-bcache", "-B", "/dev/fake0", "-C",
                        "/dev/fake1"]) == calls[1])

# vi: ts=4 expandtab syntax=python
