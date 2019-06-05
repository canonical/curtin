import mock
import os

from curtin.block import bcache
from curtin.util import (FileMissingError, load_file, ProcessExecutionError)
from .helpers import CiTestCase


class TestBlockBcache(CiTestCase):

    def setUp(self):
        super(TestBlockBcache, self).setUp()
        self.add_patch('curtin.block.bcache.util.subp', 'mock_subp')

    def _datafile(self, name):
        path = 'tests/data'
        return os.path.join(path, name)

    expected = {
        'backing': {
            "cset.uuid": "01da3829-ea92-4600-bd40-7f95974f3087",
            "dev.data.cache_mode": "1 [writeback]",
            "dev.data.cache_state": "2 [dirty]",
            "dev.data.first_sector": "16",
            "dev.label": "(empty)",
            "dev.sectors_per_block": "1",
            "dev.sectors_per_bucket": "1024",
            "dev.uuid": "f36394c0-3cc0-4423-8d6f-ffac130f171a",
            "sb.csum": "B92908820E241EDD [match]",
            "sb.first_sector": "8 [match]",
            "sb.magic": "ok",
            "sb.version": "1 [backing device]"
        },
        'caching': {
            "cset.uuid": "01da3829-ea92-4600-bd40-7f95974f3087",
            "dev.cache.cache_sectors": "234372096",
            "dev.cache.discard": "no",
            "dev.cache.first_sector": "1024",
            "dev.cache.ordered": "yes",
            "dev.cache.pos": "0",
            "dev.cache.replacement": "0 [lru]",
            "dev.cache.total_sectors": "234373120",
            "dev.label": "(empty)",
            "dev.sectors_per_block": "1",
            "dev.sectors_per_bucket": "1024",
            "dev.uuid": "ff51a56d-eddc-41b3-867d-8744277c5281",
            "sb.csum": "2F8BB7E8DC53E0B6 [match]",
            "sb.first_sector": "8 [match]",
            "sb.magic": "ok",
            "sb.version": "3 [cache device]"
        },
    }

    @mock.patch('curtin.block.bcache.util.subp')
    def test_superblock_asdict(self, m_subp):
        """ verify parsing bcache-super-show matches expected results."""
        device = self.random_string()
        results = {}
        prefix = 'bcache-super-show-'
        scenarios = ['backing', 'caching']

        # XXX: Parameterize me
        for superblock in scenarios:
            datafile = prefix + superblock
            contents = load_file(self._datafile(datafile))
            m_subp.return_value = (contents, '')

            results[superblock] = bcache.superblock_asdict(device=device)

        for superblock in scenarios:
            comment = 'mismatch in %s' % superblock
            self.assertDictEqual(
                self.expected[superblock], results[superblock], comment)

    def test_superblock_asdict_no_dev_no_data(self):
        """ superblock_asdict raises ValueError without device or data."""
        with self.assertRaises(ValueError):
            bcache.superblock_asdict()

    @mock.patch('curtin.block.bcache.util.subp')
    def test_superblock_asdict_calls_bcache_super_show(self, m_subp):
        """ superblock_asdict calls bcache-super-show on device."""
        device = self.random_string()
        m_subp.return_value = ('', '')
        bcache.superblock_asdict(device=device)
        m_subp.assert_called_with(['bcache-super-show', device], capture=True)

    @mock.patch('curtin.block.bcache.util.subp')
    def test_superblock_asdict_does_not_call_subp_with_data(self, m_subp):
        """ superblock_asdict does not bcache-super-show with data provided."""
        key = self.random_string()
        value = self.random_string()
        mydata = "\t".join([key, value])
        result = bcache.superblock_asdict(data=mydata)
        self.assertEqual({key: value}, result)
        m_subp.assert_not_called()

    @mock.patch('curtin.block.bcache.util.subp')
    def test_superblock_asdict_returns_none_invalid_superblock(self, m_subp):
        device = self.random_string()
        m_subp.side_effect = ProcessExecutionError(stdout=self.random_string(),
                                                   stderr=self.random_string(),
                                                   exit_code=2)
        self.assertEqual(None, bcache.superblock_asdict(device=device))

    def test_parse_sb_version(self):
        """ parse_sb_version converts sb.version field into integer value. """
        sbdict = {'sb.version': '1 [backing device]'}
        self.assertEqual(1, bcache.parse_sb_version(sbdict=sbdict))

    # XXX: Parameterize me
    def test_parse_sb_version_raises_exceptions_on_garbage_dict(self):
        """ parse_sb_version raises Exceptions on garbage dicts."""
        with self.assertRaises(AttributeError):
            bcache.parse_sb_version(sbdict={self.random_string():
                                            self.random_string()})

    # XXX: Parameterize me
    def test_parse_sb_version_raises_exceptions_on_non_dict(self):
        """ parse_sb_version raises Exceptions on non-dict input."""
        with self.assertRaises(ValueError):
            bcache.parse_sb_version(sbdict=self.random_string())

    @mock.patch('curtin.block.bcache.superblock_asdict')
    def test_is_backing_superblock(self, m_sbdict):
        """ is_backing returns True when given backing superblock dict. """
        bdict = {'sb.version': '1 [backing device]'}
        m_sbdict.return_value = bdict
        self.assertEqual(True, bcache.is_backing(self.random_string(),
                                                 superblock=True))

    @mock.patch('curtin.block.bcache.superblock_asdict')
    def test_is_backing_superblock_invalid(self, m_sbdict):
        """ is_backing returns False when parsing invalid superblock. """
        m_sbdict.return_value = None
        self.assertEqual(False, bcache.is_backing(self.random_string(),
                                                  superblock=True))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_is_backing_sysfs(self, m_sysb_path, m_path_exists):
        """ is_backing returns True if sysfs path has bcache/label. """
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = True
        self.assertEqual(True, bcache.is_backing(kname))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_is_backing_sysfs_false(self, m_sysb_path, m_path_exists):
        """ is_backing returns False if path does not have bcache/label. """
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = False
        self.assertEqual(False, bcache.is_backing(kname))

    @mock.patch('curtin.block.bcache.superblock_asdict')
    def test_is_cacheing_superblock(self, m_sbdict):
        """ is_caching returns True when given caching superblock dict. """
        bdict = {'sb.version': '3 [caching device]'}
        m_sbdict.return_value = bdict
        self.assertEqual(True, bcache.is_caching(self.random_string(),
                                                 superblock=True))

    @mock.patch('curtin.block.bcache.superblock_asdict')
    def test_is_caching_superblock_invalid(self, m_sbdict):
        """ is_caching returns False when parsing invalid superblock. """
        m_sbdict.return_value = None
        self.assertEqual(False, bcache.is_caching(self.random_string(),
                                                  superblock=True))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_is_caching_sysfs(self, m_sysb_path, m_path_exists):
        """ is_caching returns True if sysfs path has bcache/label. """
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = True
        self.assertEqual(True, bcache.is_caching(kname))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_is_caching_sysfs_false(self, m_sysb_path, m_path_exists):
        """ is_caching returns False if path does not have bcache/label. """
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = False
        self.assertEqual(False, bcache.is_caching(kname))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_sysfs_path(self, m_sysb_path, m_path_exists):
        """ sysfs_path returns /sys/class/block/<device>/bcache for device."""
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = True
        self.assertEqual('/sys/class/block/%s/bcache' % kname,
                         bcache.sysfs_path(kname))

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_sysfs_path_raise_strict_nopath(self, m_sysb_path, m_path_exists):
        """ sysfs_path raises OSError on strict=True and missing path. """
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = False
        with self.assertRaises(OSError):
            bcache.sysfs_path(kname)

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sys_block_path')
    def test_sysfs_path_non_strict(self, m_sysb_path, m_path_exists):
        """ sysfs_path returns path if missing and strict=False."""
        kname = self.random_string()
        m_sysb_path.return_value = '/sys/class/block/%s' % kname
        m_path_exists.return_value = False
        self.assertEqual('/sys/class/block/%s/bcache' % kname,
                         bcache.sysfs_path(kname, strict=False))

    @mock.patch('curtin.block.bcache.sysfs_path')
    @mock.patch('curtin.block.bcache.util.write_file')
    def test_write_label(self, m_write_file, m_sysfs_path):
        """ write_label writes label to device/bcache/label attribute."""
        label = self.random_string()
        kname = self.random_string()
        bdir = '/sys/class/block/%s/bcache' % kname
        label_path = bdir + '/label'
        m_sysfs_path.return_value = bdir
        bcache.write_label(label, kname)
        m_write_file.assert_called_with(label_path, content=label, mode=None)

    @mock.patch('curtin.block.bcache.os.path.realpath')
    @mock.patch('curtin.block.bcache.os.path.basename')
    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.sysfs_path')
    def test_get_attached_cacheset(self, m_spath, m_exists, m_base, m_real):
        """ get_attached_cacheset resolves 'cache' symlink under bcache dir."""
        kname = self.random_string()
        cset_uuid = self.random_string()
        bdir = '/sys/class/block/%s/bcache' % kname
        m_spath.return_value = bdir
        m_exists.return_value = True
        cacheset = '/sys/fs/bcache/%s' % cset_uuid
        m_base.return_value = cacheset

        self.assertEqual(cacheset, bcache.get_attached_cacheset(kname))
        m_exists.assert_called_with(bdir + '/cache')

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.os.path.realpath')
    @mock.patch('curtin.block.bcache.os.listdir')
    def test_get_cacheset_members(self, m_listdir, m_real, m_exists):
        """ get_cacheset_members finds backing devices using cacheset."""
        cset_uuid = self.random_string()
        bdev_target = self.random_string()
        cset_dir_keys = [
            'average_key_size', 'bdev0', 'block_size', 'btree_cache_size',
            'bucket_size', 'cache0', 'cache_available_percent', 'clear_stats',
            'congested', 'congested_read_threshold_us',
            'congested_write_threshold_us', 'errors', 'flash_vol_create',
            'internal', 'io_error_halflife', 'io_error_limit',
            'journal_delay_ms', 'root_usage_percent', 'stats_day',
            'stats_five_minute', 'stats_hour', 'stats_total', 'stop',
            'synchronous', 'tree_depth', 'unregister',
        ]
        cset_path = '/sys/fs/bcache/%s' % cset_uuid
        m_listdir.return_value = cset_dir_keys
        m_real.side_effect = iter([bdev_target])
        m_exists.return_value = True
        results = bcache.get_cacheset_members(cset_uuid)
        self.assertEqual([bdev_target], results)
        m_listdir.assert_called_with(cset_path)

    @mock.patch('curtin.block.bcache.os.path.exists')
    @mock.patch('curtin.block.bcache.os.path.realpath')
    def test_get_cacheset_cachedev(self, m_real, m_exists):
        """ get_cacheset_cachedev finds cacheset device path."""
        cset_uuid = self.random_string()
        cachedev_target = self.random_string()
        cset_path = '/sys/fs/bcache/%s/cache0' % cset_uuid
        m_exists.return_value = True
        m_real.side_effect = iter([cachedev_target])
        results = bcache.get_cacheset_cachedev(cset_uuid)
        self.assertEqual(cachedev_target, results)
        m_real.assert_called_with(cset_path)

    @mock.patch('curtin.block.bcache.is_backing')
    @mock.patch('curtin.block.bcache.sysfs_path')
    @mock.patch('curtin.block.bcache.os.listdir')
    def test_get_backing_device(self, m_list, m_sysp, m_back):
        """ extract sysfs path to backing device from bcache kname."""
        bcache_kname = self.random_string()
        backing_kname = self.random_string()
        caching_kname = self.random_string()
        m_list.return_value = [backing_kname, caching_kname]
        m_sysp.side_effect = lambda x: '/sys/class/block/%s/bcache' % x
        m_back.side_effect = iter([True, False])

        self.assertEqual('/sys/class/block/%s/bcache' % backing_kname,
                         bcache.get_backing_device(bcache_kname))

    @mock.patch('curtin.block.bcache.is_backing')
    @mock.patch('curtin.block.bcache.sysfs_path')
    @mock.patch('curtin.block.bcache.os.listdir')
    def test_get_backing_device_none_empty_dir(self, m_list, m_sysp, m_back):
        """ get_backing_device returns None on missing deps dir. """
        bcache_kname = self.random_string()
        m_list.side_effect = FileMissingError('does not exist')
        self.assertEqual(None, bcache.get_backing_device(bcache_kname))

    @mock.patch('curtin.block.bcache.is_backing')
    @mock.patch('curtin.block.bcache.sysfs_path')
    @mock.patch('curtin.block.bcache.os.listdir')
    def test_get_backing_device_raise_empty_dir(self, m_list, m_sysp, m_back):
        """ get_backing_device raises RuntimeError on empty deps dir."""
        bcache_kname = self.random_string()
        m_list.return_value = []
        with self.assertRaises(RuntimeError):
            bcache.get_backing_device(bcache_kname)

    @mock.patch('curtin.block.bcache._stop_device')
    def test_stop_cacheset(self, m_stop):
        """ stop_cacheset calls _stop_device with correct sysfs path. """
        cset_uuid = self.random_string()
        bcache.stop_cacheset(cset_uuid)
        m_stop.assert_called_with('/sys/fs/bcache/%s' % cset_uuid)

    @mock.patch('curtin.block.bcache._stop_device')
    def test_stop_cacheset_full_path(self, m_stop):
        """ stop_cacheset accepts full path to cacheset. """
        cset_path = '/sys/fs/bcache/%s' % self.random_string()
        bcache.stop_cacheset(cset_path)
        m_stop.assert_called_with(cset_path)

    @mock.patch('curtin.block.bcache._stop_device')
    @mock.patch('curtin.block.bcache.is_caching')
    @mock.patch('curtin.block.bcache.is_backing')
    def test_stop_device_backing(self, m_back, m_cache, m_stop):
        """ stop_device allows backing device to be stopped. """
        device = '/sys/class/block/%s' % self.random_string()
        m_back.return_value = True
        bcache.stop_device(device)
        m_stop.assert_called_with(device)
        m_back.assert_called_with(device)
        self.assertEqual(0, m_cache.call_count)

    @mock.patch('curtin.block.bcache._stop_device')
    @mock.patch('curtin.block.bcache.is_caching')
    @mock.patch('curtin.block.bcache.is_backing')
    def test_stop_device_caching(self, m_back, m_cache, m_stop):
        """ stop_device allows caching device to be stopped. """
        device = '/sys/class/block/%s' % self.random_string()
        m_back.return_value = False
        m_cache.return_value = True
        bcache.stop_device(device)
        m_stop.assert_called_with(device)
        m_back.assert_called_with(device)
        m_cache.assert_called_with(device)

    @mock.patch('curtin.block.bcache._stop_device')
    @mock.patch('curtin.block.bcache.is_caching')
    @mock.patch('curtin.block.bcache.is_backing')
    def test_stop_device_raise_non_syspath(self, m_back, m_cache, m_stop):
        """ stop_device raises ValueError if device is not sysfs path."""
        device = self.random_string()
        with self.assertRaises(ValueError):
            bcache.stop_device(device)
        self.assertEqual(0, m_stop.call_count)
        self.assertEqual(0, m_back.call_count)
        self.assertEqual(0, m_cache.call_count)

    @mock.patch('curtin.block.bcache._stop_device')
    @mock.patch('curtin.block.bcache.is_caching')
    @mock.patch('curtin.block.bcache.is_backing')
    def test_stop_device_raise_non_bcache_dev(self, m_back, m_cache, m_stop):
        """ stop_device raises ValueError if device is not bcache device."""
        device = '/sys/class/block/%s' % self.random_string()
        m_back.return_value = False
        m_cache.return_value = False
        with self.assertRaises(ValueError):
            bcache.stop_device(device)
        self.assertEqual(0, m_stop.call_count)
        self.assertEqual(1, m_back.call_count)
        self.assertEqual(1, m_cache.call_count)

    @mock.patch('curtin.block.bcache.util.wait_for_removal')
    @mock.patch('curtin.block.bcache.util.write_file')
    @mock.patch('curtin.block.bcache.os.path.exists')
    def test__stop_device_stops_bcache_devs(self, m_exists, m_write, m_wait):
        """ _stop_device accepts  path and issue stop."""
        device = self.random_string()
        stop_path = os.path.join(device, 'stop')
        m_exists.return_value = True
        bcache._stop_device(device)
        m_exists.assert_called_with(stop_path)
        m_write.assert_called_with(stop_path, '1', mode=None)
        m_wait.assert_called_with(stop_path, retries=bcache.BCACHE_RETRIES)

    @mock.patch('curtin.block.bcache.util.wait_for_removal')
    @mock.patch('curtin.block.bcache.util.write_file')
    @mock.patch('curtin.block.bcache.os.path.exists')
    def test__stop_device_already_removed(self, m_exists, m_write, m_wait):
        """ _stop_device skips if device path is missing. """
        device = self.random_string()
        stop_path = os.path.join(device, 'stop')
        m_exists.return_value = False

        bcache._stop_device(device)
        m_exists.assert_called_with(stop_path)
        self.assertEqual(0, m_write.call_count)
        self.assertEqual(0, m_wait.call_count)

    @mock.patch('curtin.block.bcache.util.wait_for_removal')
    @mock.patch('curtin.block.bcache.util.write_file')
    @mock.patch('curtin.block.bcache.os.path.exists')
    def test__stop_device_eats_err_calls_wait(self, m_exists, m_write, m_wait):
        """ _stop_device eats IOError or OSErrors wait still called"""
        device = self.random_string()
        stop_path = os.path.join(device, 'stop')
        m_exists.return_value = True
        m_write.side_effect = IOError('permission denied')

        bcache._stop_device(device)

        m_exists.assert_called_with(stop_path)
        m_write.assert_called_with(stop_path, '1', mode=None)
        m_wait.assert_called_with(stop_path, retries=bcache.BCACHE_RETRIES)

    @mock.patch('curtin.block.bcache.util.wait_for_removal')
    @mock.patch('curtin.block.bcache.util.write_file')
    @mock.patch('curtin.block.bcache.os.path.exists')
    def test__stop_device_raises_if_wait_expires(self, m_exists, m_write,
                                                 m_wait):
        """ _stop_device raises OSError if wait time expires """
        device = self.random_string()
        stop_path = os.path.join(device, 'stop')
        m_exists.return_value = True
        m_wait.side_effect = (
            OSError('Timeout exeeded for removal of %s' % stop_path))
        with self.assertRaises(OSError):
            bcache._stop_device(device)

        m_exists.assert_called_with(stop_path)
        m_write.assert_called_with(stop_path, '1', mode=None)
        m_wait.assert_called_with(stop_path, retries=bcache.BCACHE_RETRIES)


# vi: ts=4 expandtab syntax=python
