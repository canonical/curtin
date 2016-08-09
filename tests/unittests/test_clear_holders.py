from unittest import TestCase
import mock

from curtin.block import clear_holders
import os
import textwrap


class TestClearHolders(TestCase):
    example_holders_trees = [
        [{'device': '/sys/class/block/sda', 'name': 'sda', 'holders':
          [{'device': '/sys/class/block/sda/sda1', 'name': 'sda1',
            'holders': [], 'dev_type': 'partition'},
           {'device': '/sys/class/block/sda/sda2', 'name': 'sda2',
            'holders': [], 'dev_type': 'partition'},
           {'device': '/sys/class/block/sda/sda5', 'name': 'sda5', 'holders':
            [{'device': '/sys/class/block/dm-0', 'name': 'dm-0', 'holders':
              [{'device': '/sys/class/block/dm-1', 'name': 'dm-1',
                'holders': [], 'dev_type': 'lvm'},
               {'device': '/sys/class/block/dm-2', 'name': 'dm-2', 'holders':
                [{'device': '/sys/class/block/dm-3', 'name': 'dm-3',
                  'holders': [], 'dev_type': 'lvm'}],
                'dev_type': 'lvm'}],
              'dev_type': 'lvm'}],
            'dev_type': 'partition'}],
          'dev_type': 'disk'}],
        [{"device": "/sys/class/block/vdb", 'name': 'vdb', "holders":
          [{"device": "/sys/class/block/vdb/vdb1", 'name': 'vdb1',
            "holders": [], "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb2", 'name': 'vdb2',
            "holders": [], "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb3", 'name': 'vdb3', "holders":
            [{"device": "/sys/class/block/md0", 'name': 'md0', "holders":
              [{"device": "/sys/class/block/bcache1", 'name': 'bcache1',
                "holders": [], "dev_type": "bcache"}],
              "dev_type": "raid"}],
            "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb4", 'name': 'vdb4', "holders":
            [{"device": "/sys/class/block/md0", 'name': 'md0', "holders":
              [{"device": "/sys/class/block/bcache1", 'name': 'bcache1',
                "holders": [], "dev_type": "bcache"}],
              "dev_type": "raid"}],
            "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb5", 'name': 'vdb5', "holders":
            [{"device": "/sys/class/block/md0", 'name': 'md0', "holders":
              [{"device": "/sys/class/block/bcache1", 'name': 'bcache1',
                "holders": [], "dev_type": "bcache"}],
              "dev_type": "raid"}],
            "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb6", 'name': 'vdb6', "holders":
            [{"device": "/sys/class/block/bcache1", 'name': 'bcache1',
              "holders": [], "dev_type": "bcache"},
             {"device": "/sys/class/block/bcache2", 'name': 'bcache2',
              "holders": [], "dev_type": "bcache"}],
            "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb7", 'name': 'vdb7', "holders":
            [{"device": "/sys/class/block/bcache2", 'name': 'bcache2',
              "holders": [], "dev_type": "bcache"}],
            "dev_type": "partition"},
           {"device": "/sys/class/block/vdb/vdb8", 'name': 'vdb8',
            "holders": [], "dev_type": "partition"}],
          "dev_type": "disk"},
         {"device": "/sys/class/block/vdc", 'name': 'vdc', "holders": [],
          "dev_type": "disk"},
         {"device": "/sys/class/block/vdd", 'name': 'vdd', "holders":
          [{"device": "/sys/class/block/vdd/vdd1", 'name': 'vdd1',
            "holders": [], "dev_type": "partition"}],
          "dev_type": "disk"}],
    ]

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
        self.assertTrue(mock_log.warning.called)

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    @mock.patch('curtin.block.clear_holders.lvm')
    @mock.patch('curtin.block.clear_holders.util')
    def test_shutdown_lvm(self, mock_util, mock_lvm, mock_syspath, mock_log):
        """test clear_holders.shutdown_lvm"""
        device = '/dev/null'
        vg_name = 'volgroup1'
        lv_name = 'lvol1'
        mock_syspath.return_value = device
        mock_util.load_file.return_value = '-'.join((vg_name, lv_name))
        mock_lvm.split_lvm_name.return_value = (vg_name, lv_name)
        mock_lvm.get_lvols_in_volgroup.return_value = ['lvol2']
        clear_holders.shutdown_lvm(device)
        mock_syspath.assert_called_with(device)
        mock_util.load_file.assert_called_with(device + '/dm/name')
        mock_lvm.split_lvm_name.assert_called_with(
            '-'.join((vg_name, lv_name)))
        self.assertTrue(mock_log.debug.called)
        mock_util.subp.assert_called_with(
            ['lvremove', '--force', '--force', '/'.join((vg_name, lv_name))],
            rcs=[0, 5])
        mock_lvm.get_lvols_in_volgroup.assert_called_with(vg_name)
        self.assertEqual(len(mock_util.subp.call_args_list), 1)
        self.assertTrue(mock_lvm.lvm_scan.called)
        mock_lvm.get_lvols_in_volgroup.return_value = []
        clear_holders.shutdown_lvm(device)
        mock_util.subp.assert_called_with(
            ['vgremove', '--force', '--force', vg_name], rcs=[0, 5])

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block')
    def test_shutdown_mdadm(self, mock_block, mock_log):
        """test clear_holders.shutdown_mdadm"""
        device = '/dev/null'
        syspath = '/sys/block/null'
        mock_block.sysfs_to_devpath.return_value = device
        clear_holders.shutdown_mdadm(syspath)
        mock_block.mdadm.mdadm_stop.assert_called_with(device)
        mock_block.mdadm.mdadm_remove.assert_called_with(device)
        self.assertTrue(mock_log.debug.called)

    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.block')
    def test_clear_holders_wipe_superblock(self, mock_block, mock_util,
                                           mock_log, mock_os):
        """test clear_holders.wipe_superblock handles errors right"""
        device = '/dev/null'
        syspath = '/sys/block/null'
        mock_block.sysfs_to_devpath.return_value = device
        clear_holders.wipe_superblock(syspath)
        mock_block.sysfs_to_devpath.assert_called_with(syspath)
        mock_block.wipe_volume.assert_called_with(device, mode='superblock')
        self.assertFalse(mock_util.is_file_not_found_exc.called)
        self.assertTrue(mock_log.info.called)

        def raise_os_error(blockdev, mode=None):
            raise OSError('test')

        mock_block.wipe_volume.side_effect = raise_os_error
        mock_util.is_file_not_found_exc.return_value = True
        mock_util.load_file.return_value = '2'
        mock_os.path.exists.return_value = True
        clear_holders.wipe_superblock(syspath)

        mock_util.is_file_not_found_exc.return_value = False
        with self.assertRaises(OSError):
            clear_holders.wipe_superblock(syspath)

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block')
    @mock.patch('curtin.block.clear_holders.os')
    def test_get_holders(self, mock_os, mock_block, mock_log):
        """test clear_holders.get_holders"""
        sysfs_path = '/sys/block/null'
        device = '/dev/null'
        mock_block.sys_block_path.return_value = sysfs_path
        mock_os.path.join.side_effect = os.path.join
        clear_holders.get_holders(device)
        mock_block.sys_block_path.assert_called_with(device)
        mock_os.path.join.assert_called_with(sysfs_path, 'holders')
        self.assertTrue(mock_log.debug.called)
        mock_os.listdir.assert_called_with(os.path.join(sysfs_path, 'holders'))

    def test_plan_shutdown_holders_trees(self):
        """
        make sure clear_holdrs.plan_shutdown_holders_tree orders shutdown
        functions correctly and uses the appropriate shutdown function for each
        dev type
        """
        # trees that have been generated, checked for correctness,
        # and the order that they should be shut down in (by level)
        test_trees_and_orders = [
            (self.example_holders_trees[0][0],
             ({'dm-3'}, {'dm-1', 'dm-2'}, {'dm-0'}, {'sda5', 'sda2', 'sda1'},
              {'sda'})),
            (self.example_holders_trees[1],
             ({'bcache1'}, {'bcache2', 'md0'},
              {'vdb1', 'vdb2', 'vdb3', 'vdb4', 'vdb5', 'vdb6', 'vdb7', 'vdb8',
               'vdd1'},
              {'vdb', 'vdc', 'vdd'}))
        ]
        for tree, correct_order in test_trees_and_orders:
            res = clear_holders.plan_shutdown_holder_trees(tree)
            for level in correct_order:
                self.assertEqual({os.path.basename(e['device'])
                                  for e in res[:len(level)]}, level)
                res = res[len(level):]

    def test_format_holders_tree(self):
        """test output of clear_holders.format_holders_tree"""
        test_trees_and_results = [
            (self.example_holders_trees[0][0],
             textwrap.dedent("""
                 sda
                 |-- sda1
                 |-- sda2
                 `-- sda5
                     `-- dm-0
                         |-- dm-1
                         `-- dm-2
                             `-- dm-3
                 """).strip()),
            (self.example_holders_trees[1][0],
             textwrap.dedent("""
                 vdb
                 |-- vdb1
                 |-- vdb2
                 |-- vdb3
                 |   `-- md0
                 |       `-- bcache1
                 |-- vdb4
                 |   `-- md0
                 |       `-- bcache1
                 |-- vdb5
                 |   `-- md0
                 |       `-- bcache1
                 |-- vdb6
                 |   |-- bcache1
                 |   `-- bcache2
                 |-- vdb7
                 |   `-- bcache2
                 `-- vdb8
                 """).strip()),
            (self.example_holders_trees[1][1], 'vdc'),
            (self.example_holders_trees[1][2],
             textwrap.dedent("""
                 vdd
                 `-- vdd1
                 """).strip())
        ]
        for tree, result in test_trees_and_results:
            self.assertEqual(clear_holders.format_holders_tree(tree), result)

    def test_get_holder_types(self):
        """test clear_holders.get_holder_types"""
        test_trees_and_results = [
            (self.example_holders_trees[0][0],
             {('disk', '/sys/class/block/sda'),
              ('partition', '/sys/class/block/sda/sda1'),
              ('partition', '/sys/class/block/sda/sda2'),
              ('partition', '/sys/class/block/sda/sda5'),
              ('lvm', '/sys/class/block/dm-0'),
              ('lvm', '/sys/class/block/dm-1'),
              ('lvm', '/sys/class/block/dm-2'),
              ('lvm', '/sys/class/block/dm-3')}),
            (self.example_holders_trees[1][0],
             {('disk', '/sys/class/block/vdb'),
              ('partition', '/sys/class/block/vdb/vdb1'),
              ('partition', '/sys/class/block/vdb/vdb2'),
              ('partition', '/sys/class/block/vdb/vdb3'),
              ('partition', '/sys/class/block/vdb/vdb4'),
              ('partition', '/sys/class/block/vdb/vdb5'),
              ('partition', '/sys/class/block/vdb/vdb6'),
              ('partition', '/sys/class/block/vdb/vdb7'),
              ('partition', '/sys/class/block/vdb/vdb8'),
              ('raid', '/sys/class/block/md0'),
              ('bcache', '/sys/class/block/bcache1'),
              ('bcache', '/sys/class/block/bcache2')})
        ]
        for tree, result in test_trees_and_results:
            self.assertEqual(clear_holders.get_holder_types(tree), result)

    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    @mock.patch('curtin.block.clear_holders.gen_holders_tree')
    def test_assert_clear(self, mock_gen_holders_tree, mock_syspath):
        mock_gen_holders_tree.return_value = self.example_holders_trees[0][0]
        mock_syspath.side_effect = lambda x: x
        device = '/dev/null'
        with self.assertRaises(OSError):
            clear_holders.assert_clear(device)
            mock_gen_holders_tree.assert_called_with(device)
        mock_gen_holders_tree.return_value = self.example_holders_trees[1][1]
        clear_holders.assert_clear(device)
