from unittest import TestCase
import os
import mock
import tempfile
import shutil

from curtin import util
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
    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_existing_valid_devname(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = True
        m_get_blk.return_value = ('foodevice', None)
        self.assertEqual('/sys/class/block/foodevice',
                         block.sys_block_path("foodevice"))

    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_existing_devpath_allowed(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = True
        m_get_blk.return_value = ('foodev', None)
        self.assertEqual('/sys/class/block/foodev',
                         block.sys_block_path("/dev/foodev"))

    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_add_works(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = True
        m_get_blk.return_value = ('foodev', None)
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("/dev/foodev", "md/b"))

    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_add_works_leading_slash(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = True
        m_get_blk.return_value = ('foodev', None)
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("/dev/foodev", "/md/b"))

    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_invalid_devname_raises(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = False
        with self.assertRaises(ValueError):
            block.sys_block_path("foodevice")

    @mock.patch("curtin.block.get_blockdev_for_partition")
    def test_invalid_with_add(self, m_get_blk):
        # test the device exists, but 'add' does not
        # path_exists returns true unless 'md/device' is in it
        #  so /sys/class/foodev/ exists, but not /sys/class/foodev/md/device
        add = "md/device"

        def path_exists(path):
            return add not in path

        m_get_blk.return_value = ("foodev", None)
        with mock.patch('os.path.exists', side_effect=path_exists):
            self.assertRaises(OSError, block.sys_block_path, "foodev", add)

    @mock.patch("curtin.block.get_blockdev_for_partition")
    @mock.patch("os.path.exists")
    def test_not_strict_does_not_care(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = False
        m_get_blk.return_value = ('foodev', None)
        self.assertEqual('/sys/class/block/foodev/md/b',
                         block.sys_block_path("foodev", "/md/b", strict=False))


class TestWipeFile(TestCase):
    def __init__(self, *args, **kwargs):
        super(TestWipeFile, self).__init__(*args, **kwargs)

    def tfile(self, *args):
        # return a temp file in a dir that will be cleaned up
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        return os.path.sep.join([tmpdir] + list(args))

    def test_non_exist_raises_file_not_found(self):
        try:
            p = self.tfile("enofile")
            block.wipe_file(p)
            raise Exception("%s did not raise exception" % p)
        except Exception as e:
            if not util.is_file_not_found_exc(e):
                raise Exception("exc was not file_not_found: %s" % e)

    def test_non_exist_dir_raises_file_not_found(self):
        try:
            p = self.tfile("enodir", "file")
            block.wipe_file(p)
            raise Exception("%s did not raise exception" % p)
        except Exception as e:
            if not util.is_file_not_found_exc(e):
                raise Exception("exc was not file_not_found: %s" % e)

    def test_default_is_zero(self):
        flen = 1024
        myfile = self.tfile("def_zero")
        util.write_file(myfile, flen * b'\1', omode="wb")
        block.wipe_file(myfile)
        found = util.load_file(myfile, mode="rb")
        self.assertEqual(found, flen * b'\0')

    def test_reader_used(self):
        flen = 17

        def reader(size):
            return size * b'\1'

        myfile = self.tfile("reader_used")
        # populate with nulls
        util.write_file(myfile, flen * b'\0', omode="wb")
        block.wipe_file(myfile, reader=reader, buflen=flen)
        found = util.load_file(myfile, mode="rb")
        self.assertEqual(found, flen * b'\1')

    def test_reader_twice(self):
        flen = 37
        data = {'x': 20 * b'a' + 20 * b'b'}
        expected = data['x'][0:flen]

        def reader(size):
            buf = data['x'][0:size]
            data['x'] = data['x'][size:]
            return buf

        myfile = self.tfile("reader_twice")
        util.write_file(myfile, flen * b'\xff', omode="wb")
        block.wipe_file(myfile, reader=reader, buflen=20)
        found = util.load_file(myfile, mode="rb")
        self.assertEqual(found, expected)

    def test_reader_fhandle(self):
        srcfile = self.tfile("fhandle_src")
        trgfile = self.tfile("fhandle_trg")
        data = '\n'.join(["this is source file." for f in range(0, 10)] + [])
        util.write_file(srcfile, data)
        util.write_file(trgfile, 'a' * len(data))
        with open(srcfile, "rb") as fp:
            block.wipe_file(trgfile, reader=fp.read)
        found = util.load_file(trgfile)
        self.assertEqual(data, found)

# vi: ts=4 expandtab syntax=python
