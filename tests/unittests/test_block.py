# This file is part of curtin. See LICENSE file for copyright and license info.

import functools
import json
import os
import mock
import sys
import textwrap

from collections import OrderedDict

from .helpers import CiTestCase, simple_mocked_open
from curtin import util
from curtin import block


class TestBlock(CiTestCase):

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

    @mock.patch("curtin.block.multipath")
    @mock.patch("curtin.block.os.path.realpath")
    @mock.patch("curtin.block.os.path.exists")
    @mock.patch("curtin.block.os.listdir")
    def test_lookup_disk(self, mock_os_listdir, mock_os_path_exists,
                         mock_os_path_realpath, mock_mpath):
        serial = "SERIAL123"
        mock_os_listdir.return_value = ["sda_%s-part1" % serial,
                                        "sda_%s" % serial, "other"]
        mock_os_path_exists.return_value = True
        mock_os_path_realpath.return_value = "/dev/sda"
        mock_mpath.is_mpath_device.return_value = False
        mock_mpath.is_mpath_member.return_value = False

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

    @mock.patch("curtin.block.multipath")
    @mock.patch("curtin.block.os.path.realpath")
    @mock.patch("curtin.block.os.path.exists")
    @mock.patch("curtin.block.os.listdir")
    def test_lookup_disk_find_wwn(self, mock_os_listdir, mock_os_path_exists,
                                  mock_os_path_realpath, mock_mpath):
        wwn = "eui.0025388b710116a1"
        expected_link = 'nvme-%s' % wwn
        device = '/wark/nvme0n1'
        mock_os_listdir.return_value = [
            "nvme-eui.0025388b710116a1",
            "nvme-eui.0025388b710116a1-part1",
            "nvme-eui.0025388b710116a1-part2",
        ]
        mock_os_path_exists.return_value = True
        mock_os_path_realpath.return_value = device
        mock_mpath.is_mpath_device.return_value = False
        mock_mpath.is_mpath_member.return_value = False

        path = block.lookup_disk(wwn)

        mock_os_listdir.assert_called_with("/dev/disk/by-id/")
        mock_os_path_realpath.assert_called_with("/dev/disk/by-id/" +
                                                 expected_link)
        self.assertTrue(mock_os_path_exists.called)
        self.assertEqual(device, path)

    @mock.patch('curtin.block.udevadm_info')
    def test_get_device_mapper_links_returns_first_non_none(self, m_info):
        """ get_device_mapper_links returns first by sort entry in DEVLINKS."""
        devlinks = [self.random_string(), self.random_string()]
        m_info.return_value = {'DEVLINKS': devlinks}
        devpath = self.random_string()
        self.assertEqual(sorted(devlinks)[0],
                         block.get_device_mapper_links(devpath, first=True))

    @mock.patch('curtin.block.udevadm_info')
    def test_get_device_mapper_links_raises_valueerror_no_links(self, m_info):
        """ get_device_mapper_links raises ValueError if info has no links."""
        m_info.return_value = {self.random_string(): self.random_string()}
        with self.assertRaises(ValueError):
            block.get_device_mapper_links(self.random_string())

    @mock.patch('curtin.block.udevadm_info')
    def test_get_device_mapper_links_raises_error_no_link_vals(self, m_info):
        """ get_device_mapper_links raises ValueError if all links are none"""
        devlinks = ['', '']
        m_info.return_value = {'DEVLINKS': devlinks}
        with self.assertRaises(ValueError):
            block.get_device_mapper_links(self.random_string())

    @mock.patch("curtin.block.get_dev_disk_byid")
    def test_disk_to_byid_path(self, mock_byid):
        """ disk_to_byid path returns a /dev/disk/by-id path """
        mapping = {
            '/dev/sda': '/dev/disk/by-id/scsi-abcdef',
        }
        mock_byid.return_value = mapping

        byid_path = block.disk_to_byid_path('/dev/sda')
        self.assertEqual(mapping['/dev/sda'], byid_path)

    @mock.patch("curtin.block.get_dev_disk_byid")
    def test_disk_to_byid_path_notfound(self, mock_byid):
        """ disk_to_byid path returns None for not found devices """
        mapping = {
            '/dev/sda': '/dev/disk/by-id/scsi-abcdef',
        }
        mock_byid.return_value = mapping

        byid_path = block.disk_to_byid_path('/dev/sdb')
        self.assertEqual(mapping.get('/dev/sdb'), byid_path)


