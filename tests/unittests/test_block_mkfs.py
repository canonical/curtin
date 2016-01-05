from curtin.block import mkfs

from unittest import TestCase
import mock


class TestBlockMkfs(TestCase):

    def _get_config(self, fstype):
        return {"fstype": fstype, "type": "format", "id": "testfmt",
                "volume": "null", "label": "format1",
                "uuid": "fb26cc6c-ae73-11e5-9e38-2fb63f0c3155"}

    def _assert_same_flags(self, call, expected):
        for flag in expected:
            if type(flag) == list:
                flag_name = flag[0]
                flag_val = flag[1]
                self.assertIn(flag_name, call)
                flag_index = call.index(flag_name)
                self.assertTrue(len(call) > flag_index)
                self.assertEquals(call[flag_index + 1], flag_val)
                call.remove(flag_name)
                call.remove(flag_val)
            else:
                self.assertIn(flag, call)
                call.remove(flag)
        # Only remaining vals in call should be mkfs.fstype and dev path
        self.assertEquals(len(call), 2)

    @mock.patch("curtin.block.mkfs.block")
    @mock.patch("curtin.block.mkfs.util")
    def _run_mkfs_with_config(self, config, expected_cmd,
                              expected_flags, mock_util, mock_block,
                              release="wily"):
        # Pretend we are on wily as there are no known edge cases for it
        mock_util.lsb_release.return_value = {"codename": release}
        mock_block.is_valid_device.return_value = True

        mkfs.mkfs_from_config("/dev/null", config)
        self.assertTrue(mock_util.subp.called)
        calls = mock_util.subp.call_args_list
        self.assertEquals(len(calls), 1)

        # Get first function call, tuple of first positional arg and its
        # (nonexistant) keyword arg, and unpack to get cmd
        call = calls[0][0][0]
        self.assertEquals(call[0], expected_cmd)
        self._assert_same_flags(call, expected_flags)

    def test_mkfs_ext(self):
        conf = self._get_config("ext4")
        expected_flags = [["-L", "format1"], "-F", "-q",
                          ["-U", "fb26cc6c-ae73-11e5-9e38-2fb63f0c3155"]]
        self._run_mkfs_with_config(conf, "mkfs.ext4", expected_flags)

    def test_mkfs_btrfs(self):
        conf = self._get_config("btrfs")
        expected_flags = [["--label", "format1"], "--force",
                          ["--uuid", "fb26cc6c-ae73-11e5-9e38-2fb63f0c3155"]]
        self._run_mkfs_with_config(conf, "mkfs.btrfs", expected_flags)

        # Test precise+btrfs edge case, force should not be used
        expected_flags.remove("--force")
        self._run_mkfs_with_config(conf, "mkfs.btrfs", expected_flags,
                                   release="precise")

    def test_mkfs_fat(self):
        conf = self._get_config("fat32")
        expected_flags = [["-n", "format1"], ["-F", "32"]]
        self._run_mkfs_with_config(conf, "mkfs.fat", expected_flags)

        conf = self._get_config("fat")
        conf['fatsize'] = "16"
        expected_flags = [["-n", "format1"], ["-F", "16"]]
        self._run_mkfs_with_config(conf, "mkfs.fat", expected_flags)

    @mock.patch("curtin.block.mkfs.block")
    @mock.patch("curtin.block.mkfs.util")
    def test_mkfs_errors(self, mock_util, mock_block):
        # Should not proceed without fstype
        with self.assertRaises(ValueError):
            conf = self._get_config(None)
            self._run_mkfs_with_config(conf, "mkfs.ext4", [])

        # Should not proceed with invalid fstype
        with self.assertRaises(ValueError):
            conf = self._get_config("fakefilesystemtype")
            self._run_mkfs_with_config(conf, "mkfs.ext3", [])

        # Should not proceed if label is too long
        with self.assertRaises(ValueError):
            conf = self._get_config("ext4")
            conf['label'] = "thislabelislongerthan16chars"
            self._run_mkfs_with_config(conf, "mkfs.ext4", [])

        # Should not proceed with invalid block dev
        with self.assertRaises(ValueError):
            mock_block.is_valid_device.return_value = False
            mkfs.mkfs("/dev/null", "ext4", [])

        # Should not proceed without a block dev
        with self.assertRaises(ValueError):
            mock_block.is_valid_device.return_value = True
            mkfs.mkfs(None, "ext4", [])

        # Should not proceed with invalid flags
        with self.assertRaises(ValueError):
            mkfs.mkfs("/dev/null", "ext4", ["notarealflagtype"])
