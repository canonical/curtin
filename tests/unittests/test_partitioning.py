from unittest import TestCase
import mock
import parted
import curtin.commands.block_meta


class TestBlock(TestCase):
    storage_config = {
        "sda": {"id": "sda", "type": "disk", "ptable": "msdos",
                "serial": "DISK_1", "grub_device": "True"},
        "sdb": {"id": "sdb", "type": "disk", "ptable": "msdos"},
        "sda1": {"id": "sda1", "type": "partition", "offset": "512MB",
                 "size": "8GB", "device": "sda", "flag": "boot"},
        "sda2": {"id": "sda2", "type": "partition", "offset": "sda1+1",
                 "size": "1GB", "device": "sda"},
        "sda1_root": {"id": "sda1_root", "type": "format", "fstype": "ext4",
                      "volume": "sda1"},
        "sda2_home": {"id": "sda2_home", "type": "format", "fstype": "ext4",
                      "volume": "sda2"},
        "sda1_mount": {"id": "sda1_mount", "type": "mount", "path": "/",
                       "device": "sda1_root"},
        "sda2_mount": {"id": "sda2_mount", "type": "mount", "path": "/home",
                       "device": "sda2_home"}
    }

    @mock.patch("curtin.commands.block_meta.get_path_to_storage_volume")
    @mock.patch("curtin.commands.block_meta.parted")
    def test_parse_offset(self, mock_parted, mock_get_path_to_storage_volume):
        path = "/dev/sda1"
        offset = "sda1+1"
        pdisk = mock.create_autospec(parted.Disk)
        pdisk.device.sectorSize = "512"
        mock_get_path_to_storage_volume.return_value = path

        curtin.commands.block_meta.parse_offset(offset, pdisk,
                                                self.storage_config)
        mock_get_path_to_storage_volume.assert_called_with(
            "sda1", self.storage_config)
        pdisk.getPartitionByPath.assert_called_with(path)

        with self.assertRaises(ValueError):
            offset = "sda1"
            curtin.commands.block_meta.parse_offset(offset, pdisk,
                                                    self.storage_config)

        offset = "8GB"
        curtin.commands.block_meta.parse_offset(offset, pdisk,
                                                self.storage_config)
        mock_parted.sizeToSectors.assert_called_with(8, "GB", "512")

    @mock.patch("curtin.commands.block_meta.json")
    @mock.patch("curtin.util.load_command_config")
    @mock.patch("curtin.util.load_command_environment")
    @mock.patch("curtin.block.lookup_disk")
    @mock.patch("curtin.commands.block_meta.parted")
    def test_disk_handler(self, mock_parted, mock_lookup_disk, mock_util_env,
                          mock_util_cmd_cfg, mock_json):
        f_path = "/dev/null"
        mock_lookup_disk.return_value = "/dev/sda"
        mock_util_env.return_value = {"config": f_path}
        mock_util_cmd_cfg.return_value = {}

        curtin.commands.block_meta.disk_handler(self.storage_config.get("sda"),
                                                self.storage_config)

        mock_parted.getDevice.assert_called_with("/dev/sda")
        mock_parted.freshDisk.assert_called_with(
            mock_parted.getDevice(), "msdos")
        args, kwargs = mock_json.dump.call_args
        self.assertTrue({"grub_install_devices": ["/dev/sda"]} in args)

        with self.assertRaises(ValueError):
            curtin.commands.block_meta.disk_handler(
                self.storage_config.get("sdb"), self.storage_config)

# vi: ts=4 expandtab syntax=python