class TestSysBlockPath(CiTestCase):
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


class TestWipeFile(CiTestCase):
    def __init__(self, *args, **kwargs):
        super(TestWipeFile, self).__init__(*args, **kwargs)

    def test_non_exist_raises_file_not_found(self):
        try:
            p = self.tmp_path("enofile")
            block.wipe_file(p)
            raise Exception("%s did not raise exception" % p)
        except Exception as e:
            if not util.is_file_not_found_exc(e):
                raise Exception("exc was not file_not_found: %s" % e)

    def test_non_exist_dir_raises_file_not_found(self):
        try:
            p = self.tmp_path(os.path.sep.join(["enodir", "file"]))
            block.wipe_file(p)
            raise Exception("%s did not raise exception" % p)
        except Exception as e:
            if not util.is_file_not_found_exc(e):
                raise Exception("exc was not file_not_found: %s" % e)

    def test_default_is_zero(self):
        flen = 1024
        myfile = self.tmp_path("def_zero")
        util.write_file(myfile, flen * b'\1', omode="wb")
        block.wipe_file(myfile)
        found = util.load_file(myfile, decode=False)
        self.assertEqual(found, flen * b'\0')

    def test_reader_used(self):
        flen = 17

        def reader(size):
            return size * b'\1'

        myfile = self.tmp_path("reader_used")
        # populate with nulls
        util.write_file(myfile, flen * b'\0', omode="wb")
        block.wipe_file(myfile, reader=reader, buflen=flen)
        found = util.load_file(myfile, decode=False)
        self.assertEqual(found, flen * b'\1')

    def test_reader_twice(self):
        flen = 37
        data = {'x': 20 * b'a' + 20 * b'b'}
        expected = data['x'][0:flen]

        def reader(size):
            buf = data['x'][0:size]
            data['x'] = data['x'][size:]
            return buf

        myfile = self.tmp_path("reader_twice")
        util.write_file(myfile, flen * b'\xff', omode="wb")
        block.wipe_file(myfile, reader=reader, buflen=20)
        found = util.load_file(myfile, decode=False)
        self.assertEqual(found, expected)

    def test_reader_fhandle(self):
        srcfile = self.tmp_path("fhandle_src")
        trgfile = self.tmp_path("fhandle_trg")
        data = '\n'.join(["this is source file." for f in range(0, 10)] + [])
        util.write_file(srcfile, data)
        util.write_file(trgfile, 'a' * len(data))
        with open(srcfile, "rb") as fp:
            block.wipe_file(trgfile, reader=fp.read)
        found = util.load_file(trgfile)
        self.assertEqual(data, found)

    def test_exclusive_open_raise_missing(self):
        myfile = self.tmp_path("no-such-file")

        with self.assertRaises(ValueError):
            with block.exclusive_open(myfile) as fp:
                fp.close()

    @mock.patch('os.close')
    @mock.patch('os.fdopen')
    @mock.patch('os.open')
    def test_exclusive_open(self, mock_os_open, mock_os_fdopen, mock_os_close):
        flen = 1024
        myfile = self.tmp_path("my_exclusive_file")
        util.write_file(myfile, flen * b'\1', omode="wb")
        mock_fd = 3
        mock_os_open.return_value = mock_fd

        with block.exclusive_open(myfile) as fp:
            fp.close()

        mock_os_open.assert_called_with(myfile, os.O_RDWR | os.O_EXCL)
        mock_os_fdopen.assert_called_with(mock_fd, 'rb+')
        self.assertEqual([], mock_os_close.call_args_list)

    @mock.patch('curtin.util.fuser_mount')
    @mock.patch('os.close')
    @mock.patch('curtin.util.list_device_mounts')
    @mock.patch('curtin.block.get_holders')
    @mock.patch('os.open')
    def test_exclusive_open_non_exclusive_exception(self, mock_os_open,
                                                    mock_holders,
                                                    mock_list_mounts,
                                                    mock_os_close,
                                                    mock_util_fuser):
        flen = 1024
        myfile = self.tmp_path("my_exclusive_file")
        util.write_file(myfile, flen * b'\1', omode="wb")
        mock_os_open.side_effect = OSError("NO_O_EXCL")
        mock_holders.return_value = ['md1']
        mock_list_mounts.return_value = []
        mock_util_fuser.return_value = {}

        with self.assertRaises(OSError):
            with block.exclusive_open(myfile) as fp:
                fp.close()

        mock_os_open.assert_called_with(myfile, os.O_RDWR | os.O_EXCL)
        mock_holders.assert_called_with(myfile)
        mock_list_mounts.assert_called_with(myfile)
        self.assertEqual([], mock_os_close.call_args_list)

    @mock.patch('os.close')
    @mock.patch('os.fdopen')
    @mock.patch('os.open')
    def test_exclusive_open_fdopen_failure(self, mock_os_open,
                                           mock_os_fdopen, mock_os_close):
        flen = 1024
        myfile = self.tmp_path("my_exclusive_file")
        util.write_file(myfile, flen * b'\1', omode="wb")
        mock_fd = 3
        mock_os_open.return_value = mock_fd
        mock_os_fdopen.side_effect = OSError("EBADF")

        with self.assertRaises(OSError):
            with block.exclusive_open(myfile) as fp:
                fp.close()

        mock_os_open.assert_called_with(myfile, os.O_RDWR | os.O_EXCL)
        mock_os_fdopen.assert_called_with(mock_fd, 'rb+')
        if sys.version_info.major == 2:
            mock_os_close.assert_called_with(mock_fd)
        else:
            self.assertEqual([], mock_os_close.call_args_list)


