from unittest import TestCase
import mock
from curtin import block


class TestBlock(TestCase):

    @mock.patch("curtin.block.util")
    def test_get_volume_uuid(self, mock_util):
        path = "/dev/sda1"
        expected_call = ["blkid", "-o", "export", path]
        mock_util.subp.return_value = ("""
            UUID=182e8e23-5322-46c9-a1b8-cf2c6a88f9f7
            """, "")

        uuid = block.get_volume_uuid(path)

        mock_util.subp.assert_called_with(expected_call, capture=True)
        self.assertEqual(uuid, "182e8e23-5322-46c9-a1b8-cf2c6a88f9f7")

    @mock.patch("curtin.block.get_proc_mounts")
    @mock.patch("curtin.block._lsblock")
    def test_get_mountpoints(self, mock_lsblk, mock_proc_mounts):
        mock_lsblk.return_value = {"sda1": {"MOUNTPOINT": None},
                                   "sda2": {"MOUNTPOINT": ""},
                                   "sda3": {"MOUNTPOINT": "/mnt"}}
        mock_proc_mounts.return_value = [
            ('sysfs', '/sys', 'sysfs', 'sysfs_opts', '0', '0'),
        ]

        mountpoints = block.get_mountpoints()

        self.assertTrue(mock_lsblk.called)
        self.assertEqual(sorted(mountpoints),
                         sorted(["/mnt", "/sys"]))

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

        path = block.lookup_disk(serial)

        mock_os_listdir.assert_called_with("/dev/disk/by-id/")
        mock_os_path_realpath.assert_called_with("/dev/disk/by-id/sda_%s" %
                                                 serial)
        self.assertTrue(mock_os_path_exists.called)
        self.assertEqual(path, "/dev/sda")

        with self.assertRaises(ValueError):
            mock_os_path_exists.return_value = False
            block.lookup_disk(serial)

        with self.assertRaises(ValueError):
            mock_os_path_exists.return_value = True
            mock_os_listdir.return_value = ["other"]
            block.lookup_disk(serial)


class TestSysBlockPath(TestCase):
    @mock.patch("os.path.exists")
    def test_existing_valid_devname(self, m_os_path_exists):
        m_os_path_exists.return_value = True
        self.assertEqual('/sys/class/block/foodevice',
                         block.sys_block_path("foodevice"))

    @mock.patch("os.path.exists")
    def test_existing_devpath_allowed(self, m_os_path_exists):
        m_os_path_exists.return_value = True
        self.assertEqual('/sys/class/block/foodev',
                         block.sys_block_path("/dev/foodev"))

    @mock.patch("os.path.exists")
    def test_add_works(self, m_os_path_exists):
        m_os_path_exists.return_value = True
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("/dev/foodev", "md/b"))

    @mock.patch("os.path.exists")
    def test_add_works_leading_slash(self, m_os_path_exists):
        m_os_path_exists.return_value = True
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("/dev/foodev", "/md/b"))

    @mock.patch("os.path.exists")
    def test_invalid_devname_raises(self, m_os_path_exists):
        m_os_path_exists.return_value = False
        with self.assertRaises(OSError):
            block.sys_block_path("foodevice")

    def test_invalid_with_add(self):
        # test the device exists, but 'add' does not
        # path_exists returns true unless 'md/device' is in it
        #  so /sys/class/foodev/ exists, but not /sys/class/foodev/md/device
        add = "md/device"

        def path_exists(path):
            return add not in path

        with mock.patch('os.path.exists', side_effect=path_exists):
            self.assertRaises(OSError, block.sys_block_path, "foodev", add)

    @mock.patch("os.path.exists")
    def test_not_strict_does_not_care(self, m_os_path_exists):
        m_os_path_exists.return_value = False
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("foodev", "/md/b", strict=False))


# vi: ts=4 expandtab syntax=python
