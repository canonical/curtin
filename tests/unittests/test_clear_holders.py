from unittest import TestCase
import unittest
import mock

from curtin.block import clear_holders
from curtin import block

import errno
import os


@unittest.skip
class TestClearHolders(TestCase):

    def test_split_vg_lv_name(self):
        """Ensure that split_vg_lv_name works for all possible lvm names"""
        names = ['volgroup-lvol', 'vol--group-lvol', 'test--one-test--two',
                 'test--one--two-lvname']
        split_names = [('volgroup', 'lvol'), ('vol-group', 'lvol'),
                       ('test-one', 'test-two'), ('test-one-two', 'lvname')]
        for name, split in zip(names, split_names):
            self.assertEqual(clear_holders.split_vg_lv_name(name), split)

        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('test')
        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('-test')
        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('test-')

    @mock.patch('curtin.block.clear_holders.block')
    @mock.patch('curtin.block.clear_holders.os')
    def test_get_bcache_using_dev(self, mock_os, mock_block):
        """Ensure that get_bcache_using_dev works"""
        fake_bcache = '/sys/fs/bcache/fake'
        mock_os.path.realpath.return_value = fake_bcache
        mock_os.path.exists.side_effect = lambda x: x == fake_bcache
        mock_block.sys_block_path.return_value = '/sys/block/vda'
        bcache_dir = clear_holders.get_bcache_using_dev('/dev/vda')
        self.assertEqual(bcache_dir, fake_bcache)

        # test that path is verified before return
        with self.assertRaises(OSError):
            mock_os.path.realpath.return_value = '/dev/null'
            clear_holders.get_bcache_using_dev('/dev/vda')

    def _mock_functools(self, func, *args, **kwargs):
        res = {'func': func}
        if args is not None:
            res.update({'args': list(args)})
        if kwargs is not None:
            res.update({'kwargs': dict(kwargs)})
        return res

    @mock.patch('curtin.block.clear_holders.functools')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.util.write_file')
    @mock.patch('curtin.block.clear_holders.glob')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache(self, mock_get_bcache_dev, mock_glob,
                             mock_write_file, mock_log, mock_functools):
        """
        Ensure that shutdown_bcache works as expected even when errors
        encountered
        """
        fake_bcache_dev = '/dev/bcache0'
        fake_bcache_sys = '/sys/fs/bcache/fakebcache'
        bcache0_held = [
            os.path.join(fake_bcache_sys, 'bdev0/dev/slaves', p)
            for p in ['vda', 'vdb']
        ]
        bcache1_held = [
            os.path.join(fake_bcache_sys, 'bdev1/dev/slaves', p)
            for p in ['vda', 'vdc']
        ]

        no_sysfs_path_err = OSError(errno.ENOENT, 'no sysfs path')

        def _bcache_using_dev(dev):
            if dev != fake_bcache_dev:
                raise no_sysfs_path_err
            return fake_bcache_sys

        mock_get_bcache_dev.side_effect = _bcache_using_dev
        mock_functools.partial.side_effect = self._mock_functools
        mock_glob.glob.return_value = bcache0_held + bcache1_held

        # ensure that correct wipe statements returned and bcache is stopped
        (wipe, _err) = clear_holders.shutdown_bcache(fake_bcache_dev)
        self.assertEqual(len(_err), 0)
        mock_write_file.assert_called_with(
            os.path.join(fake_bcache_sys, 'stop'), '1')
        self.assertEqual(len(wipe), 3)
        for p in ['/dev/vda', '/dev/vdb', '/dev/vdc']:
            partial = {'func': block.wipe_volume, 'args': [p],
                       'kwargs': {'mode': 'superblock'}}
            self.assertIn(partial, wipe)

        # ensure that shutdown_bcache exits gracefully if the specified bcache
        # device was not found
        (wipe, _err) = clear_holders.shutdown_bcache('/dev/null')
        self.assertIsNone(wipe)
        self.assertEqual(len(_err), 1)
        self.assertEqual(str(no_sysfs_path_err), _err[0])

    @mock.patch('curtin.block.clear_holders.block.mdadm')
    def test_shutdown_mdadm(self, mock_mdadm):
        """Ensure that shutdown_mdadm makes the correct calls to mdadm"""
        md_dev = '/sys/class/block/null'
        (wipe, _err) = clear_holders.shutdown_mdadm(md_dev)
        self.assertIsNone(wipe)
        self.assertEqual(len(_err), 0)
        mock_mdadm.mdadm_stop.assert_called_with('/dev/null')
        mock_mdadm.mdadm_remove.assert_called_with('/dev/null')

    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    @mock.patch('curtin.block.clear_holders.functools')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.util.subp')
    @mock.patch('curtin.block.clear_holders.util.load_file')
    def test_shutdown_lvm(self, mock_load_file, mock_subp, mock_log,
                          mock_functools, mock_sys_block_path):
        """Ensure that shutdown_lvm works as expected"""
        lvm_path = '/dev/dm-0'
        # this file seems to contain a newline at the end which threw off an
        # earlier version of shutdown_lvm, so check that it works with one in
        # place
        mock_load_file.return_value = 'vg--one-lv--one\n'
        mock_sys_block_path.return_value = '/sys/block/dm-0'
        mock_functools.partial.side_effect = self._mock_functools
        (wipe, _err) = clear_holders.shutdown_lvm(lvm_path)
        self.assertEqual(len(_err), 0)
        mock_subp.assert_called_with(['lvremove', '--force', '--force',
                                      'vg-one/lv-one'])
        self.assertEqual(wipe, {'func': block.wipe_volume, 'args': [lvm_path],
                                'kwargs': {'mode': 'pvremove'}})

        # shutdown_lvm should give up if unable to parse lvm volgroup - logical
        # volume name
        mock_load_file.return_value = 'invalidname'
        (wipe, _err) = clear_holders.shutdown_lvm(lvm_path)
        self.assertIsNone(wipe)
        self.assertEqual(len(_err), 1)
        real_err = OSError(errno.ENOENT,
                           'file: {}{} missing or has invalid contents'
                           .format(mock_sys_block_path.return_value,
                                   '/dm/name'))
        self.assertEqual(str(real_err), _err[0])

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    def test_get_holders(self, mock_sys_block_path, mock_os, mock_log):
        """Test that get_holders works and handles errors correctly"""
        dev_path = '/dev/fake'
        sys_path = '/sys/block/fake'
        holders = ['vda', 'vdb']
        mock_sys_block_path.return_value = sys_path
        mock_os.listdir.return_value = holders
        (res, _err) = clear_holders.get_holders(dev_path)
        mock_sys_block_path.assert_called_with(dev_path)
        self.assertEqual(res, holders)
        self.assertEqual(len(_err), 0)
        # test error handling
        expected_err = OSError(errno.ENOENT, 'no sysfs path')

        def _fail_sys_block_path(dev):
            raise expected_err

        mock_sys_block_path.side_effect = _fail_sys_block_path
        (res, _err) = clear_holders.get_holders(dev_path)
        self.assertEqual(len(res), 0)
        self.assertEqual(len(_err), 1)
        self.assertEqual(str(expected_err), _err[0])

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.clear_holders')
    def test_check_clear(self, mock_clear_holders, mock_log):
        errors = [str(e) for e in
                  [IOError(errno.ENOENT, 'test1'),
                   OSError(errno.ENXIO, 'test2')]]
        mock_clear_holders.return_value = (True, errors)
        clear_holders.check_clear('/dev/null')
        mock_clear_holders.assert_called_with('/dev/null')
        self.assertFalse(mock_log.error.called)
        self.assertTrue(mock_log.warn.called)
        mock_log.warn.assert_called_with(
            'clear_holders encountered error: {}'.format(errors[1]))
        mock_log.info.assert_called_with(
            'clear_holders finished successfully on device: /dev/null')

        # check that error is raised if clear_holders failed
        mock_clear_holders.return_value = (False, errors)
        with self.assertRaises(OSError):
            clear_holders.check_clear('/dev/null')
        self.assertTrue(mock_log.error.called)