class TestWipeVolume(CiTestCase):
    dev = '/dev/null'

    @mock.patch('curtin.block.lvm')
    @mock.patch('curtin.block.util')
    def test_wipe_pvremove(self, mock_util, mock_lvm):
        block.wipe_volume(self.dev, mode='pvremove')
        mock_util.subp.assert_called_with(
            ['pvremove', '--force', '--force', '--yes', self.dev], rcs=[0, 5],
            capture=True)
        self.assertTrue(mock_lvm.lvm_scan.called)

    @mock.patch('curtin.block.quick_zero')
    def test_wipe_superblock(self, mock_quick_zero):
        block.wipe_volume(self.dev, mode='superblock')
        mock_quick_zero.assert_called_with(self.dev, exclusive=True,
                                           partitions=False, strict=False)
        block.wipe_volume(self.dev, exclusive=True,
                          mode='superblock-recursive')
        mock_quick_zero.assert_called_with(self.dev, exclusive=True,
                                           partitions=True, strict=False)

    @mock.patch('curtin.block.wipe_file')
    def test_wipe_zero(self, mock_wipe_file):
        with simple_mocked_open():
            block.wipe_volume(self.dev, exclusive=True, mode='zero')
            mock_wipe_file.assert_called_with(self.dev, exclusive=True)

    @mock.patch('curtin.block.wipe_file')
    def test_wipe_random(self, mock_wipe_file):
        with simple_mocked_open() as mock_open:
            block.wipe_volume(self.dev, mode='random')
            mock_open.assert_called_with('/dev/urandom', 'rb')
            mock_wipe_file.assert_called_with(
                self.dev, exclusive=True,
                reader=mock_open.return_value.__enter__().read)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            block.wipe_volume(self.dev, mode='invalidmode')


