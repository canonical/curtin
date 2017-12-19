from curtin.block import mkfs

from unittest import TestCase
import mock


class TestBlockMkfs(TestCase):
    test_uuid = "fb26cc6c-ae73-11e5-9e38-2fb63f0c3155"

    def _get_config(self, fstype):
        return {"fstype": fstype, "type": "format", "id": "testfmt",
                "volume": "null", "label": "format1",
                "uuid": self.test_uuid}

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
    @mock.patch("curtin.block.mkfs.os")
    @mock.patch("curtin.block.mkfs.util")
    def _run_mkfs_with_config(self, config, expected_cmd, expected_flags,
                              mock_util, mock_os, mock_block,
                              release="wily", strict=False):
        # Pretend we are on wily as there are no known edge cases for it
        mock_util.lsb_release.return_value = {"codename": release}
        mock_os.path.exists.return_value = True

        mkfs.mkfs_from_config("/dev/null", config, strict=strict)
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
        expected_flags = [["-L", "format1"], "-F",
                          ["-U", self.test_uuid]]
        self._run_mkfs_with_config(conf, "mkfs.ext4", expected_flags)

    def test_mkfs_btrfs(self):
        conf = self._get_config("btrfs")
        expected_flags = [["--label", "format1"], "--force",
                          ["--uuid", self.test_uuid]]
        self._run_mkfs_with_config(conf, "mkfs.btrfs", expected_flags)

    def test_mkfs_btrfs_on_precise(self):
        # Test precise+btrfs where there is no force or uuid
        conf = self._get_config("btrfs")
        expected_flags = [["--label", "format1"]]
        self._run_mkfs_with_config(conf, "mkfs.btrfs", expected_flags,
                                   release="precise")

    def test_mkfs_btrfs_on_trusty(self):
        # Test trusty btrfs where there is no uuid
        conf = self._get_config("btrfs")
        expected_flags = [["--label", "format1"], "--force"]
        self._run_mkfs_with_config(conf, "mkfs.btrfs", expected_flags,
                                   release="trusty")

    def test_mkfs_fat(self):
        conf = self._get_config("fat32")
        expected_flags = [["-n", "format1"], ["-F", "32"]]
        self._run_mkfs_with_config(conf, "mkfs.vfat", expected_flags)

    def test_mkfs_invalid_fstype(self):
        """Do not proceed if fstype is None or invalid"""
        with self.assertRaises(ValueError):
            conf = self._get_config(None)
            self._run_mkfs_with_config(conf, "mkfs.ext4", [])
        with self.assertRaises(ValueError):
            conf = self._get_config("fakefilesystemtype")
            self._run_mkfs_with_config(conf, "mkfs.ext3", [])

    def test_mkfs_invalid_label(self):
        """Do not proceed if filesystem label is too long"""
        with self.assertRaises(ValueError):
            conf = self._get_config("ext4")
            conf['label'] = "thislabelislongerthan16chars"
            self._run_mkfs_with_config(conf, "mkfs.ext4", [], strict=True)

        conf = self._get_config("swap")
        expected_flags = ["--force", ["--label", "abcdefghijklmno"],
                          ["--uuid", conf['uuid']]]
        conf['label'] = "abcdefghijklmnop"  # 16 chars, 15 is max

        # Raise error, do not truncate with strict = True
        with self.assertRaises(ValueError):
            self._run_mkfs_with_config(conf, "mkswap", expected_flags,
                                       strict=True)

        # Do not raise with strict = False
        self._run_mkfs_with_config(conf, "mkswap", expected_flags)

    @mock.patch("curtin.block.mkfs.block")
    @mock.patch("curtin.block.mkfs.util")
    @mock.patch("curtin.block.mkfs.os")
    def test_mkfs_kwargs(self, mock_os, mock_util, mock_block):
        """Ensure that kwargs are being followed"""
        mkfs.mkfs("/dev/null", "ext4", [], uuid=self.test_uuid,
                  label="testlabel", force=True)
        expected_flags = ["-F", ["-L", "testlabel"], ["-U", self.test_uuid]]
        calls = mock_util.subp.call_args_list
        self.assertEquals(len(calls), 1)
        call = calls[0][0][0]
        self.assertEquals(call[0], "mkfs.ext4")
        self._assert_same_flags(call, expected_flags)

    @mock.patch("curtin.block.mkfs.os")
    def test_mkfs_invalid_block_device(self, mock_os):
        """Do not proceed if block device is none or is not valid block dev"""
        with self.assertRaises(ValueError):
            mock_os.path.exists.return_value = False
            mkfs.mkfs("/dev/null", "ext4")
        with self.assertRaises(ValueError):
            mock_os.path.exists.return_value = True
            mkfs.mkfs(None, "ext4")

    @mock.patch("curtin.block.mkfs.util")
    @mock.patch("curtin.block.mkfs.os")
    def test_mkfs_generates_uuid(self, mock_os, mock_util):
        """Ensure that block.mkfs generates and returns a uuid if None is
           provided"""
        uuid = mkfs.mkfs("/dev/null", "ext4")
        self.assertIsNotNone(uuid)
