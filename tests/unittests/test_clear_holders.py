from unittest import TestCase
import mock

from curtin.block import clear_holders


class TestClearHolders(TestCase):

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

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.open')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache(self, mock_get_bcache, mock_open, mock_log):
        """test clear_holders.shutdown_bcache"""
        bcache_sys_block = '/sys/block/bcache0'
        mock_get_bcache.return_value = '/dev/null'
        clear_holders.shutdown_bcache(bcache_sys_block)
        mock_get_bcache.assert_called_with(bcache_sys_block)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warn.called)
        mock_open.assert_called_with('/dev/null/stop', 'w')

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.open')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_err(self, mock_get_bcache, mock_open, mock_log):
        """ensure that clear_holders.shutdown_bcache catches OSError"""
        # this is the only of the shutdown handlers that has a need to for
        # passing on an error, because there are some cases where a single
        # bcache device can have multiple knames, such as when there are
        # multiple backing devices sharing a single cache device, and therefore
        # clear_holders may attempt to shutdown the same bcache device twice

        def raise_os_err(_):
            raise OSError('test')

        mock_get_bcache.side_effect = raise_os_err
        clear_holders.shutdown_bcache('/dev/null')
        self.assertFalse(mock_open.called)
        self.assertFalse(mock_log.debug.called)
        self.assertTrue(mock_log.warn.called)

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    @mock.patch('curtin.block.clear_holders.lvm')
    @mock.patch('curtin.block.clear_holders.util')
    def test_shutdown_lvm(self, mock_util, mock_lvm, mock_syspath, mock_log):
        """test clear_holders.shutdown_lvm"""
        pass
