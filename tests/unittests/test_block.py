from unittest import TestCase
import os
import mock
import tempfile
import shutil

from collections import OrderedDict

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

    @mock.patch('curtin.block._lsblock')
    def test_get_blockdev_sector_size(self, mock_lsblk):
        mock_lsblk.return_value = {
            'sda':  {'LOG-SEC': '512', 'PHY-SEC': '4096',
                     'device_path': '/dev/sda'},
            'sda1': {'LOG-SEC': '512', 'PHY-SEC': '4096',
                     'device_path': '/dev/sda1'},
            'dm-0': {'LOG-SEC': '512', 'PHY-SEC': '512',
                     'device_path': '/dev/dm-0'},
        }
        for (devpath, expected) in [('/dev/sda', (512, 4096)),
                                    ('/dev/sda1', (512, 4096)),
                                    ('/dev/dm-0', (512, 512))]:
            res = block.get_blockdev_sector_size(devpath)
            mock_lsblk.assert_called_with([devpath])
            self.assertEqual(res, expected)

        # test that fallback works and gives right return
        mock_lsblk.return_value = OrderedDict()
        mock_lsblk.return_value.update({
            'vda': {'LOG-SEC': '4096', 'PHY-SEC': '4096',
                    'device_path': '/dev/vda'},
        })
        mock_lsblk.return_value.update({
            'vda1': {'LOG-SEC': '512', 'PHY-SEC': '512',
                     'device_path': '/dev/vda1'},
        })
        res = block.get_blockdev_sector_size('/dev/vda2')
        self.assertEqual(res, (4096, 4096))

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

    @mock.patch('curtin.block.get_blockdev_for_partition')
    @mock.patch('os.path.exists')
    def test_cciss_sysfs_path(self, m_os_path_exists, m_get_blk):
        m_os_path_exists.return_value = True
        m_get_blk.return_value = ('cciss!c0d0', None)
        self.assertEqual('/sys/class/block/cciss!c0d0',
                         block.sys_block_path('/dev/cciss/c0d0'))
        m_get_blk.return_value = ('cciss!c0d0', 1)
        self.assertEqual('/sys/class/block/cciss!c0d0/cciss!c0d0p1',
                         block.sys_block_path('/dev/cciss/c0d0p1'))


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


class TestBlockKnames(TestCase):
    """Tests for some of the kname functions in block"""
    def test_determine_partition_kname(self):
        part_knames = [(('sda', 1), 'sda1'),
                       (('vda', 1), 'vda1'),
                       (('nvme0n1', 1), 'nvme0n1p1'),
                       (('mmcblk0', 1), 'mmcblk0p1'),
                       (('cciss!c0d0', 1), 'cciss!c0d0p1'),
                       (('dm-0', 1), 'dm-0p1'),
                       (('mpath1', 2), 'mpath1p2')]
        for ((disk_kname, part_number), part_kname) in part_knames:
            self.assertEqual(block.partition_kname(disk_kname, part_number),
                             part_kname)

    @mock.patch('curtin.block.os.path.realpath')
    def test_path_to_kname(self, mock_os_realpath):
        mock_os_realpath.side_effect = lambda x: os.path.normpath(x)
        path_knames = [('/dev/sda', 'sda'),
                       ('/dev/sda1', 'sda1'),
                       ('/dev////dm-0/', 'dm-0'),
                       ('vdb', 'vdb'),
                       ('/dev/mmcblk0p1', 'mmcblk0p1'),
                       ('/dev/nvme0n0p1', 'nvme0n0p1'),
                       ('/sys/block/vdb', 'vdb'),
                       ('/sys/block/vdb/vdb2/', 'vdb2'),
                       ('/dev/cciss/c0d0', 'cciss!c0d0'),
                       ('/dev/cciss/c0d0p1/', 'cciss!c0d0p1'),
                       ('/sys/class/block/cciss!c0d0p1', 'cciss!c0d0p1'),
                       ('nvme0n1p4', 'nvme0n1p4')]
        for (path, expected_kname) in path_knames:
            self.assertEqual(block.path_to_kname(path), expected_kname)
            if os.path.sep in path:
                mock_os_realpath.assert_called_with(path)

    @mock.patch('curtin.block.os.path.exists')
    @mock.patch('curtin.block.os.path.realpath')
    @mock.patch('curtin.block.is_valid_device')
    def test_kname_to_path(self, mock_is_valid_device, mock_os_realpath,
                           mock_exists):
        kname_paths = [('sda', '/dev/sda'),
                       ('sda1', '/dev/sda1'),
                       ('/dev/sda', '/dev/sda'),
                       ('cciss!c0d0p1', '/dev/cciss/c0d0p1'),
                       ('/dev/cciss/c0d0', '/dev/cciss/c0d0'),
                       ('mmcblk0p1', '/dev/mmcblk0p1')]

        mock_exists.return_value = True
        mock_os_realpath.side_effect = lambda x: x.replace('!', '/')
        # first call to is_valid_device needs to return false for nonpaths
        mock_is_valid_device.side_effect = lambda x: x.startswith('/dev')
        for (kname, expected_path) in kname_paths:
            self.assertEqual(block.kname_to_path(kname), expected_path)
            mock_is_valid_device.assert_called_with(expected_path)

        # test failure
        mock_is_valid_device.return_value = False
        mock_is_valid_device.side_effect = None
        for (kname, expected_path) in kname_paths:
            with self.assertRaises(OSError):
                block.kname_to_path(kname)

# vi: ts=4 expandtab syntax=python
