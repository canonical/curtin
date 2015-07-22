from unittest import TestCase
import mock
import os
import parted
import curtin.commands.block_meta

from sys import version_info
if version_info.major == 2:
    import __builtin__ as builtins
else:
    import builtins


class TestBlock(TestCase):
    storage_config = {
        "sda": {"id": "sda", "type": "disk", "ptable": "msdos",
                "serial": "DISK_1", "grub_device": "True"},
        "sdb": {"id": "sdb", "type": "disk", "ptable": "msdos"},
        "sda1": {"id": "sda1", "type": "partition", "offset": "512MB",
                 "size": "8GB", "device": "sda", "flag": "boot"},
        "sda2": {"id": "sda2", "type": "partition", "offset": "sda1+1",
                 "size": "1GB", "device": "sda"},
        "sda3": {"id": "sda3", "type": "partition", "offset": "sda2+1",
                 "size": "2GB", "device": "sda"},
        "fake0": {"id": "fake0", "type": "faketype"},
        "sda1_root": {"id": "sda1_root", "type": "format", "fstype": "ext4",
                      "volume": "sda1"},
        "sda2_home": {"id": "sda2_home", "type": "format", "fstype": "fat32",
                      "volume": "sda2"},
        "sda1_mount": {"id": "sda1_mount", "type": "mount", "path": "/",
                       "device": "sda1_root"},
        "sda2_mount": {"id": "sda2_mount", "type": "mount", "path": "/home",
                       "device": "sda2_home"},
    }

    @mock.patch("curtin.commands.block_meta.devsync")
    @mock.patch("curtin.commands.block_meta.block")
    @mock.patch("curtin.commands.block_meta.parted")
    def test_get_path_to_storage_volume(self, mock_parted, mock_block,
                                        mock_devsync):
        # Test disk
        mock_block.lookup_disk.side_effect = \
            lambda x: "/dev/fake/serial-%s" % x
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "sda", self.storage_config)
        self.assertTrue(path == "/dev/fake/serial-DISK_1")
        mock_devsync.assert_called_with("/dev/fake/serial-DISK_1")

        # Test partition
        path = curtin.commands.block_meta.get_path_to_storage_volume(
            "sda1", self.storage_config)
        mock_parted.getDevice.assert_called_with("/dev/fake/serial-DISK_1")
        self.assertTrue(mock_parted.newDisk.called)
        mock_devsync.assert_called_with("/dev/fake/serial-DISK_1")

        # Test errors
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

    @mock.patch("curtin.commands.block_meta.parted")
    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    def test_partition_handler(self, mock_get_path_to_storage_volume,
                               mock_parted):
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
            start=62,
            length=mock_parted.sizeToSectors.return_value)
        mock_parted.Partition().setFlag.assert_called_with(
            mock_parted.PARTITION_BOOT)

        curtin.commands.block_meta.partition_handler(
            self.storage_config.get("sda2"), self.storage_config)
        self.assertEqual(mock_parted.Partition().setFlag.call_count, 1)

        with self.assertRaises(ValueError):
            curtin.commands.block_meta.partition_handler({},
                                                         self.storage_config)

    @mock.patch("curtin.commands.block_meta.util")
    def test_format_handler(self, mock_util):
        curtin.commands.block_meta.format_handler(
            self.storage_config.get("sda1_root"), self.storage_config)

        mock_util.subp.assert_called_with(["curtin", "mkfs", "sda1_root"],
                                          env=os.environ.copy())

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

# vi: ts=4 expandtab syntax=python