class TestBlockKnames(CiTestCase):
    """Tests for some of the kname functions in block"""

    @mock.patch('curtin.block.os.path.realpath')
    @mock.patch('curtin.block.get_device_mapper_links')
    def test_determine_partition_kname(self, m_mlink, m_realp):
        dm0_link = '/dev/disk/by-id/dm-name-XXXX2406'
        m_mlink.return_value = dm0_link

        # we need to convert the -part path to the real dm value
        def _my_realp(pp):
            if pp.startswith(dm0_link):
                return 'dm-1'
            return pp
        m_realp.side_effect = _my_realp
        part_knames = [(('sda', 1), 'sda1'),
                       (('vda', 1), 'vda1'),
                       (('nvme0n1', 1), 'nvme0n1p1'),
                       (('mmcblk0', 1), 'mmcblk0p1'),
                       (('cciss!c0d0', 1), 'cciss!c0d0p1'),
                       (('dm-0', 1),  'dm-1'),
                       (('md0', 1), 'md0p1'),
                       (('mpath1', 2), 'mpath1p2')]
        for ((disk_kname, part_number), part_kname) in part_knames:
            self.assertEqual(part_kname,
                             block.partition_kname(disk_kname, part_number))

    @mock.patch('curtin.block.os.path.realpath')
    def test_path_to_kname(self, mock_os_realpath):
        mock_os_realpath.side_effect = lambda x: os.path.normpath(x)
        path_knames = [('/dev/sda', 'sda'),
                       ('/dev/sda1', 'sda1'),
                       ('/dev////dm-0/', 'dm-0'),
                       ('/dev/md0p1', 'md0p1'),
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


class TestPartTableSignature(CiTestCase):
    blockdev = '/dev/null'
    dos_content = b'\x00' * 0x1fe + b'\x55\xAA' + b'\x00' * 0xf00
    gpt_content = b'\x00' * 0x200 + b'EFI PART' + b'\x00' * (0x200 - 8)
    gpt_content_4k = b'\x00' * 0x800 + b'EFI PART' + b'\x00' * (0x800 - 8)
    null_content = b'\x00' * 0xf00

    def setUp(self):
        super(TestPartTableSignature, self).setUp()
        self.add_patch('curtin.util.subp', 'm_subp')
        self.m_subp.side_effect = iter([
            util.ProcessExecutionError(stdout="", stderr="", exit_code=1)])

    def _test_util_load_file(self, content, device, read_len, offset, decode):
        return (bytes if not decode else str)(content[offset:offset+read_len])

    @mock.patch('curtin.block.check_dos_signature')
    @mock.patch('curtin.block.check_efi_signature')
    def test_gpt_part_table_type(self, mock_check_efi, mock_check_dos):
        """test block.get_part_table_type logic"""
        for (has_dos, has_efi, expected) in [(True, True, 'gpt'),
                                             (True, False, 'dos'),
                                             (False, False, None)]:
            mock_check_dos.return_value = has_dos
            mock_check_efi.return_value = has_efi
            self.assertEqual(
                block.get_part_table_type(self.blockdev), expected)

    @mock.patch('curtin.block.is_block_device')
    @mock.patch('curtin.block.util')
    def test_check_dos_signature(self, mock_util, mock_is_block_device):
        """test block.check_dos_signature"""
        for (is_block, f_size, contents, expected) in [
                (True, 0x200, self.dos_content, True),
                (False, 0x200, self.dos_content, False),
                (True, 0, self.dos_content, False),
                (True, 0x400, self.dos_content, True),
                (True, 0x200, self.null_content, False)]:
            mock_util.load_file.side_effect = (
                functools.partial(self._test_util_load_file, contents))
            mock_util.file_size.return_value = f_size
            mock_is_block_device.return_value = is_block
            (self.assertTrue if expected else self.assertFalse)(
                block.check_dos_signature(self.blockdev))

    @mock.patch('curtin.block.is_block_device')
    @mock.patch('curtin.block.get_blockdev_sector_size')
    @mock.patch('curtin.block.util')
    def test_check_efi_signature(self, mock_util, mock_get_sector_size,
                                 mock_is_block_device):
        """test block.check_efi_signature"""
        for (sector_size, gpt_dat) in zip(
                (0x200, 0x800), (self.gpt_content, self.gpt_content_4k)):
            mock_get_sector_size.return_value = (sector_size, sector_size)
            for (is_block, f_size, contents, expected) in [
                    (True, 2 * sector_size, gpt_dat, True),
                    (True, 1 * sector_size, gpt_dat, False),
                    (False, 2 * sector_size, gpt_dat, False),
                    (True, 0, gpt_dat, False),
                    (True, 2 * sector_size, self.dos_content, False),
                    (True, 2 * sector_size, self.null_content, False)]:
                mock_util.load_file.side_effect = (
                    functools.partial(self._test_util_load_file, contents))
                mock_util.file_size.return_value = f_size
                mock_is_block_device.return_value = is_block
                (self.assertTrue if expected else self.assertFalse)(
                    block.check_efi_signature(self.blockdev))

    def test_check_vtoc_signature_finds_vtoc_returns_true(self):
        self.m_subp.side_effect = iter([("vtoc.....ok", "")])
        self.assertTrue(block.check_vtoc_signature(self.blockdev))

    def test_check_vtoc_signature_returns_false_with_no_sig(self):
        self.m_subp.side_effect = iter([
            util.ProcessExecutionError(stdout="", stderr="", exit_code=1)])
        self.assertFalse(block.check_vtoc_signature(self.blockdev))


class TestNonAscii(CiTestCase):
    @mock.patch('curtin.block.util.subp')
    def test_lsblk(self, mock_subp):
        # lsblk can write non-ascii data, causing shlex to blow up
        out = (b'ALIGNMENT="0" DISC-ALN="0" DISC-GRAN="512" '
               b'DISC-MAX="2147450880" DISC-ZERO="0" FSTYPE="" '
               b'GROUP="root" KNAME="sda" LABEL="" LOG-SEC="512" '
               b'MAJ:MIN="8:0" MIN-IO="512" MODE="\xc3\xb8---------" '
               b'MODEL="Samsung SSD 850 " MOUNTPOINT="" NAME="sda" '
               b'OPT-IO="0" OWNER="root" PHY-SEC="512" RM="0" RO="0" '
               b'ROTA="0" RQ-SIZE="128" SIZE="500107862016" '
               b'STATE="running" TYPE="disk" UUID=""').decode('utf-8')
        err = b''.decode()
        mock_subp.return_value = (out, err)
        out = block._lsblock()

    @mock.patch('curtin.block.util.subp')
    def test_blkid(self, mock_subp):
        # we use shlex on blkid, so cover that it might output non-ascii
        out = (b'/dev/sda2: UUID="19ac97d5-6973-4193-9a09-2e6bbfa38262" '
               b'LABEL="\xc3\xb8foo" TYPE="ext4"').decode('utf-8')
        err = b''.decode()
        mock_subp.return_value = (out, err)
        block.blkid()


class TestSlaveKnames(CiTestCase):

    def setUp(self):
        super(TestSlaveKnames, self).setUp()
        self.add_patch('curtin.block.get_blockdev_for_partition',
                       'm_blockdev_for_partition')
        self.add_patch('curtin.block.os.path.exists',
                       'm_os_path_exists')
        # trusty-p3 does not like autospec=True for os.listdir
        self.add_patch('curtin.block.os.listdir',
                       'm_os_listdir', autospec=False)

    def _prepare_mocks(self, device, cfg):
        """
        Construct the correct sequence of mocks
        give a mapping of device and slaves

        cfg = {
            'wark': ['foo', 'bar'],
            'foo': [],
            'bar': [],
        }
        device = 'wark', slaves = ['foo, 'bar']

        cfg = {
            'wark': ['foo', 'bar'],
            'foo': ['zip'],
            'bar': [],
            'zip': []
        }
        device = 'wark', slaves = ['zip', 'bar']
        """
        # kname side-effect mapping
        parts = [(k, None) for k in cfg.keys()]
        self.m_blockdev_for_partition.side_effect = iter(parts)

        # construct side effects to os.path.exists
        # and os.listdir based on mapping.
        dirs = []
        exists = [True] if device.startswith('/dev') else []
        for (dev, slvs) in cfg.items():
            # sys_block_dev checks if dev exists
            exists.append(True)
            if slvs:
                # os.path.exists on slaves dir
                exists.append(True)
                # result of os.listdir
                dirs.append(slvs)
            else:
                # os.path.exists on slaves dir
                exists.append(False)

        self.m_os_path_exists.side_effect = iter(exists)
        self.m_os_listdir.side_effect = iter(dirs)

    def test_get_device_slave_knames(self):
        #
        # /sys/class/block/wark/slaves/foo -> ../../foo
        # /sys/class/block/foo #
        # should return 'bar'
        cfg = OrderedDict([
            ('wark', ['foo']),
            ('foo', []),
        ])
        device = "/dev/wark"
        slaves = ["foo"]
        self._prepare_mocks(device, cfg)
        knames = block.get_device_slave_knames(device)
        self.assertEqual(slaves, knames)

    def test_get_device_slave_knames_stacked(self):
        #
        # /sys/class/block/wark/slaves/foo -> ../../foo
        # /sys/class/block/wark/slaves/bar -> ../../bar
        # /sys/class/block/foo
        # /sys/class/block/bar
        #
        # should return ['foo', 'bar']
        cfg = OrderedDict([
            ('wark', ['foo', 'bar']),
            ('foo', []),
            ('bar', []),
        ])
        device = 'wark'
        slaves = ['foo', 'bar']
        self._prepare_mocks(device, cfg)
        knames = block.get_device_slave_knames(device)
        self.assertEqual(slaves, knames)

    def test_get_device_slave_knames_double_stacked(self):
        # /sys/class/block/wark/slaves/foo -> ../../foo
        # /sys/class/block/wark/slaves/bar -> ../../bar
        # /sys/class/block/foo
        # /sys/class/block/bar/slaves/zip -> ../../zip
        # /sys/class/block/zip
        #
        # mapping of device:
        cfg = OrderedDict([
            ('wark', ['foo', 'bar']),
            ('foo', []),
            ('bar', ['zip']),
            ('zip', []),
        ])
        device = 'wark'
        slaves = ['foo', 'zip']
        self._prepare_mocks(device, cfg)
        knames = block.get_device_slave_knames(device)
        self.assertEqual(slaves, knames)


class TestGetSupportedFilesystems(CiTestCase):

    supported_filesystems = ['sysfs', 'rootfs', 'ramfs', 'ext4']

    def _proc_filesystems_output(self, supported=None):
        if not supported:
            supported = self.supported_filesystems

        def devname(fsname):
            """ in-use filesystem modules not emit the 'nodev' prefix """
            return '\t' if fsname.startswith('ext') else 'nodev\t'

        return '\n'.join([devname(fs) + fs for fs in supported]) + '\n'

    @mock.patch('curtin.block.util')
    @mock.patch('curtin.block.os')
    def test_get_supported_filesystems(self, mock_os, mock_util):
        """ test parsing /proc/filesystems contents into a filesystem list"""
        mock_os.path.exists.return_value = True
        mock_util.load_file.return_value = self._proc_filesystems_output()

        result = block.get_supported_filesystems()
        self.assertEqual(sorted(self.supported_filesystems), sorted(result))

    @mock.patch('curtin.block.util')
    @mock.patch('curtin.block.os')
    def test_get_supported_filesystems_no_proc_path(self, mock_os, mock_util):
        """ missing /proc/filesystems raises RuntimeError """
        mock_os.path.exists.return_value = False
        with self.assertRaises(RuntimeError):
            block.get_supported_filesystems()
        self.assertEqual(0, mock_util.load_file.call_count)


class TestZkeySupported(CiTestCase):

    @mock.patch('curtin.block.util')
    def test_zkey_supported_loads_module(self, m_util):
        block.zkey_supported()
        m_util.load_kernel_module.assert_called_with('pkey')

    @mock.patch('curtin.block.util.load_kernel_module')
    def test_zkey_supported_returns_false_missing_kmod(self, m_kmod):
        m_kmod.side_effect = (
            util.ProcessExecutionError(stdout=self.random_string(),
                                       stderr=self.random_string(),
                                       exit_code=2))
        self.assertFalse(block.zkey_supported())

    @mock.patch('curtin.block.util.subp')
    @mock.patch('curtin.block.util.load_kernel_module')
    def test_zkey_supported_returns_false_zkey_error(self, m_kmod, m_subp):
        m_subp.side_effect = (
            util.ProcessExecutionError(stdout=self.random_string(),
                                       stderr=self.random_string(),
                                       exit_code=2))
        self.assertFalse(block.zkey_supported())

    @mock.patch('curtin.block.tempfile.NamedTemporaryFile')
    @mock.patch('curtin.block.util')
    def test_zkey_supported_calls_zkey_generate(self, m_util, m_temp):
        testname = self.random_string()
        m_temp.return_value.__enter__.return_value.name = testname
        block.zkey_supported()
        m_util.subp.assert_called_with(['zkey', 'generate', testname],
                                       capture=True)


class TestSfdiskInfo(CiTestCase):

    VALID_SFDISK_OUTPUT = textwrap.dedent("""\
    {
       "partitiontable": {
          "label":"dos",
          "id":"0xb0dbdde1",
          "device":"/dev/vdb",
          "unit":"sectors",
          "partitions": [
             {"node":"/dev/vdb1", "start":2048, "size":8388608,
              "type":"83", "bootable":true},
             {"node":"/dev/vdb2", "start":8390656, "size":8388608,
              "type":"83"},
             {"node":"/dev/vdb3", "start":16779264, "size":62914560,
              "type":"85"},
             {"node":"/dev/vdb5", "start":16781312, "size":31457280,
              "type":"83"},
             {"node":"/dev/vdb6", "start":48240640, "size":10485760,
              "type":"83"},
             {"node":"/dev/vdb7", "start":58728448, "size":20965376,
              "type":"83"}
          ]
       }
    }""")

    def setUp(self):
        super(TestSfdiskInfo, self).setUp()
        self.add_patch('curtin.block.get_blockdev_for_partition',
                       'm_get_blockdev_for_partition')
        self.add_patch('curtin.block.util.subp', 'm_subp')
        self.add_patch('curtin.block.util.load_json', 'm_load_json')
        self.device = '/dev/vdb3'
        self.disk = '/dev/vdb'
        self.part = '3'
        self.m_get_blockdev_for_partition.return_value = (self.disk, self.part)
        self.m_subp.return_value = (self.VALID_SFDISK_OUTPUT, "")
        self.loaded_json = json.loads(self.VALID_SFDISK_OUTPUT)
        self.m_load_json.return_value = self.loaded_json
        self.expected = self.loaded_json.get('partitiontable', {})

    def test_sfdisk_info(self):
        """verify sfdisk_info returns correct info dictionary for device."""
        self.assertEqual(self.expected, block.sfdisk_info(self.device))
        self.assertEqual(
            [mock.call(self.device)],
            self.m_get_blockdev_for_partition.call_args_list)
        self.assertEqual(
            [mock.call(['sfdisk', '--json', self.disk], capture=True)],
            self.m_subp.call_args_list)
        self.assertEqual(
            [mock.call(self.m_subp.return_value[0])],
            self.m_load_json.call_args_list)

    def test_sfdisk_info_returns_empty_on_subp_error(self):
        """verify sfdisk_info returns empty dict on subp errors."""
        self.m_subp.side_effect = (
            util.ProcessExecutionError(
                stdout="",
                stderr="sfdisk: cannot open /dev/vdb: Permission denied",
                exit_code=1))
        self.assertEqual({}, block.sfdisk_info(self.device))
        self.assertEqual(
            [mock.call(self.device)],
            self.m_get_blockdev_for_partition.call_args_list)
        self.assertEqual(
            [mock.call(['sfdisk', '--json', self.disk], capture=True)],
            self.m_subp.call_args_list)
        self.assertEqual([], self.m_load_json.call_args_list)


# vi: ts=4 expandtab syntax=python
