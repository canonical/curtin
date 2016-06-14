from unittest import TestCase
from curtin.block import clear_holders
from curtin import block
import os
import mock


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

        def _bcache_using_dev(dev):
            if dev != fake_bcache_dev:
                raise OSError(2, 'no sysfs path')
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
