from unittest import TestCase
import mock
import curtin.block


class TestBlock(TestCase):

    @mock.patch("curtin.block.util")
    def test_get_volume_uuid(self, mock_util):
        path = "/dev/sda1"
        expected_call = ["blkid", "-o", "export", path]
        mock_util.subp.return_value = ("""
            UUID=182e8e23-5322-46c9-a1b8-cf2c6a88f9f7
            """, "")

        uuid = curtin.block.get_volume_uuid(path)

        mock_util.subp.assert_called_with(expected_call, capture=True)
        self.assertEqual(uuid, "182e8e23-5322-46c9-a1b8-cf2c6a88f9f7")

    @mock.patch("curtin.block._lsblock")
    def test_get_mountpoints(self, mock_lsblk):
        mock_lsblk.return_value = {"sda1": {"MOUNTPOINT": None},
                                   "sda2": {"MOUNTPOINT": ""},
                                   "sda3": {"MOUNTPOINT": "/mnt"}}

        mountpoints = curtin.block.get_mountpoints()

        self.assertTrue(mock_lsblk.called)
        self.assertEqual(mountpoints, ["/mnt"])

    @mock.patch("curtin.block.os.path.realpath")
    @mock.patch("curtin.block.os.path.exists")
    @mock.patch("curtin.block.os.listdir")
    def test_lookup_disk(self, mock_os_listdir, mock_os_path_exists,
                         mock_os_path_realpath):
        serial = "SERIAL123"
        mock_os_listdir.return_value = ["sda_%s-part1" % serial,
                                        "sda_%s" % serial, "other"]
        mock_os_path_exists.return_value = True
        mock_os_path_realpath.return_value = "/dev/sda"

        path = curtin.block.lookup_disk(serial)

        mock_os_listdir.assert_called_with("/dev/disk/by-id/")
        mock_os_path_realpath.assert_called_with("/dev/disk/by-id/sda_%s" %
                                                 serial)
        self.assertTrue(mock_os_path_exists.called)
        self.assertEqual(path, "/dev/sda")

        with self.assertRaises(ValueError):
            mock_os_path_exists.return_value = False
            curtin.block.lookup_disk(serial)

        with self.assertRaises(ValueError):
            mock_os_path_exists.return_value = True
            mock_os_listdir.return_value = ["other"]
            curtin.block.lookup_disk(serial)

# vi: ts=4 expandtab syntax=python
