import mock
import os
import textwrap

from curtin.block import clear_holders
from .helpers import CiTestCase


class TestClearHolders(CiTestCase):
    test_blockdev = '/dev/null'
    test_syspath = '/sys/class/block/null'
    remove_retries = [0.2] * 150  # clear_holders defaults to 30 seconds
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
                  'holders': [], 'dev_type': 'crypt'}],
                'dev_type': 'lvm'}],
              'dev_type': 'crypt'}],
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
    @mock.patch('curtin.block.clear_holders.util')
    def test_get_dmsetup_uuid(self, mock_util, mock_block):
        """ensure that clear_holders.get_dmsetup_uuid works as expected"""
        uuid = "CRYPT-LUKS1-fe335a74374e4649af9776c1699676f8-sdb5_crypt"
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        mock_util.subp.return_value = (' ' + uuid + '\n', None)
        res = clear_holders.get_dmsetup_uuid(self.test_syspath)
        mock_util.subp.assert_called_with(
            ['dmsetup', 'info', self.test_blockdev, '-C', '-o',
             'uuid', '--noheadings'], capture=True)
        self.assertEqual(res, uuid)
        mock_block.sysfs_to_devpath.assert_called_with(self.test_syspath)

    @mock.patch('curtin.block.clear_holders.block')
    @mock.patch('curtin.block.clear_holders.os')
    def test_get_bcache_using_dev(self, mock_os, mock_block):
        """Ensure that get_bcache_using_dev works"""
        fake_bcache = '/sys/fs/bcache/fake'
        mock_os.path.join.side_effect = os.path.join
        mock_block.sys_block_path.return_value = self.test_syspath
        mock_os.path.realpath.return_value = fake_bcache

        bcache_dir = clear_holders.get_bcache_using_dev(self.test_blockdev)
        mock_os.path.realpath.assert_called_with(self.test_syspath +
                                                 '/bcache/cache')
        self.assertEqual(bcache_dir, fake_bcache)

    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.block')
    def test_get_bcache_sys_path(self, mock_block, mock_os):
        fake_backing = '/sys/class/block/fake'
        mock_block.sys_block_path.return_value = fake_backing
        mock_os.path.join.side_effect = os.path.join
        mock_os.path.exists.return_value = True
        bcache_dir = clear_holders.get_bcache_sys_path("/dev/fake")
        self.assertEqual(bcache_dir, fake_backing + "/bcache")

    @mock.patch('curtin.block.clear_holders.get_dmsetup_uuid')
    @mock.patch('curtin.block.clear_holders.block')
    def test_differentiate_lvm_and_crypt(
            self, mock_block, mock_get_dmsetup_uuid):
        """test clear_holders.identify_lvm and clear_holders.identify_crypt"""
        for (kname, dm_uuid, is_lvm, is_crypt) in [
                ('dm-0', 'LVM-abcdefg', True, False),
                ('sda', 'LVM-abcdefg', False, False),
                ('sda', 'CRYPT-abcdefg', False, False),
                ('dm-0', 'CRYPT-abcdefg', False, True),
                ('dm-1', 'invalid', False, False)]:
            mock_block.path_to_kname.return_value = kname
            mock_get_dmsetup_uuid.return_value = dm_uuid
            self.assertEqual(
                is_lvm, clear_holders.identify_lvm(self.test_syspath))
            self.assertEqual(
                is_crypt, clear_holders.identify_crypt(self.test_syspath))
            mock_block.path_to_kname.assert_called_with(self.test_syspath)
            mock_get_dmsetup_uuid.assert_called_with(self.test_syspath)

    @mock.patch('curtin.block.clear_holders.udev.udevadm_settle')
    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache(self, mock_get_bcache, mock_log, mock_os,
                             mock_util, mock_get_bcache_block,
                             mock_udevadm_settle):
        """test clear_holders.shutdown_bcache"""
        #
        # pass in a sysfs path to a bcache block device,
        # determine the bcache cset it is part of (or not)
        # 1) stop the cset device (if it's enabled)
        # 2) wait on cset to be removed if it was present
        # 3) stop the block device (if it's still present after stopping cset)
        # 4) wait on bcache block device to be removed
        #

        device = self.test_syspath
        bcache_cset_uuid = 'c08ae789-a964-46fb-a66e-650f0ae78f94'

        mock_os.path.exists.return_value = True
        mock_os.path.join.side_effect = os.path.join
        # os.path.realpath on symlink of /sys/class/block/null/bcache/cache ->
        # to /sys/fs/bcache/cset_UUID
        mock_get_bcache.return_value = '/sys/fs/bcache/' + bcache_cset_uuid
        mock_get_bcache_block.return_value = device + '/bcache'

        clear_holders.shutdown_bcache(device)

        mock_get_bcache.assert_called_with(device, strict=False)
        mock_get_bcache_block.assert_called_with(device, strict=False)

        self.assertTrue(mock_log.info.called)
        self.assertFalse(mock_log.warn.called)
        mock_util.wait_for_removal.assert_has_calls([
                mock.call('/sys/fs/bcache/' + bcache_cset_uuid,
                          retries=self.remove_retries),
                mock.call(device, retries=self.remove_retries)])

        mock_util.write_file.assert_has_calls([
                mock.call('/sys/fs/bcache/%s/stop' % bcache_cset_uuid,
                          '1', mode=None),
                mock.call(device + '/bcache/stop',
                          '1', mode=None)])

    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_non_sysfs_device(self, mock_get_bcache, mock_log,
                                              mock_os, mock_util,
                                              mock_get_bcache_block):
        device = "/dev/fakenull"
        with self.assertRaises(ValueError):
            clear_holders.shutdown_bcache(device)

        self.assertEqual(0, len(mock_get_bcache.call_args_list))
        self.assertEqual(0, len(mock_log.call_args_list))
        self.assertEqual(0, len(mock_os.call_args_list))
        self.assertEqual(0, len(mock_util.call_args_list))
        self.assertEqual(0, len(mock_get_bcache_block.call_args_list))

    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_no_device(self, mock_get_bcache, mock_log,
                                       mock_os, mock_util,
                                       mock_get_bcache_block):
        device = "/sys/class/block/null"
        mock_os.path.exists.return_value = False

        clear_holders.shutdown_bcache(device)

        self.assertEqual(1, len(mock_log.info.call_args_list))
        self.assertEqual(1, len(mock_os.path.exists.call_args_list))
        self.assertEqual(0, len(mock_get_bcache.call_args_list))
        self.assertEqual(0, len(mock_util.call_args_list))
        self.assertEqual(0, len(mock_get_bcache_block.call_args_list))

    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_no_cset(self, mock_get_bcache, mock_log,
                                     mock_os, mock_util,
                                     mock_get_bcache_block):
        device = "/sys/class/block/null"
        mock_os.path.exists.side_effect = iter([
                True,   # backing device exists
                False,  # cset device not present (already removed)
                True,   # backing device (still) exists
        ])
        mock_get_bcache.return_value = '/sys/fs/bcache/fake'
        mock_get_bcache_block.return_value = device + '/bcache'
        mock_os.path.join.side_effect = os.path.join

        clear_holders.shutdown_bcache(device)

        self.assertEqual(2, len(mock_log.info.call_args_list))
        self.assertEqual(3, len(mock_os.path.exists.call_args_list))
        self.assertEqual(1, len(mock_get_bcache.call_args_list))
        self.assertEqual(1, len(mock_get_bcache_block.call_args_list))
        self.assertEqual(1, len(mock_util.write_file.call_args_list))
        self.assertEqual(2, len(mock_util.wait_for_removal.call_args_list))

        mock_get_bcache.assert_called_with(device, strict=False)
        mock_get_bcache_block.assert_called_with(device, strict=False)
        mock_util.write_file.assert_called_with(device + '/bcache/stop',
                                                '1', mode=None)
        retries = self.remove_retries
        mock_util.wait_for_removal.assert_has_calls([
            mock.call(device, retries=retries),
            mock.call(device + '/bcache', retries=retries)])

    @mock.patch('curtin.block.clear_holders.udev.udevadm_settle')
    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_delete_cset_and_backing(self, mock_get_bcache,
                                                     mock_log, mock_os,
                                                     mock_util,
                                                     mock_get_bcache_block,
                                                     mock_udevadm_settle):
        device = "/sys/class/block/null"
        mock_os.path.exists.side_effect = iter([
                True,  # backing device exists
                True,  # cset device not present (already removed)
                True,  # backing device (still) exists
        ])
        cset = '/sys/fs/bcache/fake'
        mock_get_bcache.return_value = cset
        mock_get_bcache_block.return_value = device + '/bcache'
        mock_os.path.join.side_effect = os.path.join

        clear_holders.shutdown_bcache(device)

        self.assertEqual(2, len(mock_log.info.call_args_list))
        self.assertEqual(3, len(mock_os.path.exists.call_args_list))
        self.assertEqual(1, len(mock_get_bcache.call_args_list))
        self.assertEqual(1, len(mock_get_bcache_block.call_args_list))
        self.assertEqual(2, len(mock_util.write_file.call_args_list))
        self.assertEqual(3, len(mock_util.wait_for_removal.call_args_list))

        mock_get_bcache.assert_called_with(device, strict=False)
        mock_get_bcache_block.assert_called_with(device, strict=False)
        mock_util.write_file.assert_has_calls([
            mock.call(cset + '/stop', '1', mode=None),
            mock.call(device + '/bcache/stop', '1', mode=None)])
        mock_util.wait_for_removal.assert_has_calls([
            mock.call(cset, retries=self.remove_retries),
            mock.call(device, retries=self.remove_retries)
        ])

    @mock.patch('curtin.block.clear_holders.udev.udevadm_settle')
    @mock.patch('curtin.block.clear_holders.get_bcache_sys_path')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.get_bcache_using_dev')
    def test_shutdown_bcache_delete_cset_no_backing(self, mock_get_bcache,
                                                    mock_log, mock_os,
                                                    mock_util,
                                                    mock_get_bcache_block,
                                                    mock_udevadm_settle):
        device = "/sys/class/block/null"
        mock_os.path.exists.side_effect = iter([
                True,   # backing device exists
                True,   # cset device not present (already removed)
                False,  # backing device is removed with cset
        ])
        cset = '/sys/fs/bcache/fake'
        mock_get_bcache.return_value = cset
        mock_get_bcache_block.return_value = device + '/bcache'
        mock_os.path.join.side_effect = os.path.join

        clear_holders.shutdown_bcache(device)

        self.assertEqual(2, len(mock_log.info.call_args_list))
        self.assertEqual(3, len(mock_os.path.exists.call_args_list))
        self.assertEqual(1, len(mock_get_bcache.call_args_list))
        self.assertEqual(1, len(mock_get_bcache_block.call_args_list))
        self.assertEqual(1, len(mock_util.write_file.call_args_list))
        self.assertEqual(1, len(mock_util.wait_for_removal.call_args_list))

        mock_get_bcache.assert_called_with(device, strict=False)
        mock_util.write_file.assert_has_calls([
            mock.call(cset + '/stop', '1', mode=None),
        ])
        mock_util.wait_for_removal.assert_has_calls([
            mock.call(cset, retries=self.remove_retries)
        ])

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block.sys_block_path')
    @mock.patch('curtin.block.clear_holders.lvm')
    @mock.patch('curtin.block.clear_holders.util')
    def test_shutdown_lvm(self, mock_util, mock_lvm, mock_syspath, mock_log):
        """test clear_holders.shutdown_lvm"""
        vg_name = 'volgroup1'
        lv_name = 'lvol1'
        mock_syspath.return_value = self.test_blockdev
        mock_util.load_file.return_value = '-'.join((vg_name, lv_name))
        mock_lvm.split_lvm_name.return_value = (vg_name, lv_name)
        mock_lvm.get_lvols_in_volgroup.return_value = ['lvol2']
        clear_holders.shutdown_lvm(self.test_blockdev)
        mock_syspath.assert_called_with(self.test_blockdev)
        mock_util.load_file.assert_called_with(self.test_blockdev + '/dm/name')
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
        clear_holders.shutdown_lvm(self.test_blockdev)
        mock_util.subp.assert_called_with(
            ['vgremove', '--force', '--force', vg_name], rcs=[0, 5])

    @mock.patch('curtin.block.clear_holders.block')
    @mock.patch('curtin.block.clear_holders.util')
    def test_shutdown_crypt(self, mock_util, mock_block):
        """test clear_holders.shutdown_crypt"""
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        clear_holders.shutdown_crypt(self.test_syspath)
        mock_block.sysfs_to_devpath.assert_called_with(self.test_syspath)
        mock_util.subp.assert_called_with(
            ['cryptsetup', 'remove', self.test_blockdev], capture=True)

    @mock.patch('curtin.block.clear_holders.time')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.mdadm')
    @mock.patch('curtin.block.clear_holders.block')
    def test_shutdown_mdadm(self, mock_block, mock_mdadm, mock_log, mock_util,
                            mock_time):
        """test clear_holders.shutdown_mdadm"""
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        mock_block.path_to_kname.return_value = self.test_blockdev
        mock_mdadm.md_present.return_value = False
        clear_holders.shutdown_mdadm(self.test_syspath)
        mock_mdadm.mdadm_stop.assert_called_with(self.test_blockdev)
        mock_mdadm.md_present.assert_called_with(self.test_blockdev)
        self.assertTrue(mock_log.debug.called)

    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.time')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.mdadm')
    @mock.patch('curtin.block.clear_holders.block')
    def test_shutdown_mdadm_fail_raises_oserror(self, mock_block, mock_mdadm,
                                                mock_log, mock_util, mock_time,
                                                mock_os):
        """test clear_holders.shutdown_mdadm raises OSError on failure"""
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        mock_block.path_to_kname.return_value = self.test_blockdev
        mock_mdadm.md_present.return_value = True
        mock_util.subp.return_value = ("", "")
        mock_os.path.exists.return_value = True

        with self.assertRaises(OSError):
            clear_holders.shutdown_mdadm(self.test_syspath)

        mock_mdadm.mdadm_stop.assert_called_with(self.test_blockdev)
        mock_mdadm.md_present.assert_called_with(self.test_blockdev)
        mock_util.load_file.assert_called_with('/proc/mdstat')
        self.assertTrue(mock_log.debug.called)
        self.assertTrue(mock_log.critical.called)

    @mock.patch('curtin.block.clear_holders.os')
    @mock.patch('curtin.block.clear_holders.time')
    @mock.patch('curtin.block.clear_holders.util')
    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.mdadm')
    @mock.patch('curtin.block.clear_holders.block')
    def test_shutdown_mdadm_fails_no_proc_mdstat(self, mock_block, mock_mdadm,
                                                 mock_log, mock_util,
                                                 mock_time, mock_os):
        """test clear_holders.shutdown_mdadm handles no /proc/mdstat"""
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        mock_block.path_to_kname.return_value = self.test_blockdev
        mock_mdadm.md_present.return_value = True
        mock_os.path.exists.return_value = False

        with self.assertRaises(OSError):
            clear_holders.shutdown_mdadm(self.test_syspath)

        mock_mdadm.mdadm_stop.assert_called_with(self.test_blockdev)
        mock_mdadm.md_present.assert_called_with(self.test_blockdev)
        self.assertEqual([], mock_util.subp.call_args_list)
        self.assertTrue(mock_log.debug.called)
        self.assertTrue(mock_log.critical.called)

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block')
    def test_clear_holders_wipe_superblock(self, mock_block, mock_log):
        """test clear_holders.wipe_superblock handles errors right"""
        mock_block.sysfs_to_devpath.return_value = self.test_blockdev
        mock_block.is_extended_partition.return_value = True
        clear_holders.wipe_superblock(self.test_syspath)
        self.assertFalse(mock_block.wipe_volume.called)
        mock_block.is_extended_partition.return_value = False
        clear_holders.wipe_superblock(self.test_syspath)
        mock_block.sysfs_to_devpath.assert_called_with(self.test_syspath)
        mock_block.wipe_volume.assert_called_with(
            self.test_blockdev, mode='superblock')

    @mock.patch('curtin.block.clear_holders.LOG')
    @mock.patch('curtin.block.clear_holders.block')
    @mock.patch('curtin.block.clear_holders.os')
    def test_get_holders(self, mock_os, mock_block, mock_log):
        """test clear_holders.get_holders"""
        mock_block.sys_block_path.return_value = self.test_syspath
        mock_os.path.join.side_effect = os.path.join
        clear_holders.get_holders(self.test_blockdev)
        mock_block.sys_block_path.assert_called_with(self.test_blockdev)
        mock_os.path.join.assert_called_with(self.test_syspath, 'holders')
        self.assertTrue(mock_log.debug.called)
        mock_os.listdir.assert_called_with(
            os.path.join(self.test_syspath, 'holders'))

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
              ('crypt', '/sys/class/block/dm-0'),
              ('lvm', '/sys/class/block/dm-1'),
              ('lvm', '/sys/class/block/dm-2'),
              ('crypt', '/sys/class/block/dm-3')}),
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

    @mock.patch('curtin.block.clear_holders.mdadm')
    @mock.patch('curtin.block.clear_holders.util')
    def test_start_clear_holders_deps(self, mock_util, mock_mdadm):
        clear_holders.start_clear_holders_deps()
        mock_mdadm.mdadm_assemble.assert_called_with(
            scan=True, ignore_errors=True)
        mock_util.subp.assert_called_with(['modprobe', 'bcache'], rcs=[0, 1])
