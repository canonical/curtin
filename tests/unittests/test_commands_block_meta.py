# This file is part of curtin. See LICENSE file for copyright and license info.

from argparse import Namespace
from collections import OrderedDict
import copy
from mock import patch, call
import os

from curtin.commands import block_meta
from curtin import paths, util
from .helpers import CiTestCase


class TestGetPathToStorageVolume(CiTestCase):

    def setUp(self):
        super(TestGetPathToStorageVolume, self).setUp()
        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'os.path.exists', 'm_exists')
        self.add_patch(basepath + 'block.lookup_disk', 'm_lookup')
        self.add_patch(basepath + 'devsync', 'm_devsync')
        self.add_patch(basepath + 'util.subp', 'm_subp')
        self.add_patch(basepath + 'multipath.is_mpath_member', 'm_mp')

    def test_block_lookup_called_with_disk_wwn(self):
        volume = 'mydisk'
        wwn = self.random_string()
        cfg = {'id': volume, 'type': 'disk', 'wwn': wwn}
        s_cfg = OrderedDict({volume: cfg})
        block_meta.get_path_to_storage_volume(volume, s_cfg)
        expected_calls = [call(wwn)]
        self.assertEqual(expected_calls, self.m_lookup.call_args_list)

    def test_block_lookup_called_with_disk_serial(self):
        volume = 'mydisk'
        serial = self.random_string()
        cfg = {'id': volume, 'type': 'disk', 'serial': serial}
        s_cfg = OrderedDict({volume: cfg})
        block_meta.get_path_to_storage_volume(volume, s_cfg)
        expected_calls = [call(serial)]
        self.assertEqual(expected_calls, self.m_lookup.call_args_list)

    def test_block_lookup_called_with_disk_wwn_fallback_to_serial(self):
        volume = 'mydisk'
        wwn = self.random_string()
        serial = self.random_string()
        cfg = {'id': volume, 'type': 'disk', 'wwn': wwn, 'serial': serial}
        s_cfg = OrderedDict({volume: cfg})

        # doesn't find wwn, returns path on serial
        self.m_lookup.side_effect = iter([ValueError('Error'), 'foo'])

        block_meta.get_path_to_storage_volume(volume, s_cfg)
        expected_calls = [call(wwn), call(serial)]
        self.assertEqual(expected_calls, self.m_lookup.call_args_list)

    def test_fallback_to_path_when_lookup_wwn_serial_fail(self):
        volume = 'mydisk'
        wwn = self.random_string()
        serial = self.random_string()
        path = "/%s/%s" % (self.random_string(), self.random_string())
        cfg = {'id': volume, 'type': 'disk',
               'path': path, 'wwn': wwn, 'serial': serial}
        s_cfg = OrderedDict({volume: cfg})

        # lookups fail
        self.m_lookup.side_effect = iter([
            ValueError('Error'), ValueError('Error')])

        result = block_meta.get_path_to_storage_volume(volume, s_cfg)
        expected_calls = [call(wwn), call(serial)]
        self.assertEqual(expected_calls, self.m_lookup.call_args_list)
        self.assertEqual(path, result)

    def test_block_lookup_not_called_with_wwn_or_serial_keys(self):
        volume = 'mydisk'
        path = "/%s/%s" % (self.random_string(), self.random_string())
        cfg = {'id': volume, 'type': 'disk', 'path': path}
        s_cfg = OrderedDict({volume: cfg})
        result = block_meta.get_path_to_storage_volume(volume, s_cfg)
        self.assertEqual(0, self.m_lookup.call_count)
        self.assertEqual(path, result)

    def test_exception_raise_if_disk_not_found(self):
        volume = 'mydisk'
        wwn = self.random_string()
        serial = self.random_string()
        path = "/%s/%s" % (self.random_string(), self.random_string())
        cfg = {'id': volume, 'type': 'disk',
               'path': path, 'wwn': wwn, 'serial': serial}
        s_cfg = OrderedDict({volume: cfg})

        # lookups fail
        self.m_lookup.side_effect = iter([
            ValueError('Error'), ValueError('Error')])
        # no path
        self.m_exists.return_value = False
        # not multipath
        self.m_mp.return_value = False

        with self.assertRaises(ValueError):
            block_meta.get_path_to_storage_volume(volume, s_cfg)
        expected_calls = [call(wwn), call(serial)]
        self.assertEqual(expected_calls, self.m_lookup.call_args_list)
        self.m_exists.assert_has_calls([call(path)])


class TestBlockMetaSimple(CiTestCase):
    def setUp(self):
        super(TestBlockMetaSimple, self).setUp()
        self.target = "my_target"

        # block_meta
        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_bootpt_cfg', 'mock_bootpt_cfg')
        self.add_patch(basepath + 'get_partition_format_type',
                       'mock_part_fmt_type')
        # block
        self.add_patch('curtin.block.stop_all_unused_multipath_devices',
                       'mock_block_stop_mp')
        self.add_patch('curtin.block.get_installable_blockdevs',
                       'mock_block_get_installable_bdevs')
        self.add_patch('curtin.block.get_dev_name_entry',
                       'mock_block_get_dev_name_entry')
        self.add_patch('curtin.block.get_root_device',
                       'mock_block_get_root_device')
        self.add_patch('curtin.block.is_valid_device',
                       'mock_block_is_valid_device')
        # config
        self.add_patch('curtin.config.load_command_config',
                       'mock_config_load')
        # util
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.add_patch('curtin.util.load_command_environment',
                       'mock_load_env')

    def test_write_image_to_disk(self):
        source = {
            'type': 'dd-xz',
            'uri': 'http://myhost/curtin-unittest-dd.xz'
        }
        devname = "fakedisk1p1"
        devnode = "/dev/" + devname
        self.mock_block_get_dev_name_entry.return_value = (devname, devnode)

        block_meta.write_image_to_disk(source, devname)

        wget = ['sh', '-c',
                'wget "$1" --progress=dot:mega -O - |xzcat| dd bs=4M of="$2"',
                '--', source['uri'], devnode]
        self.mock_block_get_dev_name_entry.assert_called_with(devname)
        self.mock_subp.assert_has_calls([call(args=wget),
                                         call(['partprobe', devnode]),
                                         call(['udevadm', 'settle'])])
        paths = ["curtin", "system-data/var/lib/snapd", "snaps"]
        self.mock_block_get_root_device.assert_called_with([devname],
                                                           paths=paths)

    def test_write_image_to_disk_ddtgz(self):
        source = {
            'type': 'dd-tgz',
            'uri': 'http://myhost/curtin-unittest-dd.tgz'
        }
        devname = "fakedisk1p1"
        devnode = "/dev/" + devname
        self.mock_block_get_dev_name_entry.return_value = (devname, devnode)

        block_meta.write_image_to_disk(source, devname)

        wget = ['sh', '-c',
                'wget "$1" --progress=dot:mega -O - |'
                'tar -xOzf -| dd bs=4M of="$2"',
                '--', source['uri'], devnode]
        self.mock_block_get_dev_name_entry.assert_called_with(devname)
        self.mock_subp.assert_has_calls([call(args=wget),
                                         call(['partprobe', devnode]),
                                         call(['udevadm', 'settle'])])
        paths = ["curtin", "system-data/var/lib/snapd", "snaps"]
        self.mock_block_get_root_device.assert_called_with([devname],
                                                           paths=paths)

    @patch('curtin.commands.block_meta.meta_clear')
    @patch('curtin.commands.block_meta.write_image_to_disk')
    def test_meta_simple_calls_write_img(self, mock_write_image, mock_clear):
        devname = "fakedisk1p1"
        devnode = "/dev/" + devname
        sources = {
            'unittest': {'type': 'dd-xz',
                         'uri': 'http://myhost/curtin-unittest-dd.xz'}
        }
        config = {
            'block-meta': {'devices': [devname]},
            'sources': sources,
        }
        self.mock_config_load.return_value = config
        self.mock_load_env.return_value = {'target': self.target}
        self.mock_block_is_valid_device.return_value = True
        self.mock_block_get_dev_name_entry.return_value = (devname, devnode)
        mock_write_image.return_value = devname

        args = Namespace(target=self.target, devices=None, mode=None,
                         boot_fstype=None, fstype=None, force_mode=False)

        block_meta.block_meta(args)

        mock_write_image.assert_called_with(sources.get('unittest'), devname)
        self.mock_subp.assert_has_calls(
            [call(['mount', devname, self.target])])


class TestBlockMeta(CiTestCase):

    def setUp(self):
        super(TestBlockMeta, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'mock_getpath')
        self.add_patch(basepath + 'make_dname', 'mock_make_dname')
        self.add_patch(basepath + 'multipath', 'm_mp')
        self.add_patch('curtin.util.load_command_environment',
                       'mock_load_env')
        self.add_patch('curtin.util.subp', 'mock_subp')
        self.add_patch('curtin.util.ensure_dir', 'mock_ensure_dir')
        self.add_patch('curtin.block.get_part_table_type',
                       'mock_block_get_part_table_type')
        self.add_patch('curtin.block.wipe_volume',
                       'mock_block_wipe_volume')
        self.add_patch('curtin.block.path_to_kname',
                       'mock_block_path_to_kname')
        self.add_patch('curtin.block.sys_block_path',
                       'mock_block_sys_block_path')
        self.add_patch('curtin.block.clear_holders.get_holders',
                       'mock_get_holders')
        self.add_patch('curtin.block.clear_holders.clear_holders',
                       'mock_clear_holders')
        self.add_patch('curtin.block.clear_holders.assert_clear',
                       'mock_assert_clear')
        self.add_patch('curtin.block.iscsi.volpath_is_iscsi',
                       'mock_volpath_is_iscsi')
        self.add_patch('curtin.block.get_volume_uuid',
                       'mock_block_get_volume_uuid')
        self.add_patch('curtin.commands.block_meta._get_volume_type',
                       'mock_get_volume_type')
        self.add_patch('curtin.commands.block_meta.udevadm_info',
                       'mock_udevadm_info')
        self.add_patch('curtin.block.zero_file_at_offsets',
                       'mock_block_zero_file')
        self.add_patch('curtin.block.rescan_block_devices',
                       'mock_block_rescan')
        self.add_patch('curtin.block.get_blockdev_sector_size',
                       'mock_block_sector_size')

        self.target = "my_target"
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'grub_device': True,
                     'id': 'sda',
                     'name': 'sda',
                     'path': '/wark/xxx',
                     'ptable': 'msdos',
                     'type': 'disk',
                     'wipe': 'superblock'},
                    {'device': 'sda',
                     'flag': 'boot',
                     'id': 'sda-part1',
                     'name': 'sda-part1',
                     'number': 1,
                     'offset': '4194304B',
                     'size': '511705088B',
                     'type': 'partition',
                     'uuid': 'fc7ab24c-b6bf-460f-8446-d3ac362c0625',
                     'wipe': 'superblock'},
                    {'id': 'sda1-root',
                     'type': 'format',
                     'fstype': 'xfs',
                     'volume': 'sda-part1'},
                    {'id': 'sda-part1-mnt-root',
                     'type': 'mount',
                     'path': '/',
                     'device': 'sda1-root'},
                    {'id': 'sda-part1-mnt-root-ro',
                     'type': 'mount',
                     'path': '/readonly',
                     'options': 'ro',
                     'device': 'sda1-root'}
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

        # mp off by default
        self.m_mp.is_mpath_device.return_value = False
        self.m_mp.is_mpath_member.return_value = False

    def test_disk_handler_calls_clear_holder(self):
        info = self.storage_config.get('sda')
        disk = info.get('path')
        self.mock_getpath.return_value = disk
        self.mock_block_get_part_table_type.return_value = 'dos'
        self.mock_subp.side_effect = iter([
            (0, 0),  # parted mklabel
        ])
        holders = ['md1']
        self.mock_get_holders.return_value = holders

        block_meta.disk_handler(info, self.storage_config)

        print("clear_holders: %s" % self.mock_clear_holders.call_args_list)
        print("assert_clear: %s" % self.mock_assert_clear.call_args_list)
        self.mock_clear_holders.assert_called_with(disk)
        self.mock_assert_clear.assert_called_with(disk)

    def test_partition_handler_wipes_at_partition_offset(self):
        """ Test wiping partition at offset prior to creating partition"""
        disk_info = self.storage_config.get('sda')
        part_info = self.storage_config.get('sda-part1')
        disk_kname = disk_info.get('path')
        part_kname = disk_kname + '1'
        self.mock_getpath.side_effect = iter([
            disk_kname,
            part_kname,
        ])
        self.mock_block_get_part_table_type.return_value = 'dos'
        kname = 'xxx'
        self.mock_block_path_to_kname.return_value = kname
        self.mock_block_sys_block_path.return_value = '/sys/class/block/xxx'
        self.mock_block_sector_size.return_value = (512, 512)

        block_meta.partition_handler(part_info, self.storage_config)
        part_offset = 2048 * 512
        self.mock_block_zero_file.assert_called_with(disk_kname, [part_offset],
                                                     exclusive=False)
        self.mock_subp.assert_has_calls(
            [call(['parted', disk_kname, '--script',
                   'mkpart', 'primary', '2048s', '1001471s',
                   'set', '1', 'boot', 'on'], capture=True)])

    @patch('curtin.util.write_file')
    def test_mount_handler_defaults(self, mock_write_file):
        """Test mount_handler has defaults to 'defaults' for mount options"""
        fstab = self.tmp_path('fstab')
        self.mock_load_env.return_value = {'fstab': fstab,
                                           'target': self.target}
        disk_info = self.storage_config.get('sda')
        fs_info = self.storage_config.get('sda1-root')
        mount_info = self.storage_config.get('sda-part1-mnt-root')

        self.mock_getpath.return_value = '/wark/xxx'
        self.mock_volpath_is_iscsi.return_value = False
        self.mock_udevadm_info.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': [],
        }
        self.mock_get_volume_type.return_value = 'part'

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        comment = "# / was on /wark/xxx during curtin installation"
        expected = "%s\n%s %s %s %s 0 0\n" % (comment,
                                              disk_info['path'],
                                              mount_info['path'],
                                              fs_info['fstype'], options)

        mock_write_file.assert_called_with(fstab, expected, omode='a')

    @patch('curtin.util.write_file')
    def test_mount_handler_uses_mount_options(self, mock_write_file):
        """Test mount_handler 'options' string is present in fstab entry"""
        fstab = self.tmp_path('fstab')
        self.mock_load_env.return_value = {'fstab': fstab,
                                           'target': self.target}
        disk_info = self.storage_config.get('sda')
        fs_info = self.storage_config.get('sda1-root')
        mount_info = self.storage_config.get('sda-part1-mnt-root-ro')

        self.mock_getpath.return_value = '/wark/xxx'
        self.mock_volpath_is_iscsi.return_value = False
        self.mock_udevadm_info.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': [],
        }
        self.mock_get_volume_type.return_value = 'part'

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'ro'
        comment = "# /readonly was on /wark/xxx during curtin installation"
        expected = "%s\n%s %s %s %s 0 0\n" % (comment,
                                              disk_info['path'],
                                              mount_info['path'],
                                              fs_info['fstype'], options)

        mock_write_file.assert_called_with(fstab, expected, omode='a')

    @patch('curtin.util.write_file')
    def test_mount_handler_empty_options_string(self, mock_write_file):
        """Test mount_handler with empty 'options' string, selects defaults"""
        fstab = self.tmp_path('fstab')
        self.mock_load_env.return_value = {'fstab': fstab,
                                           'target': self.target}
        disk_info = self.storage_config.get('sda')
        fs_info = self.storage_config.get('sda1-root')
        mount_info = self.storage_config.get('sda-part1-mnt-root-ro')
        mount_info['options'] = ''

        self.mock_getpath.return_value = '/wark/xxx'
        self.mock_volpath_is_iscsi.return_value = False
        self.mock_udevadm_info.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': [],
        }
        self.mock_get_volume_type.return_value = 'part'

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        comment = "# /readonly was on /wark/xxx during curtin installation"
        expected = "%s\n%s %s %s %s 0 0\n" % (comment,
                                              disk_info['path'],
                                              mount_info['path'],
                                              fs_info['fstype'], options)

        mock_write_file.assert_called_with(fstab, expected, omode='a')

    def test_mount_handler_appends_to_fstab(self):
        """Test mount_handler appends fstab lines to existing file"""
        fstab = self.tmp_path('fstab')
        with open(fstab, 'w') as fh:
            fh.write("#curtin-test\n")

        self.mock_load_env.return_value = {'fstab': fstab,
                                           'target': self.target}
        disk_info = self.storage_config.get('sda')
        fs_info = self.storage_config.get('sda1-root')
        mount_info = self.storage_config.get('sda-part1-mnt-root-ro')
        mount_info['options'] = ''

        self.mock_getpath.return_value = '/wark/xxx'
        self.mock_volpath_is_iscsi.return_value = False
        self.mock_udevadm_info.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': [],
        }
        self.mock_get_volume_type.return_value = 'part'

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        comment = "# /readonly was on /wark/xxx during curtin installation"
        expected = "#curtin-test\n%s\n%s %s %s %s 0 0\n" % (comment,
                                                            disk_info['path'],
                                                            mount_info['path'],
                                                            fs_info['fstype'],
                                                            options)

        with open(fstab, 'r') as fh:
            rendered_fstab = fh.read()

        print(rendered_fstab)
        self.assertEqual(expected, rendered_fstab)


class TestZpoolHandler(CiTestCase):
    @patch('curtin.commands.block_meta.zfs')
    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_zpool_handler_falls_back_to_path_when_no_byid(self, m_getpath,
                                                           m_util, m_block,
                                                           m_zfs):
        storage_config = OrderedDict()
        info = {'type': 'zpool', 'id': 'myrootfs_zfsroot_pool',
                'pool': 'rpool', 'vdevs': ['disk1p1'], 'mountpoint': '/',
                'pool_properties': {'ashift': 42},
                'fs_properties': {'compression': 'lz4'}}
        disk_path = "/wark/mydev"
        m_getpath.return_value = disk_path
        m_block.disk_to_byid_path.return_value = None
        m_util.load_command_environment.return_value = {'target': 'mytarget'}
        block_meta.zpool_handler(info, storage_config)
        m_zfs.zpool_create.assert_called_with(
            info['pool'], [disk_path],
            mountpoint="/",
            altroot="mytarget",
            pool_properties={'ashift': 42},
            zfs_properties={'compression': 'lz4'})


class TestZFSRootUpdates(CiTestCase):
    zfsroot_id = 'myrootfs'
    base = [
        {'id': 'disk1', 'type': 'disk', 'ptable': 'gpt',
         'serial': 'dev_vda', 'name': 'main_disk', 'wipe': 'superblock',
         'grub_device': True},
        {'id': 'disk1p1', 'type': 'partition', 'number': '1',
         'size': '9G', 'device': 'disk1'},
        {'id': 'bios_boot', 'type': 'partition', 'size': '1M',
         'number': '2', 'device': 'disk1', 'flag': 'bios_grub'}]
    zfsroots = [
        {'id': zfsroot_id, 'type': 'format', 'fstype': 'zfsroot',
         'volume': 'disk1p1', 'label': 'cloudimg-rootfs'},
        {'id': 'disk1p1_mount', 'type': 'mount', 'path': '/',
         'device': zfsroot_id}]
    extra = [
        {'id': 'extra', 'type': 'disk', 'ptable': 'gpt',
         'wipe': 'superblock'}
    ]

    def test_basic_zfsroot_update_storage_config(self):
        zfsroot_volname = "/ROOT/zfsroot"
        pool_id = self.zfsroot_id + '_zfsroot_pool'
        newents = [
            {'type': 'zpool', 'id': pool_id,
             'pool': 'rpool', 'vdevs': ['disk1p1'], 'mountpoint': '/'},
            {'type': 'zfs', 'id': self.zfsroot_id + '_zfsroot_container',
             'pool': pool_id, 'volume': '/ROOT',
             'properties': {'canmount': 'off', 'mountpoint': 'none'}},
            {'type': 'zfs', 'id': self.zfsroot_id + '_zfsroot_fs',
             'pool': pool_id, 'volume': zfsroot_volname,
             'properties': {'canmount': 'noauto', 'mountpoint': '/'}},
        ]
        expected = OrderedDict(
            [(i['id'], i) for i in self.base + newents + self.extra])

        scfg = block_meta.extract_storage_ordered_dict(
            {'storage': {'version': 1,
                         'config': self.base + self.zfsroots + self.extra}})
        found = block_meta.zfsroot_update_storage_config(scfg)
        print(util.json_dumps([(k, v) for k, v in found.items()]))
        self.assertEqual(expected, found)

    def test_basic_zfsroot_raise_valueerror_no_gpt(self):
        msdos_base = copy.deepcopy(self.base)
        msdos_base[0]['ptable'] = 'msdos'
        scfg = block_meta.extract_storage_ordered_dict(
            {'storage': {'version': 1,
                         'config': msdos_base + self.zfsroots + self.extra}})
        with self.assertRaises(ValueError):
            block_meta.zfsroot_update_storage_config(scfg)

    def test_basic_zfsroot_raise_valueerror_multi_zfsroot(self):
        extra_disk = [
            {'id': 'disk2', 'type': 'disk', 'ptable': 'gpt',
             'serial': 'dev_vdb', 'name': 'extra_disk', 'wipe': 'superblock'}]
        second_zfs = [
            {'id': 'zfsroot2', 'type': 'format', 'fstype': 'zfsroot',
             'volume': 'disk2', 'label': ''}]
        scfg = block_meta.extract_storage_ordered_dict(
            {'storage': {'version': 1,
                         'config': (self.base + extra_disk +
                                    self.zfsroots + second_zfs)}})
        with self.assertRaises(ValueError):
            block_meta.zfsroot_update_storage_config(scfg)


class TestFstabData(CiTestCase):
    mnt = {'id': 'm1', 'type': 'mount', 'device': 'fs1', 'path': '/',
           'options': 'noatime'}
    base_cfg = [
        {'id': 'xda', 'type': 'disk', 'ptable': 'msdos'},
        {'id': 'xda1', 'type': 'partition', 'size': '3GB',
         'device': 'xda'},
        {'id': 'fs1', 'type': 'format', 'fstype': 'ext4',
         'volume': 'xda1', 'label': 'rfs'},
    ]

    def _my_gptsv(self, d_id, _scfg):
        """local test replacement for get_path_to_storage_volume."""
        if d_id in ("xda", "xda1"):
            return "/dev/" + d_id
        raise RuntimeError("Unexpected call to gptsv with %s" % d_id)

    def test_mount_data_raises_valueerror_if_not_mount(self):
        """mount_data on non-mount type raises ValueError."""
        mnt = self.mnt.copy()
        mnt['type'] = "not-mount"
        with self.assertRaisesRegexp(ValueError, r".*not type 'mount'"):
            block_meta.mount_data(mnt, {mnt['id']: mnt})

    def test_mount_data_no_device_or_spec_raises_valueerror(self):
        """test_mount_data raises ValueError if no device or spec."""
        mnt = self.mnt.copy()
        del mnt['device']
        with self.assertRaisesRegexp(ValueError, r".*mount.*missing.*"):
            block_meta.mount_data(mnt, {mnt['id']: mnt})

    def test_mount_data_invalid_device_ref_raises_valueerror(self):
        """test_mount_data raises ValueError if device is invalid ref."""
        mnt = self.mnt.copy()
        mnt['device'] = 'myinvalid'
        scfg = OrderedDict([(i['id'], i) for i in self.base_cfg + [mnt]])
        with self.assertRaisesRegexp(ValueError, r".*refers.*myinvalid"):
            block_meta.mount_data(mnt, scfg)

    def test_mount_data_invalid_format_ref_raises_valueerror(self):
        """test_mount_data raises ValueError if format.volume is invalid."""
        mycfg = copy.deepcopy(self.base_cfg) + [self.mnt.copy()]
        scfg = OrderedDict([(i['id'], i) for i in mycfg])
        # change the 'volume' entry for the 'format' type.
        scfg['fs1']['volume'] = 'myinvalidvol'
        with self.assertRaisesRegexp(ValueError, r".*refers.*myinvalidvol"):
            block_meta.mount_data(scfg['m1'], scfg)

    def test_non_device_mount_with_spec(self):
        """mount_info with a spec does not need device."""
        info = {'id': 'xm1', 'spec': 'none', 'type': 'mount',
                'fstype': 'tmpfs', 'path': '/tmpfs'}
        self.assertEqual(
            block_meta.FstabData(
                spec="none", fstype="tmpfs", path="/tmpfs",
                options="defaults", freq="0", passno="0", device=None),
            block_meta.mount_data(info, {'xm1': info}))

    @patch('curtin.block.iscsi.volpath_is_iscsi')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_device_mount_basic(self, m_gptsv, m_is_iscsi):
        """Test mount_data for FstabData with a device."""
        m_gptsv.side_effect = self._my_gptsv
        m_is_iscsi.return_value = False

        scfg = OrderedDict(
            [(i['id'], i) for i in self.base_cfg + [self.mnt]])
        self.assertEqual(
            block_meta.FstabData(
                spec=None, fstype="ext4", path="/",
                options="noatime", freq="0", passno="0", device="/dev/xda1"),
            block_meta.mount_data(scfg['m1'], scfg))

    @patch('curtin.block.iscsi.volpath_is_iscsi', return_value=False)
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_device_mount_boot_efi(self, m_gptsv, m_is_iscsi):
        """Test mount_data fat fs gets converted to vfat."""
        bcfg = copy.deepcopy(self.base_cfg)
        bcfg[2]['fstype'] = 'fat32'
        mnt = {'id': 'm1', 'type': 'mount', 'device': 'fs1',
               'path': '/boot/efi'}
        m_gptsv.side_effect = self._my_gptsv

        scfg = OrderedDict(
            [(i['id'], i) for i in bcfg + [mnt]])
        self.assertEqual(
            block_meta.FstabData(
                spec=None, fstype="vfat", path="/boot/efi",
                options="defaults", freq="0", passno="0", device="/dev/xda1"),
            block_meta.mount_data(scfg['m1'], scfg))

    @patch('curtin.block.iscsi.volpath_is_iscsi')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_device_mount_iscsi(self, m_gptsv, m_is_iscsi):
        """mount_data for a iscsi device should have _netdev in opts."""
        m_gptsv.side_effect = self._my_gptsv
        m_is_iscsi.return_value = True

        scfg = OrderedDict([(i['id'], i) for i in self.base_cfg + [self.mnt]])
        self.assertEqual(
            block_meta.FstabData(
                spec=None, fstype="ext4", path="/",
                options="noatime,_netdev", freq="0", passno="0",
                device="/dev/xda1"),
            block_meta.mount_data(scfg['m1'], scfg))

    @patch('curtin.block.iscsi.volpath_is_iscsi')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_spec_fstype_override_inline(self, m_gptsv, m_is_iscsi):
        """spec and fstype are preferred over lookups from 'device' ref.

        If a mount entry has 'fstype' and 'spec', those are prefered over
        values looked up via the 'device' reference present in the entry.
        The test here enforces that the device reference present in
        the mount entry is not looked up, that isn't strictly necessary.
        """
        m_gptsv.side_effect = Exception(
            "Unexpected Call to get_path_to_storage_volume")
        m_is_iscsi.return_value = Exception(
            "Unexpected Call to volpath_is_iscsi")

        myspec = '/dev/disk/by-label/LABEL=rfs'
        mnt = {'id': 'm1', 'type': 'mount', 'device': 'fs1', 'path': '/',
               'options': 'noatime', 'spec': myspec, 'fstype': 'ext3'}
        scfg = OrderedDict([(i['id'], i) for i in self.base_cfg + [mnt]])
        self.assertEqual(
            block_meta.FstabData(
                spec=myspec, fstype="ext3", path="/",
                options="noatime", freq="0", passno="0",
                device=None),
            block_meta.mount_data(mnt, scfg))

    @patch('curtin.commands.block_meta.mount_fstab_data')
    def test_mount_apply_skips_mounting_swap(self, m_mount_fstab_data):
        """mount_apply does not mount swap fs, but should write fstab."""
        fdata = block_meta.FstabData(
            spec="/dev/xxxx1", path="none", fstype='swap')
        fstab = self.tmp_path("fstab")
        block_meta.mount_apply(fdata, fstab=fstab)
        contents = util.load_file(fstab)
        self.assertEqual(0, m_mount_fstab_data.call_count)
        self.assertIn("/dev/xxxx1", contents)
        self.assertIn("swap", contents)

    @patch('curtin.commands.block_meta.mount_fstab_data')
    def test_mount_apply_calls_mount_fstab_data(self, m_mount_fstab_data):
        """mount_apply should call mount_fstab_data to mount."""
        fdata = block_meta.FstabData(
            spec="/dev/xxxx1", path="none", fstype='ext3')
        target = self.tmp_dir()
        block_meta.mount_apply(fdata, target=target, fstab=None)
        self.assertEqual([call(fdata, target=target)],
                         m_mount_fstab_data.call_args_list)

    @patch('curtin.commands.block_meta.mount_fstab_data')
    def test_mount_apply_appends_to_fstab(self, m_mount_fstab_data):
        """mount_apply should append to fstab."""
        fdslash = block_meta.FstabData(
            spec="/dev/disk2", path="/", fstype='ext4')
        fdboot = block_meta.FstabData(
            spec="/dev/disk1", path="/boot", fstype='ext3')
        fstab = self.tmp_path("fstab")
        existing_line = "# this is my line"
        util.write_file(fstab, existing_line + "\n")
        block_meta.mount_apply(fdslash, fstab=fstab)
        block_meta.mount_apply(fdboot, fstab=fstab)

        self.assertEqual(2, m_mount_fstab_data.call_count)
        lines = util.load_file(fstab).splitlines()
        self.assertEqual(existing_line, lines[0])
        self.assertEqual(
            '# / was on /dev/disk2 during curtin installation', lines[1])
        self.assertIn("/dev/disk2", lines[2])
        self.assertEqual(
            '# /boot was on /dev/disk1 during curtin installation', lines[3])
        self.assertIn("/dev/disk1", lines[4])

    def test_fstab_line_for_data_swap(self):
        """fstab_line_for_data return value for swap fstab line."""
        fdata = block_meta.FstabData(
            spec="/dev/disk2", path="none", fstype='swap')
        self.assertEqual(
            ["/dev/disk2", "none", "swap", "sw", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())

    def test_fstab_line_for_data_swap_no_path(self):
        """fstab_line_for_data return value for swap with path=None."""
        fdata = block_meta.FstabData(
            spec="/dev/disk2", path=None, fstype='swap')
        self.assertEqual(
            ["/dev/disk2", "none", "swap", "sw", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())

    def test_fstab_line_for_data_not_swap_and_no_path(self):
        """fstab_line_for_data raises ValueError if no path and not swap."""
        fdata = block_meta.FstabData(
            spec="/dev/disk2", device=None, path="", fstype='ext3')
        with self.assertRaisesRegexp(ValueError, r".*empty.*path"):
            block_meta.fstab_line_for_data(fdata)

    def test_fstab_line_for_data_with_options(self):
        """fstab_line_for_data return value with options."""
        fdata = block_meta.FstabData(
            spec="/dev/disk2", path="/mnt", fstype='btrfs', options='noatime')
        lines = block_meta.fstab_line_for_data(fdata).splitlines()
        self.assertEqual(
            ["/dev/disk2", "/mnt", "btrfs", "noatime", "0", "0"],
            lines[1].split())

    def test_fstab_line_for_data_with_passno_and_freq(self):
        """fstab_line_for_data should respect passno and freq."""
        fdata = block_meta.FstabData(
            spec="/dev/d1", path="/mnt", fstype='ext4', freq="1", passno="2")
        lines = block_meta.fstab_line_for_data(fdata).splitlines()
        self.assertEqual(["1", "2"], lines[1].split()[4:6])

    def test_fstab_line_for_data_raises_error_without_spec_or_device(self):
        """fstab_line_for_data should raise ValueError if no spec or device."""
        fdata = block_meta.FstabData(
            spec=None, device=None, path="/", fstype='ext3')
        match = r".*missing.*spec.*device"
        with self.assertRaisesRegexp(ValueError, match):
            block_meta.fstab_line_for_data(fdata)

    @patch('curtin.commands.block_meta._get_volume_type')
    @patch('curtin.commands.block_meta.udevadm_info')
    def test_fstab_line_for_data_uses_uuid(self, m_uinfo, m_vol_type):
        """fstab_line_for_data with a device mounts by uuid."""
        fdata = block_meta.FstabData(
            device="/dev/disk2", path="/mnt", fstype='ext4')
        uuid = 'b30d2389-5152-4fbc-8f18-0385ef3046c5'
        by_uuid = '/dev/disk/by-uuid/' + uuid
        m_uinfo.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': [by_uuid, '/dev/disk/by-foo/wark'],
        }
        m_vol_type.return_value = 'part'
        lines = block_meta.fstab_line_for_data(fdata).splitlines()
        self.assertEqual(
            "# /mnt was on /dev/disk2 during curtin installation",
            lines[0])
        self.assertEqual(
            [by_uuid, "/mnt", "ext4", "defaults", "0", "0"],
            lines[1].split())
        self.assertEqual(1, m_uinfo.call_count)
        self.assertEqual(1, m_vol_type.call_count)

    @patch('curtin.commands.block_meta._get_volume_type')
    @patch('curtin.commands.block_meta.udevadm_info')
    def test_fstab_line_for_data_uses_device_if_no_uuid(self, m_uinfo,
                                                        m_vol_type):
        """fstab_line_for_data with a device and no uuid uses device."""
        fdata = block_meta.FstabData(
            device="/dev/disk2", path="/mnt", fstype='ext4')
        m_uinfo.return_value = {
            'DEVTYPE': 'partition',
            'DEVLINKS': []
        }
        m_vol_type.return_value = 'part'
        lines = block_meta.fstab_line_for_data(fdata).splitlines()
        self.assertEqual(
            "# /mnt was on /dev/disk2 during curtin installation",
            lines[0])
        self.assertEqual(
            ["/dev/disk2", "/mnt", "ext4", "defaults", "0", "0"],
            lines[1].split())
        self.assertEqual(1, m_uinfo.call_count)
        self.assertEqual(1, m_vol_type.call_count)

    @patch('curtin.block.get_volume_uuid')
    def test_fstab_line_for_data__spec_and_dev_prefers_spec(self, m_get_uuid):
        """fstab_line_for_data should prefer spec over device."""
        spec = "/dev/xvda1"
        fdata = block_meta.FstabData(
            spec=spec, device="/dev/disk/by-uuid/7AC9-DEFF",
            path="/mnt", fstype='ext4')
        m_get_uuid.return_value = None
        lines = block_meta.fstab_line_for_data(fdata).splitlines()
        self.assertEqual(
            '# /mnt was on /dev/xvda1 during curtin installation',
            lines[0])
        self.assertEqual(
            ["/dev/xvda1", "/mnt", "ext4", "defaults", "0", "0"],
            lines[1].split())
        self.assertEqual(0, m_get_uuid.call_count)

    @patch('curtin.util.ensure_dir')
    @patch('curtin.util.subp')
    def test_mount_fstab_data_without_target(self, m_subp, m_ensure_dir):
        """mount_fstab_data with no target param does the right thing."""
        fdata = block_meta.FstabData(
            device="/dev/disk1", path="/mnt", fstype='ext4')
        block_meta.mount_fstab_data(fdata)
        self.assertEqual(
            call(['mount', "-t", "ext4", "-o", "defaults",
                  "/dev/disk1", "/mnt"], capture=True),
            m_subp.call_args)
        self.assertTrue(m_ensure_dir.called)

    def _check_mount_fstab_subp(self, fdata, expected, target=None):
        # expected currently is like: mount <device> <mp>
        # and thus mp will always be target + fdata.path
        if target is None:
            target = self.tmp_dir()

        expected = [
            a if a != "_T_MP" else paths.target_path(target, fdata.path)
            for a in expected]
        with patch("curtin.util.subp") as m_subp:
            block_meta.mount_fstab_data(fdata, target=target)

        self.assertEqual(call(expected, capture=True), m_subp.call_args)
        self.assertTrue(os.path.isdir(self.tmp_path(fdata.path, target)))

    def test_mount_fstab_data_with_spec_and_device(self):
        """mount_fstab_data with spec and device should use device."""
        self._check_mount_fstab_subp(
            block_meta.FstabData(
                spec="LABEL=foo", device="/dev/disk1", path="/mnt",
                fstype='ext4'),
            ['mount', "-t", "ext4", "-o", "defaults", "/dev/disk1", "_T_MP"])

    def test_mount_fstab_data_with_spec_that_is_path(self):
        """If spec is a path outside of /dev, then prefix target."""
        target = self.tmp_dir()
        spec = "/mydata"
        self._check_mount_fstab_subp(
            block_meta.FstabData(
                spec=spec, path="/var/lib", fstype="none", options="bind"),
            ['mount', "-o", "bind", self.tmp_path(spec, target), "_T_MP"],
            target)

    def test_mount_fstab_data_bind_type_creates_src(self):
        """Bind mounts should have both src and target dir created."""
        target = self.tmp_dir()
        spec = "/mydata"
        self._check_mount_fstab_subp(
            block_meta.FstabData(
                spec=spec, path="/var/lib", fstype="none", options="bind"),
            ['mount', "-o", "bind", self.tmp_path(spec, target), "_T_MP"],
            target)
        self.assertTrue(os.path.isdir(self.tmp_path(spec, target)))

    def test_mount_fstab_data_with_spec_that_is_device(self):
        """If spec looks like a path to a device, then use it."""
        spec = "/dev/xxda1"
        self._check_mount_fstab_subp(
            block_meta.FstabData(spec=spec, path="/var/", fstype="ext3"),
            ['mount', "-t", "ext3", "-o", "defaults", spec, "_T_MP"])

    def test_mount_fstab_data_with_device_no_spec(self):
        """mount_fstab_data mounts by spec if present, not require device."""
        spec = "/dev/xxda1"
        self._check_mount_fstab_subp(
            block_meta.FstabData(spec=spec, path="/home", fstype="ext3"),
            ['mount', "-t", "ext3", "-o", "defaults", spec, "_T_MP"])

    def test_mount_fstab_data_with_uses_options(self):
        """mount_fstab_data mounts with -o options."""
        device = "/dev/xxda1"
        opts = "option1,option2,x=4"
        self._check_mount_fstab_subp(
            block_meta.FstabData(
                device=device, path="/var", fstype="ext3", options=opts),
            ['mount', "-t", "ext3", "-o", opts, device, "_T_MP"])

    @patch('curtin.util.subp')
    def test_mount_fstab_data_does_not_swallow_subp_exception(self, m_subp):
        """verify that subp exception gets raised.

        The implementation there could/should change to raise the
        ProcessExecutionError directly.  Currently raises a RuntimeError."""
        my_error = util.ProcessExecutionError(
            stdout="", stderr="BOOM", exit_code=4)
        m_subp.side_effect = my_error

        mp = self.tmp_path("my-mountpoint")
        with self.assertRaisesRegexp(RuntimeError, r"Mount failed.*"):
            block_meta.mount_fstab_data(
                block_meta.FstabData(device="/dev/disk1", path="/var"),
                target=mp)
        # dir should be created before call to subp failed.
        self.assertTrue(os.path.isdir(mp))


class TestFstabVolumeSpec(CiTestCase):

    DEVLINK_MAP = {
        'bcache': ['/dev/disk/by-uuid/45354276-e0c0-4bf6-9083-f130b89411cc',
                   '/dev/bcache/by-uuid/f36394c0-3cc0-4423-8d6f-ffac130f171a'],
        'crypt': [
            "/dev/disk/by-uuid/bf243cf7-5e45-4d38-b00d-3d35df616ac0",
            "/dev/disk/by-id/dm-name-dmcrypt0 /dev/mapper/dmcrypt0",
            ("/dev/disk/by-id/"
             "dm-uuid-CRYPT-LUKS2-344580c161864ba59712bd84df3e86ba-dmcrypt0")],
        'lvm': [
            "/dev/disk/by-dname/vg1-lv1", "/dev/vg1/lv1"
            "/dev/disk/by-id/dm-name-vg1-lv1", "/dev/mapper/vg1-lv1",
            "/dev/disk/by-uuid/A212-FC0F",
            ("/dev/disk/by-id/dm-uuid-LVM-"
             "qa6NPTq2eJH8eciholQPb2S7nIqpif8G4pn1OeZEDmUUJXdyFdtoIDyUKjZnz")],
        'mpath': [
            "/dev/disk/by-id/dm-name-mpatha-part1", "/dev/mapper/mpatha-part1",
            "/dev/disk/by-id/wwn-0x0000000000000064-part1",
            "/dev/disk/by-id/dm-uuid-part1-mpath-30000000000000064",
            "/dev/disk/by-partuuid/8088175c-362a-4b46-9603-f3595065fa73"],
        'part': [
            "/dev/disk/by-id/ata-WDC_WD40EZRZ-00GXCB0_WD-WCC7K7FHN5U2-part1",
            "/dev/disk/by-id/wwn-0x50014ee20ec2d5b7-part1",
            "/dev/disk/by-label/tank",
            "/dev/disk/by-partlabel/zfs-fa8d6afc7a67405c",
            "/dev/disk/by-partuuid/0b3eae85-960f-fb4f-b5ae-0b3551e763f8",
            "/dev/disk/by-path/pci-0000:00:17.0-ata-1-part1",
            "/dev/disk/by-uuid/14011020183977000633"],
        'raid': [
            "/dev/md/ubuntu-server:0",
            "/dev/disk/by-id/md-name-ubuntu-server:0",
            "/dev/disk/by-id/md-uuid-20078a26:ee6c756b:55e80044:8f6d01b7",
            "/dev/disk/by-uuid/30f91086-7d7c-4f41-994b-a2da5ec4df3a"],
        's390x': [
            "/dev/disk/by-id/scsi-36005076306ffd6b60000000000002406",
            "/dev/disk/by-id/wwn-0x6005076306ffd6b60000000000002406",
            "/dev/disk/by-id/scsi-SIBM_2107900_75DXP712406",
            ("/dev/disk/by-path/" +
             "ccw-0.0.e000-fc-0x50050763060b16b6-lun-0x4024400600000000")],
    }

    def setUp(self):
        super(TestFstabVolumeSpec, self).setUp()
        self.add_patch('curtin.commands.block_meta.udevadm_info', 'm_info')
        self.add_patch(
            'curtin.commands.block_meta._get_volume_type', 'm_vtype')
        self.add_patch('curtin.commands.block_meta.platform.machine', 'm_mach')
        self.m_mach.return_value = 'amd64'

    def test_disks_on_s390x_use_by_path(self):
        block_type = 'disk'
        disk_bypath = (
            "/dev/disk/by-path/" +
            "ccw-0.0.e000-fc-0x50050763060b16b6-lun-0x4024400600000000")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP['s390x'])
        self.m_mach.return_value = 's390x'
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(disk_bypath, block_meta.get_volume_spec(device))

    def test_bcache_uses_dev_bcache_by_uuid(self):
        block_type = 'disk'
        bcache_uuid = (
            "/dev/bcache/by-uuid/f36394c0-3cc0-4423-8d6f-ffac130f171a")
        device = '/dev/bcache' + self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP['bcache'])
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(bcache_uuid, block_meta.get_volume_spec(device))

    def test_raid_device_uses_md_uuid_devlink(self):
        block_type = 'raid'
        md_uuid = ("/dev/disk/by-id/"
                   "md-uuid-20078a26:ee6c756b:55e80044:8f6d01b7")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP['raid'])
        self.m_vtype.return_value = block_type + '1'
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(md_uuid, block_meta.get_volume_spec(device))

    def test_raid_device_uses_devname_if_no_md_uuid_link(self):
        block_type = 'raid'
        md_uuid = ("/dev/disk/by-id/"
                   "md-uuid-20078a26:ee6c756b:55e80044:8f6d01b7")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP['raid'])
        DEVLINKS.remove(md_uuid)
        self.m_vtype.return_value = block_type + '1'
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(device, block_meta.get_volume_spec(device))

    def test_crypt_uses_dm_uuid_devlink(self):
        block_type = 'crypt'
        dm_uuid = (
            "/dev/disk/by-id/"
            "dm-uuid-CRYPT-LUKS2-344580c161864ba59712bd84df3e86ba-dmcrypt0")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(dm_uuid, block_meta.get_volume_spec(device))

    def test_crypt_device_uses_devname_if_no_dm_uuid_link(self):
        block_type = 'crypt'
        dm_uuid = (
            "/dev/disk/by-id/"
            "dm-uuid-CRYPT-LUKS2-344580c161864ba59712bd84df3e86ba-dmcrypt0")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        DEVLINKS.remove(dm_uuid)
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(device, block_meta.get_volume_spec(device))

    def test_lvm_uses_dm_uuid_devlink(self):
        block_type = 'lvm'
        dm_uuid = (
            "/dev/disk/by-id/dm-uuid-LVM-"
            "qa6NPTq2eJH8eciholQPb2S7nIqpif8G4pn1OeZEDmUUJXdyFdtoIDyUKjZnz")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(dm_uuid, block_meta.get_volume_spec(device))

    def test_lvm_device_uses_devname_if_no_dm_uuid_link(self):
        block_type = 'lvm'
        device = self.random_string()
        dm_uuid = (
            "/dev/disk/by-id/dm-uuid-LVM-"
            "qa6NPTq2eJH8eciholQPb2S7nIqpif8G4pn1OeZEDmUUJXdyFdtoIDyUKjZnz")
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        DEVLINKS.remove(dm_uuid)
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(device, block_meta.get_volume_spec(device))

    def test_mpath_uses_dm_uuid_devlink(self):
        block_type = 'mpath'
        dm_uuid = "/dev/disk/by-id/dm-uuid-part1-mpath-30000000000000064"
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(dm_uuid, block_meta.get_volume_spec(device))

    def test_mpath_device_uses_devname_if_no_dm_uuid_link(self):
        block_type = 'mpath'
        dm_uuid = "/dev/disk/by-id/dm-uuid-part1-mpath-30000000000000064"
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        DEVLINKS.remove(dm_uuid)
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(device, block_meta.get_volume_spec(device))

    def test_part_uses_fs_uuid_devlink_if_present(self):
        block_type = 'part'
        fs_uuid = "/dev/disk/by-uuid/14011020183977000633"
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(fs_uuid, block_meta.get_volume_spec(device))

    def test_part_device_uses_part_uuid_if_not_fs_uuid(self):
        block_type = 'part'
        fs_uuid = "/dev/disk/by-uuid/14011020183977000633"
        part_uuid = (
            "/dev/disk/by-partuuid/0b3eae85-960f-fb4f-b5ae-0b3551e763f8")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        DEVLINKS.remove(fs_uuid)
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(part_uuid, block_meta.get_volume_spec(device))

    def test_part_device_uses_devname_if_no_fs_or_part_uuid(self):
        block_type = 'part'
        fs_uuid = "/dev/disk/by-uuid/14011020183977000633"
        part_uuid = (
            "/dev/disk/by-partuuid/0b3eae85-960f-fb4f-b5ae-0b3551e763f8")
        device = self.random_string()
        DEVLINKS = copy.deepcopy(self.DEVLINK_MAP[block_type])
        DEVLINKS.remove(fs_uuid)
        DEVLINKS.remove(part_uuid)
        self.m_vtype.return_value = block_type
        self.m_info.return_value = {'DEVLINKS': DEVLINKS}
        self.assertEqual(device, block_meta.get_volume_spec(device))


class TestDasdHandler(CiTestCase):

    @patch('curtin.commands.block_meta.dasd.DasdDevice.devname')
    @patch('curtin.commands.block_meta.dasd.DasdDevice.format')
    @patch('curtin.commands.block_meta.dasd.DasdDevice.needs_formatting')
    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_dasd_handler_calls_format(self, m_getpath, m_util, m_block,
                                       m_dasd_needf, m_dasd_format,
                                       m_dasd_devname):
        """verify dasd.format is called on disk that differs from config."""
        storage_config = OrderedDict()
        info = {'type': 'dasd', 'id': 'dasd_rootfs', 'device_id': '0.1.24fe',
                'blocksize': 4096, 'disk_layout': 'cdl', 'mode': 'quick',
                'label': 'cloudimg-rootfs'}

        disk_path = "/wark/dasda"
        m_dasd_devname.return_value = disk_path
        m_getpath.return_value = disk_path
        m_dasd_needf.side_effect = [True, False]
        block_meta.dasd_handler(info, storage_config)
        m_dasd_format.assert_called_with(blksize=4096, layout='cdl',
                                         set_label='cloudimg-rootfs',
                                         mode='quick')

    @patch('curtin.commands.block_meta.dasd.DasdDevice.format')
    @patch('curtin.commands.block_meta.dasd.DasdDevice.needs_formatting')
    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_dasd_handler_skips_format_if_not_needed(self, m_getpath, m_util,
                                                     m_block, m_dasd_needf,
                                                     m_dasd_format):
        """verify dasd.format is NOT called if disk matches config."""
        storage_config = OrderedDict()
        info = {'type': 'dasd', 'id': 'dasd_rootfs', 'device_id': '0.1.24fe',
                'blocksize': 4096, 'disk_layout': 'cdl', 'mode': 'quick',
                'label': 'cloudimg-rootfs'}

        disk_path = "/wark/dasda"
        m_getpath.return_value = disk_path
        m_dasd_needf.side_effect = [False, False]
        block_meta.dasd_handler(info, storage_config)
        self.assertEqual(0, m_dasd_format.call_count)

    @patch('curtin.commands.block_meta.dasd.DasdDevice.format')
    @patch('curtin.commands.block_meta.dasd.DasdDevice.needs_formatting')
    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_dasd_handler_preserves_existing_dasd(self, m_getpath, m_util,
                                                  m_block, m_dasd_needf,
                                                  m_dasd_format):
        """verify dasd.format is skipped if preserve is True."""
        storage_config = OrderedDict()
        info = {'type': 'dasd', 'id': 'dasd_rootfs', 'device_id': '0.1.24fe',
                'blocksize': 4096, 'disk_layout': 'cdl', 'mode': 'quick',
                'label': 'cloudimg-rootfs', 'preserve': True}

        disk_path = "/wark/dasda"
        m_getpath.return_value = disk_path
        m_dasd_needf.side_effect = [False, False]
        block_meta.dasd_handler(info, storage_config)
        self.assertEqual(1, m_dasd_needf.call_count)
        self.assertEqual(0, m_dasd_format.call_count)

    @patch('curtin.commands.block_meta.dasd.DasdDevice.format')
    @patch('curtin.commands.block_meta.dasd.DasdDevice.needs_formatting')
    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_dasd_handler_raise_on_preserve_needs_formatting(self, m_getpath,
                                                             m_util, m_block,
                                                             m_dasd_needf,
                                                             m_dasd_format):
        """ValueError raised if preserve is True but dasd needs formatting."""
        storage_config = OrderedDict()
        info = {'type': 'dasd', 'id': 'dasd_rootfs', 'device_id': '0.1.24fe',
                'blocksize': 4096, 'disk_layout': 'cdl', 'mode': 'quick',
                'label': 'cloudimg-rootfs', 'preserve': True}

        disk_path = "/wark/dasda"
        m_getpath.return_value = disk_path
        m_dasd_needf.side_effect = [True, False]
        with self.assertRaises(ValueError):
            block_meta.dasd_handler(info, storage_config)
        self.assertEqual(1, m_dasd_needf.call_count)
        self.assertEqual(0, m_dasd_format.call_count)


class TestDiskHandler(CiTestCase):

    with_logs = True

    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_disk_handler_preserves_known_ptable(self, m_getpath, m_util,
                                                 m_block):
        storage_config = OrderedDict()
        info = {'ptable': 'vtoc', 'serial': 'LX260B',
                'preserve': True, 'name': '', 'grub_device': False,
                'device_id': '0.0.260b', 'type': 'disk', 'id': 'disk-dasda'}

        disk_path = "/wark/dasda"
        m_getpath.return_value = disk_path
        m_block.get_part_table_type.return_value = 'vtoc'
        m_getpath.return_value = disk_path
        block_meta.disk_handler(info, storage_config)
        m_getpath.assert_called_with(info['id'], storage_config)
        m_block.get_part_table_type.assert_called_with(disk_path)

    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_disk_handler_allows_unsupported(self, m_getpath, m_util, m_block):
        storage_config = OrderedDict()
        info = {'ptable': 'unsupported', 'type': 'disk', 'id': 'disk-foobar',
                'preserve': True, 'name': '', 'grub_device': False}

        disk_path = "/wark/foobar"
        m_getpath.return_value = disk_path
        m_block.get_part_table_type.return_value = self.random_string()
        m_getpath.return_value = disk_path
        block_meta.disk_handler(info, storage_config)
        m_getpath.assert_called_with(info['id'], storage_config)
        self.assertEqual(0, m_block.get_part_table_type.call_count)

    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_disk_handler_allows_no_ptable(self, m_getpath, m_util, m_block):
        storage_config = OrderedDict()
        info = {'type': 'disk', 'id': 'disk-foobar',
                'preserve': True, 'name': '', 'grub_device': False}
        self.assertNotIn('ptable', info)
        disk_path = "/wark/foobar"
        m_getpath.return_value = disk_path
        m_block.get_part_table_type.return_value = 'gpt'
        m_getpath.return_value = disk_path
        block_meta.disk_handler(info, storage_config)
        m_getpath.assert_called_with(info['id'], storage_config)
        self.assertEqual(0, m_block.get_part_table_type.call_count)

    @patch('curtin.commands.block_meta.block')
    @patch('curtin.commands.block_meta.util')
    @patch('curtin.commands.block_meta.get_path_to_storage_volume')
    def test_disk_handler_errors_when_reading_current_ptable(self, m_getpath,
                                                             m_util, m_block):
        storage_config = OrderedDict()
        info = {'ptable': 'gpt', 'type': 'disk', 'id': 'disk-foobar',
                'preserve': True, 'name': '', 'grub_device': False}

        disk_path = "/wark/foobar"
        m_getpath.return_value = disk_path
        m_block.get_part_table_type.return_value = None
        m_getpath.return_value = disk_path
        with self.assertRaises(ValueError):
            block_meta.disk_handler(info, storage_config)
        m_getpath.assert_called_with(info['id'], storage_config)
        m_block.get_part_table_type.assert_called_with(disk_path)


class TestLvmVolgroupHandler(CiTestCase):

    def setUp(self):
        super(TestLvmVolgroupHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'lvm', 'm_lvm')
        self.add_patch(basepath + 'util.subp', 'm_subp')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'block.wipe_volume', 'm_wipe')

        self.target = "my_target"
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'id': 'wda2',
                     'type': 'partition'},
                    {'id': 'wdb2',
                     'type': 'partition'},
                    {'id': 'lvm-volgroup1',
                     'type': 'lvm_volgroup',
                     'name': 'vg1',
                     'devices': ['wda2', 'wdb2']},
                    {'id': 'lvm-part1',
                     'type': 'lvm_partition',
                     'name': 'lv1',
                     'size': 1073741824,
                     'volgroup': 'lvm-volgroup1'},
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

    def test_lvmvolgroup_creates_volume_group(self):
        """ lvm_volgroup handler creates volume group. """

        devices = [self.random_string(), self.random_string()]
        self.m_getpath.side_effect = iter(devices)

        block_meta.lvm_volgroup_handler(self.storage_config['lvm-volgroup1'],
                                        self.storage_config)

        self.assertEqual([call(['vgcreate', '--force', '--zero=y', '--yes',
                                'vg1'] + devices,  capture=True)],
                         self.m_subp.call_args_list)
        self.assertEqual(1, self.m_lvm.lvm_scan.call_count)

    @patch('curtin.commands.block_meta.lvm_volgroup_verify')
    def test_lvmvolgroup_preserve_existing_volume_group(self, m_verify):
        """ lvm_volgroup handler preserves existing volume group. """
        m_verify.return_value = True
        devices = [self.random_string(), self.random_string()]
        self.m_getpath.side_effect = iter(devices)

        self.storage_config['lvm-volgroup1']['preserve'] = True
        block_meta.lvm_volgroup_handler(self.storage_config['lvm-volgroup1'],
                                        self.storage_config)

        self.assertEqual(0, self.m_subp.call_count)
        self.assertEqual(1, self.m_lvm.lvm_scan.call_count)

    def test_lvmvolgroup_preserve_verifies_volgroup_members(self):
        """ lvm_volgroup handler preserves existing volume group. """
        devices = [self.random_string(), self.random_string()]
        self.m_getpath.side_effect = iter(devices)
        self.m_lvm.get_pvols_in_volgroup.return_value = devices
        self.storage_config['lvm-volgroup1']['preserve'] = True

        block_meta.lvm_volgroup_handler(self.storage_config['lvm-volgroup1'],
                                        self.storage_config)

        self.assertEqual(1, self.m_lvm.activate_volgroups.call_count)
        self.assertEqual([call('vg1')],
                         self.m_lvm.get_pvols_in_volgroup.call_args_list)
        self.assertEqual(0, self.m_subp.call_count)
        self.assertEqual(1, self.m_lvm.lvm_scan.call_count)

    def test_lvmvolgroup_preserve_raises_exception_wrong_pvs(self):
        """ lvm_volgroup handler preserve raises execption on wrong pv devs."""
        devices = [self.random_string(), self.random_string()]
        self.m_getpath.side_effect = iter(devices)
        self.m_lvm.get_pvols_in_volgroup.return_value = [self.random_string()]
        self.storage_config['lvm-volgroup1']['preserve'] = True

        with self.assertRaises(RuntimeError):
            block_meta.lvm_volgroup_handler(
                self.storage_config['lvm-volgroup1'], self.storage_config)

        self.assertEqual(1, self.m_lvm.activate_volgroups.call_count)
        self.assertEqual([call('vg1')],
                         self.m_lvm.get_pvols_in_volgroup.call_args_list)
        self.assertEqual(0, self.m_subp.call_count)
        self.assertEqual(0, self.m_lvm.lvm_scan.call_count)


class TestLvmPartitionHandler(CiTestCase):

    def setUp(self):
        super(TestLvmPartitionHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'lvm', 'm_lvm')
        self.add_patch(basepath + 'distro', 'm_distro')
        self.add_patch(basepath + 'util.subp', 'm_subp')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'block.wipe_volume', 'm_wipe')

        self.target = "my_target"
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'id': 'lvm-volgroup1',
                     'type': 'lvm_volgroup',
                     'name': 'vg1',
                     'devices': ['wda2', 'wdb2']},
                    {'id': 'lvm-part1',
                     'type': 'lvm_partition',
                     'name': 'lv1',
                     'size': 1073741824,
                     'volgroup': 'lvm-volgroup1'},
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

    def test_lvmpart_accepts_size_as_integer(self):
        """ lvm_partition_handler accepts size as integer. """

        self.m_distro.lsb_release.return_value = {'codename': 'bionic'}
        lv_size = self.storage_config['lvm-part1']['size']
        self.assertEqual(int, type(lv_size))
        expected_size_str = "%sB" % util.human2bytes(lv_size)

        block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                         self.storage_config)

        call_name, call_args, call_kwargs = self.m_subp.mock_calls[0]
        # call_args is an n-tuple of arg list
        self.assertIn(expected_size_str, call_args[0])

    def test_lvmpart_wipes_volume_by_default(self):
        """ lvm_partition_handler wipes superblock by default. """

        self.m_distro.lsb_release.return_value = {'codename': 'bionic'}
        devpath = self.random_string()
        self.m_getpath.return_value = devpath

        block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                         self.storage_config)
        self.m_wipe.assert_called_with(devpath, mode='superblock',
                                       exclusive=False)

    def test_lvmpart_handles_wipe_setting(self):
        """ lvm_partition_handler handles wipe settings. """

        self.m_distro.lsb_release.return_value = {'codename': 'bionic'}
        devpath = self.random_string()
        self.m_getpath.return_value = devpath

        wipe_mode = 'zero'
        self.storage_config['lvm-part1']['wipe'] = wipe_mode
        block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                         self.storage_config)
        self.m_wipe.assert_called_with(devpath, mode=wipe_mode,
                                       exclusive=False)

    @patch('curtin.commands.block_meta.lvm_partition_verify')
    def test_lvmpart_preserve_existing_lvmpart(self, m_verify):
        m_verify.return_value = True
        self.storage_config['lvm-part1']['preserve'] = True
        block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                         self.storage_config)
        self.assertEqual(0, self.m_distro.lsb_release.call_count)
        self.assertEqual(0, self.m_subp.call_count)

    def test_lvmpart_preserve_verifies_lv_in_vg_and_lv_size(self):
        self.storage_config['lvm-part1']['preserve'] = True
        self.m_lvm.get_lvols_in_volgroup.return_value = ['lv1']
        self.m_lvm.get_lv_size_bytes.return_value = 1073741824.0

        block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                         self.storage_config)
        self.assertEqual([call('vg1')],
                         self.m_lvm.get_lvols_in_volgroup.call_args_list)
        self.assertEqual([call('lv1')],
                         self.m_lvm.get_lv_size_bytes.call_args_list)
        self.assertEqual(0, self.m_distro.lsb_release.call_count)
        self.assertEqual(0, self.m_subp.call_count)

    def test_lvmpart_preserve_fails_if_lv_not_in_vg(self):
        self.storage_config['lvm-part1']['preserve'] = True
        self.m_lvm.get_lvols_in_volgroup.return_value = []

        with self.assertRaises(RuntimeError):
            block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                             self.storage_config)

            self.assertEqual([call('vg1')],
                             self.m_lvm.get_lvols_in_volgroup.call_args_list)
        self.assertEqual(0, self.m_lvm.get_lv_size_bytes.call_count)
        self.assertEqual(0, self.m_distro.lsb_release.call_count)
        self.assertEqual(0, self.m_subp.call_count)

    def test_lvmpart_preserve_verifies_lv_size_matches(self):
        self.storage_config['lvm-part1']['preserve'] = True
        self.m_lvm.get_lvols_in_volgroup.return_value = ['lv1']
        self.m_lvm.get_lv_size_bytes.return_value = 0.0

        with self.assertRaises(RuntimeError):
            block_meta.lvm_partition_handler(self.storage_config['lvm-part1'],
                                             self.storage_config)
            self.assertEqual([call('vg1')],
                             self.m_lvm.get_lvols_in_volgroup.call_args_list)
            self.assertEqual([call('lv1')],
                             self.m_lvm.get_lv_size_bytes.call_args_list)
        self.assertEqual(0, self.m_distro.lsb_release.call_count)
        self.assertEqual(0, self.m_subp.call_count)


class TestDmCryptHandler(CiTestCase):

    def setUp(self):
        super(TestDmCryptHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'util.load_command_environment',
                       'm_load_env')
        self.add_patch(basepath + 'util.which', 'm_which')
        self.add_patch(basepath + 'util.subp', 'm_subp')
        self.add_patch(basepath + 'block', 'm_block')

        self.target = "my_target"
        self.keyfile = self.random_string()
        self.cipher = self.random_string()
        self.keysize = self.random_string()
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'grub_device': True,
                     'id': 'sda',
                     'name': 'sda',
                     'path': '/wark/xxx',
                     'ptable': 'msdos',
                     'type': 'disk',
                     'wipe': 'superblock'},
                    {'device': 'sda',
                     'id': 'sda-part1',
                     'name': 'sda-part1',
                     'number': 1,
                     'size': '511705088B',
                     'type': 'partition'},
                    {'id': 'dmcrypt0',
                     'type': 'dm_crypt',
                     'dm_name': 'cryptroot',
                     'volume': 'sda-part1',
                     'cipher': self.cipher,
                     'keysize': self.keysize,
                     'keyfile': self.keyfile},
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))
        self.m_block.zkey_supported.return_value = False
        self.m_which.return_value = False
        self.fstab = self.tmp_path('fstab')
        self.crypttab = os.path.join(os.path.dirname(self.fstab), 'crypttab')
        self.m_load_env.return_value = {'fstab': self.fstab,
                                        'target': self.target}

    def test_dm_crypt_calls_cryptsetup(self):
        """ verify dm_crypt calls (format, open) w/ correct params"""
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path

        info = self.storage_config['dmcrypt0']
        block_meta.dm_crypt_handler(info, self.storage_config)
        expected_calls = [
            call(['cryptsetup', '--cipher', self.cipher,
                  '--key-size', self.keysize,
                  'luksFormat', volume_path, self.keyfile]),
            call(['cryptsetup', 'open', '--type', 'luks', volume_path,
                  info['dm_name'], '--key-file', self.keyfile])
        ]
        self.m_subp.assert_has_calls(expected_calls)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    def test_dm_crypt_defaults_dm_name_to_id(self):
        """ verify dm_crypt_handler falls back to id with no dm_name. """
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        info = self.storage_config['dmcrypt0']
        del info['dm_name']

        block_meta.dm_crypt_handler(info, self.storage_config)
        expected_calls = [
            call(['cryptsetup', '--cipher', self.cipher,
                  '--key-size', self.keysize,
                  'luksFormat', volume_path, self.keyfile]),
            call(['cryptsetup', 'open', '--type', 'luks', volume_path,
                  info['id'], '--key-file', self.keyfile])
        ]
        self.m_subp.assert_has_calls(expected_calls)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    def test_dm_crypt_zkey_cryptsetup(self):
        """ verify dm_crypt zkey calls generates and run before crypt open."""

        # zkey binary is present
        self.m_block.zkey_supported.return_value = True
        self.m_which.return_value = "/my/path/to/zkey"
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        volume_byid = "/dev/disk/by-id/ccw-%s" % volume_path
        self.m_block.disk_to_byid_path.return_value = volume_byid

        info = self.storage_config['dmcrypt0']
        volume_name = "%s:%s" % (volume_byid, info['dm_name'])
        block_meta.dm_crypt_handler(info, self.storage_config)
        expected_calls = [
            call(['zkey', 'generate', '--xts', '--volume-type', 'luks2',
                  '--sector-size', '4096', '--name', info['dm_name'],
                  '--description',
                  'curtin generated zkey for %s' % volume_name,
                  '--volumes', volume_name], capture=True),
            call(['zkey', 'cryptsetup', '--run', '--volumes', volume_byid,
                  '--batch-mode', '--key-file', self.keyfile], capture=True),
            call(['cryptsetup', 'open', '--type', 'luks2', volume_path,
                  info['dm_name'], '--key-file', self.keyfile]),
        ]
        self.m_subp.assert_has_calls(expected_calls)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    def test_dm_crypt_zkey_gen_failure_fallback_to_cryptsetup(self):
        """ verify dm_cyrpt zkey generate err falls back cryptsetup format. """

        # zkey binary is present
        self.m_block.zkey_supported.return_value = True
        self.m_which.return_value = "/my/path/to/zkey"

        self.m_subp.side_effect = iter([
            util.ProcessExecutionError("foobar"),  # zkey generate
            (0, 0),  # cryptsetup luksFormat
            (0, 0),  # cryptsetup open
        ])

        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        volume_byid = "/dev/disk/by-id/ccw-%s" % volume_path
        self.m_block.disk_to_byid_path.return_value = volume_byid

        info = self.storage_config['dmcrypt0']
        volume_name = "%s:%s" % (volume_byid, info['dm_name'])
        block_meta.dm_crypt_handler(info, self.storage_config)
        expected_calls = [
            call(['zkey', 'generate', '--xts', '--volume-type', 'luks2',
                  '--sector-size', '4096', '--name', info['dm_name'],
                  '--description',
                  'curtin generated zkey for %s' % volume_name,
                  '--volumes', volume_name], capture=True),
            call(['cryptsetup', '--cipher', self.cipher,
                  '--key-size', self.keysize,
                  'luksFormat', volume_path, self.keyfile]),
            call(['cryptsetup', 'open', '--type', 'luks', volume_path,
                  info['dm_name'], '--key-file', self.keyfile])
        ]
        self.m_subp.assert_has_calls(expected_calls)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    def test_dm_crypt_zkey_run_failure_fallback_to_cryptsetup(self):
        """ verify dm_cyrpt zkey run err falls back on cryptsetup format. """

        # zkey binary is present
        self.m_block.zkey_supported.return_value = True
        self.m_which.return_value = "/my/path/to/zkey"

        self.m_subp.side_effect = iter([
            (0, 0),  # zkey generate
            util.ProcessExecutionError("foobar"),  # zkey cryptsetup --run
            (0, 0),  # cryptsetup luksFormat
            (0, 0),  # cryptsetup open
        ])

        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        volume_byid = "/dev/disk/by-id/ccw-%s" % volume_path
        self.m_block.disk_to_byid_path.return_value = volume_byid

        info = self.storage_config['dmcrypt0']
        volume_name = "%s:%s" % (volume_byid, info['dm_name'])
        block_meta.dm_crypt_handler(info, self.storage_config)
        expected_calls = [
            call(['zkey', 'generate', '--xts', '--volume-type', 'luks2',
                  '--sector-size', '4096', '--name', info['dm_name'],
                  '--description',
                  'curtin generated zkey for %s' % volume_name,
                  '--volumes', volume_name], capture=True),
            call(['zkey', 'cryptsetup', '--run', '--volumes', volume_byid,
                  '--batch-mode', '--key-file', self.keyfile], capture=True),
            call(['cryptsetup', '--cipher', self.cipher,
                  '--key-size', self.keysize,
                  'luksFormat', volume_path, self.keyfile]),
            call(['cryptsetup', 'open', '--type', 'luks', volume_path,
                  info['dm_name'], '--key-file', self.keyfile])
        ]
        self.m_subp.assert_has_calls(expected_calls)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    @patch('curtin.commands.block_meta.dm_crypt_verify')
    def test_dm_crypt_preserves_existing(self, m_verify):
        """ verify dm_crypt preserves existing device. """
        m_verify.return_value = True
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path

        info = self.storage_config['dmcrypt0']
        info['preserve'] = True
        block_meta.dm_crypt_handler(info, self.storage_config)

        self.assertEqual(0, self.m_subp.call_count)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    @patch('curtin.commands.block_meta.os.path.exists')
    def test_dm_crypt_preserve_verifies_correct_device_is_present(self, m_ex):
        """ verify dm_crypt preserve verifies correct dev is used. """
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        self.m_block.dmsetup_info.return_value = {
            'blkdevname': 'dm-0',
            'blkdevs_used': volume_path,
            'name': 'cryptroot',
            'uuid': self.random_string(),
            'subsystem': 'crypt'
        }
        m_ex.return_value = True

        info = self.storage_config['dmcrypt0']
        info['preserve'] = True
        block_meta.dm_crypt_handler(info, self.storage_config)
        self.assertEqual(len(util.load_file(self.crypttab).splitlines()), 1)

    @patch('curtin.commands.block_meta.os.path.exists')
    def test_dm_crypt_preserve_raises_exception_if_not_present(self, m_ex):
        """ verify dm_crypt raises exception if dm device not present. """
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        m_ex.return_value = False
        info = self.storage_config['dmcrypt0']
        info['preserve'] = True
        with self.assertRaises(RuntimeError):
            block_meta.dm_crypt_handler(info, self.storage_config)

    @patch('curtin.commands.block_meta.os.path.exists')
    def test_dm_crypt_preserve_raises_exception_if_wrong_dev_used(self, m_ex):
        """ verify dm_crypt preserve raises exception on wrong dev used. """
        volume_path = self.random_string()
        self.m_getpath.return_value = volume_path
        self.m_block.dmsetup_info.return_value = {
            'blkdevname': 'dm-0',
            'blkdevs_used': self.random_string(),
            'name': 'cryptroot',
            'uuid': self.random_string(),
            'subsystem': 'crypt'
        }
        m_ex.return_value = True
        info = self.storage_config['dmcrypt0']
        info['preserve'] = True
        with self.assertRaises(RuntimeError):
            block_meta.dm_crypt_handler(info, self.storage_config)


class TestRaidHandler(CiTestCase):

    def setUp(self):
        super(TestRaidHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'util', 'm_util')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'mdadm', 'm_mdadm')
        self.add_patch(basepath + 'block', 'm_block')
        self.add_patch(basepath + 'udevadm_settle', 'm_uset')

        self.target = "my_target"
        self.config = {
            'storage': {
                 'version': 1,
                 'config': [
                        {'grub_device': 1,
                         'id': 'sda',
                         'model': 'QEMU HARDDISK',
                         'name': 'main_disk',
                         'ptable': 'gpt',
                         'serial': 'disk-a',
                         'type': 'disk',
                         'wipe': 'superblock'},
                        {'device': 'sda',
                         'flag': 'bios_grub',
                         'id': 'bios_boot_partition',
                         'size': '1MB',
                         'type': 'partition'},
                        {'device': 'sda',
                         'id': 'sda1',
                         'size': '3GB',
                         'type': 'partition'},
                        {'id': 'sdb',
                         'model': 'QEMU HARDDISK',
                         'name': 'second_disk',
                         'ptable': 'gpt',
                         'serial': 'disk-b',
                         'type': 'disk',
                         'wipe': 'superblock'},
                        {'device': 'sdb',
                         'id': 'sdb1',
                         'size': '3GB',
                         'type': 'partition'},
                        {'id': 'sdc',
                         'model': 'QEMU HARDDISK',
                         'name': 'third_disk',
                         'ptable': 'gpt',
                         'serial': 'disk-c',
                         'type': 'disk',
                         'wipe': 'superblock'},
                        {'device': 'sdc',
                         'id': 'sdc1',
                         'size': '3GB',
                         'type': 'partition'},
                        {'devices': ['sda1', 'sdb1', 'sdc1'],
                         'id': 'mddevice',
                         'name': 'md0',
                         'raidlevel': 5,
                         'type': 'raid'},
                        {'fstype': 'ext4',
                         'id': 'md_root',
                         'type': 'format',
                         'volume': 'mddevice'},
                        {'device': 'md_root',
                         'id': 'md_mount',
                         'path': '/',
                         'type': 'mount'}],
            },
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))
        self.m_util.load_command_environment.return_value = {'fstab': None}

    def test_raid_handler(self):
        """ raid_handler creates raid device. """
        devices = [self.random_string(), self.random_string(),
                   self.random_string()]
        md_devname = '/dev/' + self.storage_config['mddevice']['name']
        self.m_block.dev_path.return_value = '/dev/md0'
        self.m_getpath.side_effect = iter(devices)
        block_meta.raid_handler(self.storage_config['mddevice'],
                                self.storage_config)
        self.assertEqual([call(md_devname, 5, devices, [], '')],
                         self.m_mdadm.mdadm_create.call_args_list)

    @patch('curtin.commands.block_meta.raid_verify')
    def test_raid_handler_preserves_existing_device(self, m_verify):
        """ raid_handler preserves existing device. """

        devices = [self.random_string(), self.random_string(),
                   self.random_string()]
        self.m_block.dev_path.return_value = '/dev/md0'
        self.m_getpath.side_effect = iter(devices)
        m_verify.return_value = True
        self.storage_config['mddevice']['preserve'] = True
        block_meta.raid_handler(self.storage_config['mddevice'],
                                self.storage_config)
        self.assertEqual(0, self.m_mdadm.mdadm_create.call_count)

    def test_raid_handler_preserve_verifies_md_device(self):
        """ raid_handler preserve verifies existing raid device. """

        devices = [self.random_string(), self.random_string(),
                   self.random_string()]
        md_devname = '/dev/' + self.storage_config['mddevice']['name']
        self.m_block.dev_path.return_value = '/dev/md0'
        self.m_getpath.side_effect = iter(devices)
        self.m_mdadm.md_check.return_value = True
        self.storage_config['mddevice']['preserve'] = True
        block_meta.raid_handler(self.storage_config['mddevice'],
                                self.storage_config)
        self.assertEqual(0, self.m_mdadm.mdadm_create.call_count)
        self.assertEqual([call(md_devname, 5, devices, [])],
                         self.m_mdadm.md_check.call_args_list)

    def test_raid_handler_preserve_verifies_md_device_after_assemble(self):
        """ raid_handler preserve assembles array if first check fails. """

        devices = [self.random_string(), self.random_string(),
                   self.random_string()]
        md_devname = '/dev/' + self.storage_config['mddevice']['name']
        self.m_block.dev_path.return_value = '/dev/md0'
        self.m_getpath.side_effect = iter(devices)
        self.m_mdadm.md_check.side_effect = iter([False, True])
        self.storage_config['mddevice']['preserve'] = True
        block_meta.raid_handler(self.storage_config['mddevice'],
                                self.storage_config)
        self.assertEqual(0, self.m_mdadm.mdadm_create.call_count)
        self.assertEqual([call(md_devname, 5, devices, [])] * 2,
                         self.m_mdadm.md_check.call_args_list)
        self.assertEqual([call(md_devname, devices, [])],
                         self.m_mdadm.mdadm_assemble.call_args_list)

    def test_raid_handler_preserve_raises_exception_if_verify_fails(self):
        """ raid_handler preserve raises exception on failed verification."""

        devices = [self.random_string(), self.random_string(),
                   self.random_string()]
        md_devname = '/dev/' + self.storage_config['mddevice']['name']
        self.m_block.dev_path.return_value = '/dev/md0'
        self.m_getpath.side_effect = iter(devices)
        self.m_mdadm.md_check.side_effect = iter([False, False])
        self.storage_config['mddevice']['preserve'] = True
        with self.assertRaises(RuntimeError):
            block_meta.raid_handler(self.storage_config['mddevice'],
                                    self.storage_config)
        self.assertEqual(0, self.m_mdadm.mdadm_create.call_count)
        self.assertEqual([call(md_devname, 5, devices, [])] * 2,
                         self.m_mdadm.md_check.call_args_list)
        self.assertEqual([call(md_devname, devices, [])],
                         self.m_mdadm.mdadm_assemble.call_args_list)


class TestBcacheHandler(CiTestCase):

    def setUp(self):
        super(TestBcacheHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'util', 'm_util')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'bcache', 'm_bcache')
        self.add_patch(basepath + 'block', 'm_block')
        self.add_patch(basepath + 'disk_handler', 'm_disk_handler')

        self.target = "my_target"
        self.config = {
            'storage': {
                 'version': 1,
                 'config': [
                    {'grub_device': True,
                     'id': 'id_rotary0',
                     'name': 'rotary0',
                     'ptable': 'msdos',
                     'serial': 'disk-a',
                     'type': 'disk',
                     'wipe': 'superblock'},
                    {'id': 'id_ssd0',
                     'name': 'ssd0',
                     'serial': 'disk-b',
                     'type': 'disk',
                     'wipe': 'superblock'},
                    {'device': 'id_rotary0',
                     'id': 'id_rotary0_part1',
                     'name': 'rotary0-part1',
                     'number': 1,
                     'offset': '1M',
                     'size': '999M',
                     'type': 'partition',
                     'wipe': 'superblock'},
                    {'device': 'id_rotary0',
                     'id': 'id_rotary0_part2',
                     'name': 'rotary0-part2',
                     'number': 2,
                     'size': '9G',
                     'type': 'partition',
                     'wipe': 'superblock'},
                    {'backing_device': 'id_rotary0_part2',
                     'cache_device': 'id_ssd0',
                     'cache_mode': 'writeback',
                     'id': 'id_bcache0',
                     'name': 'bcache0',
                     'type': 'bcache'},
                    {'fstype': 'ext4',
                     'id': 'bootfs',
                     'label': 'boot-fs',
                     'type': 'format',
                     'volume': 'id_rotary0_part1'},
                    {'fstype': 'ext4',
                     'id': 'rootfs',
                     'label': 'root-fs',
                     'type': 'format',
                     'volume': 'id_bcache0'},
                    {'device': 'rootfs',
                     'id': 'rootfs_mount',
                     'path': '/',
                     'type': 'mount'},
                    {'device': 'bootfs',
                     'id': 'bootfs_mount',
                     'path': '/boot',
                     'type': 'mount'}
                 ],
            },
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

    def test_bcache_handler(self):
        """ bcache_handler creates bcache device. """
        backing_device = self.random_string()
        caching_device = self.random_string()
        cset_uuid = self.random_string()
        cache_mode = self.storage_config['id_bcache0']['cache_mode']
        self.m_getpath.side_effect = iter([backing_device, caching_device])
        self.m_bcache.create_cache_device.return_value = cset_uuid

        block_meta.bcache_handler(self.storage_config['id_bcache0'],
                                  self.storage_config)
        self.assertEqual([call(caching_device)],
                         self.m_bcache.create_cache_device.call_args_list)
        self.assertEqual([
            call(backing_device, caching_device, cache_mode, cset_uuid)],
                         self.m_bcache.create_backing_device.call_args_list)


class TestPartitionHandler(CiTestCase):

    def setUp(self):
        super(TestPartitionHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'util', 'm_util')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'block', 'm_block')
        self.add_patch(basepath + 'multipath', 'm_mp')
        self.add_patch(basepath + 'udevadm_settle', 'm_uset')
        self.add_patch(basepath + 'udevadm_info', 'm_uinfo')

        self.target = "my_target"
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'id': 'sda',
                     'type': 'disk',
                     'name': 'main_disk',
                     'ptable': 'msdos',
                     'serial': 'disk-a'},
                    {'id': 'disk-sda-part-1',
                     'type': 'partition',
                     'device': 'sda',
                     'name': 'main_part',
                     'number': 1,
                     'size': '3GB',
                     'flag': 'boot'},
                    {'id': 'disk-sda-part-2',
                     'type': 'partition',
                     'device': 'sda',
                     'name': 'extended_part',
                     'number': 2,
                     'size': '5GB',
                     'flag': 'extended'},
                    {'id': 'disk-sda-part-5',
                     'type': 'partition',
                     'device': 'sda',
                     'name': 'logical_part',
                     'number': 5,
                     'size': '2GB',
                     'flag': 'logical'},
                    {'id': 'disk-sda-part-6',
                     'type': 'partition',
                     'device': 'sda',
                     'name': 'logical_part',
                     'number': 6,
                     'size': '2GB',
                     'flag': 'logical'},
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

    def test_find_extended_partition(self):
        """
        find_extended_partition returns extended part_id of logical partition.
        """
        extended_parts = [item for item_id, item in self.storage_config.items()
                          if item['type'] == 'partition' and
                          item.get('flag') == 'extended']
        self.assertEqual(1, len(extended_parts))
        extended_part = extended_parts[0]
        logical_parts = [item for item_id, item in self.storage_config.items()
                         if item['type'] == 'partition' and
                         item.get('flag') == 'logical']

        for logical in logical_parts:
            ext_part_id = (
                block_meta.find_extended_partition(logical['device'],
                                                   self.storage_config))
            self.assertEqual(extended_part['id'], ext_part_id)

    def test_find_extended_partition_returns_none_if_not_found(self):
        """
        find_extended_partition returns none if no extended part is found.
        """

        del self.storage_config['disk-sda-part-2']['flag']
        logical_parts = [item for item_id, item in self.storage_config.items()
                         if item['type'] == 'partition' and
                         item.get('flag') == 'logical']

        for logical in logical_parts:
            ext_part_id = (
                block_meta.find_extended_partition(logical['device'],
                                                   self.storage_config))
            self.assertIsNone(ext_part_id)

    @patch('curtin.commands.block_meta.find_extended_partition')
    def test_part_handler_finds_extended_part_for_logical_part_5(self,
                                                                 m_ex_part):
        """
        part_handler_finds_extended_part_number_for_logical_part_5.
        """
        extended_parts = [item for item_id, item in self.storage_config.items()
                          if item['type'] == 'partition' and
                          item.get('flag') == 'extended']
        self.assertEqual(1, len(extended_parts))
        logical_parts = [item for item_id, item in self.storage_config.items()
                         if item['type'] == 'partition' and
                         item.get('number') == 5]
        self.assertEqual(1, len(logical_parts))
        logical_part = logical_parts[0]

        self.m_getpath.return_value = '/wark/sda'
        self.m_block.path_to_kname.return_value = 'sda'
        self.m_block.partition_kname.return_value = 'sda2'
        self.m_block.sys_block_path.return_value = 'sys/class/block/sda'
        self.m_block.get_blockdev_sector_size.return_value = (512, 512)
        m_ex_part.return_value = 'disk-sda-part-2'
        block_meta.partition_handler(logical_part, self.storage_config)
        m_ex_part.assert_called_with('sda', self.storage_config)

    def test_part_handler_raise_exception_missing_extended_part(self):
        """
        part_handler raises exception on missing extended partition.
        """
        del self.storage_config['disk-sda-part-2']['flag']
        logical_parts = [item for item_id, item in self.storage_config.items()
                         if item['type'] == 'partition' and
                         item.get('number') == 5]
        self.assertEqual(1, len(logical_parts))
        logical_part = logical_parts[0]

        self.m_getpath.return_value = '/wark/sda'
        self.m_block.path_to_kname.return_value = 'sda'
        self.m_block.partition_kname.return_value = 'sda2'
        self.m_block.sys_block_path.return_value = 'sys/class/block/sda'
        self.m_block.get_blockdev_sector_size.return_value = (512, 512)
        with self.assertRaises(RuntimeError):
            block_meta.partition_handler(logical_part, self.storage_config)


class TestMultipathPartitionHandler(CiTestCase):

    def setUp(self):
        super(TestMultipathPartitionHandler, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'm_getpath')
        self.add_patch(basepath + 'util', 'm_util')
        self.add_patch(basepath + 'make_dname', 'm_dname')
        self.add_patch(basepath + 'block', 'm_block')
        self.add_patch(basepath + 'multipath', 'm_mp')
        self.add_patch(basepath + 'udevadm_settle', 'm_uset')
        self.add_patch(basepath + 'udevadm_info', 'm_uinfo')

        self.target = self.tmp_dir()
        self.config = {
            'storage': {
                'version': 1,
                'config': [
                    {'id': 'sda',
                     'type': 'disk',
                     'name': 'main_disk',
                     'ptable': 'gpt',
                     'serial': 'disk-a'},
                    {'id': 'disk-sda-part-1',
                     'type': 'partition',
                     'device': 'sda',
                     'name': 'bios_boot',
                     'number': 1,
                     'size': '1M',
                     'flag': 'bios_grub'},
                    {'id': 'disk-sda-part-2',
                     'type': 'partition',
                     'device': 'sda',
                     'number': 2,
                     'size': '5GB'},
                ],
            }
        }
        self.storage_config = (
            block_meta.extract_storage_ordered_dict(self.config))

    @patch('curtin.commands.block_meta.calc_partition_info')
    def test_part_handler_uses_kpartx_on_multipath_parts(self, m_part_info):

        # dm-0 is mpatha, dm-1 is mpatha-part1, dm-2 is mpatha-part2
        disk_path = '/wark/mapper/mpatha'
        self.m_getpath.return_value = disk_path
        self.m_block.path_to_kname.return_value = 'dm-0'
        self.m_block.sys_block_path.return_value = 'sys/class/block/dm-0'
        self.m_block.get_blockdev_sector_size.return_value = (512, 512)
        self.m_block.partition_kname.return_value = 'dm-2'
        self.m_mp.is_mpath_device.return_value = True

        # prev_start_sec, prev_size_sec
        m_part_info.return_value = (2048, 2048)

        part2 = self.storage_config['disk-sda-part-2']
        block_meta.partition_handler(part2, self.storage_config)

        expected_calls = [
            call(['sgdisk', '--new', '2:4096:4096', '--typecode=2:8300',
                  disk_path], capture=True),
            call(['kpartx', '-v', '-a', '-s', '-p', '-part', disk_path]),
        ]
        self.assertEqual(expected_calls, self.m_util.subp.call_args_list)

    @patch('curtin.commands.block_meta.os.path')
    @patch('curtin.commands.block_meta.calc_partition_info')
    def test_part_handler_deleted__non_symlink_before_kpartx(self,
                                                             m_part_info,
                                                             m_os_path):
        # dm-0 is mpatha, dm-1 is mpatha-part1, dm-2 is mpatha-part2
        disk_path = '/wark/mapper/mpatha'
        self.m_getpath.return_value = disk_path
        self.m_block.path_to_kname.return_value = 'dm-0'
        self.m_block.sys_block_path.return_value = 'sys/class/block/dm-0'
        self.m_block.get_blockdev_sector_size.return_value = (512, 512)
        self.m_block.partition_kname.return_value = 'dm-2'
        self.m_mp.is_mpath_device.return_value = True
        m_os_path.exists.return_value = True
        m_os_path.islink.return_value = False

        # prev_start_sec, prev_size_sec
        m_part_info.return_value = (2048, 2048)

        part2 = self.storage_config['disk-sda-part-2']
        block_meta.partition_handler(part2, self.storage_config)

        expected_calls = [
            call(['sgdisk', '--new', '2:4096:4096', '--typecode=2:8300',
                  disk_path], capture=True),
            call(['kpartx', '-v', '-a', '-s', '-p', '-part', disk_path]),
        ]
        self.assertEqual(expected_calls, self.m_util.subp.call_args_list)
        self.assertEqual([call(disk_path + '-part2')],
                         self.m_util.del_file.call_args_list)


class TestCalcPartitionInfo(CiTestCase):

    def setUp(self):
        super(TestCalcPartitionInfo, self).setUp()
        self.add_patch('curtin.commands.block_meta.util.load_file',
                       'm_load_file')

    def _prepare_load_file_mocks(self, start, size, logsize):
        partition_size = str(int(size / logsize))
        partition_start = str(int(start / logsize))
        self.m_load_file.side_effect = iter([partition_size, partition_start])

    def test_calc_partition_info(self):
        disk = self.random_string()
        partition = self.random_string()
        part_path = os.path.join(disk, partition)
        part_size = 10 * 1024 * 1024
        part_start = 1 * 1024 * 1024
        blk_size = 512
        self._prepare_load_file_mocks(part_start, part_size, blk_size)

        (start, size) = block_meta.calc_partition_info(
            disk, partition, blk_size)

        self.assertEqual(part_start / blk_size, start)
        self.assertEqual(part_size / blk_size, size)
        self.assertEqual(
            [call(part_path + '/size'), call(part_path + '/start')],
            self.m_load_file.call_args_list)

    @patch('curtin.commands.block_meta.calc_dm_partition_info')
    def test_calc_partition_info_dm_part(self, m_calc_dm):
        disk = self.random_string()
        partition = 'dm-237'
        part_size = 10 * 1024 * 1024
        part_start = 1 * 1024 * 1024
        blk_size = 512
        m_calc_dm.return_value = (part_start / blk_size, part_size / blk_size)

        (start, size) = block_meta.calc_partition_info(
            disk, partition, blk_size)

        self.assertEqual(part_start / blk_size, start)
        self.assertEqual(part_size / blk_size, size)
        self.assertEqual([call(partition)], m_calc_dm.call_args_list)
        self.assertEqual([], self.m_load_file.call_args_list)

    @patch('curtin.commands.block_meta.calc_dm_partition_info')
    def test_calc_partition_info_none_start_sec_raise_exc(self, m_calc_dm):
        disk = self.random_string()
        partition = 'dm-237'
        blk_size = 512
        m_calc_dm.return_value = (None, None)

        with self.assertRaises(RuntimeError):
            block_meta.calc_partition_info(disk, partition, blk_size)

        self.assertEqual([call(partition)], m_calc_dm.call_args_list)
        self.assertEqual([], self.m_load_file.call_args_list)


class TestCalcDMPartitionInfo(CiTestCase):

    def setUp(self):
        super(TestCalcDMPartitionInfo, self).setUp()
        self.add_patch('curtin.commands.block_meta.multipath', 'm_mp')
        self.add_patch('curtin.commands.block_meta.util.subp', 'm_subp')

        self.mpath_id = 'mpath%s-part1' % self.random_string(length=1)
        self.m_mp.get_mpath_id_from_device.return_value = self.mpath_id

    def test_calc_dm_partition_info_raises_exc_no_mpath_id(self):
        self.m_mp.get_mpath_id_from_device.return_value = None
        with self.assertRaises(RuntimeError):
            block_meta.calc_dm_partition_info(self.random_string())

    def test_calc_dm_partition_info_return_none_with_no_dmsetup_output(self):
        self.m_subp.return_value = ("", "")
        self.assertEqual(
            (None, None),
            block_meta.calc_dm_partition_info(self.random_string()))

    def test_calc_dm_partition_info_calls_dmsetup_table(self):
        partition = 'dm-245'
        dm_part = '/dev/' + partition
        self.m_subp.return_value = ("0 20480 linear 253:0 2048", "")
        (start, size) = block_meta.calc_dm_partition_info(partition)
        self.assertEqual(2048, start)
        self.assertEqual(20480, size)
        self.assertEqual(
            [call(dm_part)],
            self.m_mp.get_mpath_id_from_device.call_args_list)
        self.assertEqual([
            call(['dmsetup', 'table', '--target', 'linear', self.mpath_id],
                 capture=True)],
            self.m_subp.call_args_list)


class TestPartitionVerify(CiTestCase):

    def setUp(self):
        super(TestPartitionVerify, self).setUp()
        base = 'curtin.commands.block_meta.'
        self.add_patch(base + 'verify_exists', 'm_verify_exists')
        self.add_patch(base + 'block.sfdisk_info', 'm_block_sfdisk_info')
        self.add_patch(base + 'verify_size', 'm_verify_size')
        self.add_patch(base + 'verify_ptable_flag', 'm_verify_ptable_flag')
        self.info = {
            'id': 'disk-sda-part-2',
            'type': 'partition',
            'device': 'sda',
            'number': 2,
            'size': '5GB',
            'flag': 'boot',
        }
        self.part_size = int(util.human2bytes(self.info['size']))
        self.devpath = self.random_string()

    def test_partition_verify(self):
        block_meta.partition_verify(self.devpath, self.info)
        self.assertEqual(
            [call(self.devpath)],
            self.m_verify_exists.call_args_list)
        self.assertEqual(
            [call(self.devpath)],
            self.m_block_sfdisk_info.call_args_list)
        self.assertEqual(
            [call(self.devpath, self.part_size,
                  sfdisk_info=self.m_block_sfdisk_info.return_value)],
            self.m_verify_size.call_args_list)
        self.assertEqual(
            [call(self.devpath, self.info['flag'],
                  sfdisk_info=self.m_block_sfdisk_info.return_value)],
            self.m_verify_ptable_flag.call_args_list)

    def test_partition_verify_skips_ptable_no_flag(self):
        del self.info['flag']
        block_meta.partition_verify(self.devpath, self.info)
        self.assertEqual(
            [call(self.devpath)],
            self.m_verify_exists.call_args_list)
        self.assertEqual(
            [call(self.devpath)],
            self.m_block_sfdisk_info.call_args_list)
        self.assertEqual(
            [call(self.devpath, self.part_size,
                  sfdisk_info=self.m_block_sfdisk_info.return_value)],
            self.m_verify_size.call_args_list)
        self.assertEqual([], self.m_verify_ptable_flag.call_args_list)


class TestVerifyExists(CiTestCase):

    def setUp(self):
        super(TestVerifyExists, self).setUp()
        base = 'curtin.commands.block_meta.'
        self.add_patch(base + 'os.path.exists', 'm_exists')
        self.devpath = self.random_string()
        self.m_exists.return_value = True

    def test_verify_exists(self):
        block_meta.verify_exists(self.devpath)
        self.assertEqual(
            [call(self.devpath)],
            self.m_exists.call_args_list)

    def test_verify_exists_raise_runtime_exc_if_path_not_exist(self):
        self.m_exists.return_value = False
        with self.assertRaises(RuntimeError):
            block_meta.verify_exists(self.devpath)
        self.assertEqual(
            [call(self.devpath)],
            self.m_exists.call_args_list)


class TestVerifySize(CiTestCase):

    def setUp(self):
        super(TestVerifySize, self).setUp()
        base = 'curtin.commands.block_meta.'
        self.add_patch(base + 'block.sfdisk_info', 'm_block_sfdisk_info')
        self.add_patch(base + 'block.get_partition_sfdisk_info',
                       'm_block_get_partition_sfdisk_info')
        self.devpath = self.random_string()


class TestVerifyPtableFlag(CiTestCase):

    def setUp(self):
        super(TestVerifyPtableFlag, self).setUp()
        base = 'curtin.commands.block_meta.'
        self.add_patch(base + 'block.sfdisk_info', 'm_block_sfdisk_info')
        self.add_patch(base + 'block.get_blockdev_for_partition',
                       'm_block_get_blockdev_for_partition')
        self.sfdisk_info_dos = {
            "label": "dos",
            "id": "0xb0dbdde1",
            "device": "/dev/vdb",
            "unit": "sectors",
            "partitions": [
               {"node": "/dev/vdb1", "start": 2048, "size": 8388608,
                "type": "83", "bootable": True},
               {"node": "/dev/vdb2", "start": 8390656, "size": 8388608,
                "type": "83"},
               {"node": "/dev/vdb3", "start": 16779264, "size": 62914560,
                "type": "85"},
               {"node": "/dev/vdb5", "start": 16781312, "size": 31457280,
                "type": "83"},
               {"node": "/dev/vdb6", "start": 48240640, "size": 10485760,
                "type": "83"},
               {"node": "/dev/vdb7", "start": 58728448, "size": 20965376,
                "type": "83"}]}
        self.sfdisk_info_gpt = {
            "label": "gpt",
            "id": "AEA37E20-8E52-4B37-BDFD-9946A352A37B",
            "device": "/dev/vda",
            "unit": "sectors",
            "firstlba": 34,
            "lastlba": 41943006,
            "partitions": [
               {"node": "/dev/vda1", "start": 227328, "size": 41715679,
                "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "uuid": "42C72DE9-FF5E-4CD6-A4C8-283685DEB1D5"},
               {"node": "/dev/vda14", "start": 2048, "size": 8192,
                "type": "21686148-6449-6E6F-744E-656564454649",
                "uuid": "762F070A-122A-4EB8-90BF-2CA6E9171B01"},
               {"node": "/dev/vda15", "start": 10240, "size": 217088,
                "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                "uuid": "789133C6-8579-4792-9D61-FC9A7BEC2A15"}]}

    def test_verify_ptable_flag_finds_boot_on_gpt(self):
        devpath = '/dev/vda15'
        expected_flag = 'boot'
        block_meta.verify_ptable_flag(devpath, expected_flag,
                                      sfdisk_info=self.sfdisk_info_gpt)

    def test_verify_ptable_flag_raises_exception_missing_flag(self):
        devpath = '/dev/vda1'
        expected_flag = 'boot'
        with self.assertRaises(RuntimeError):
            block_meta.verify_ptable_flag(devpath, expected_flag,
                                          sfdisk_info=self.sfdisk_info_gpt)

    def test_verify_ptable_flag_raises_exception_invalid_flag(self):
        devpath = '/dev/vda1'
        expected_flag = self.random_string()
        self.assertNotIn(expected_flag, block_meta.SGDISK_FLAGS.keys())
        self.assertNotIn(expected_flag, block_meta.MSDOS_FLAGS.keys())
        with self.assertRaises(RuntimeError):
            block_meta.verify_ptable_flag(devpath, expected_flag,
                                          sfdisk_info=self.sfdisk_info_gpt)

    def test_verify_ptable_flag_checks_bootable_not_table_type(self):
        devpath = '/dev/vdb1'
        expected_flag = 'boot'
        del self.sfdisk_info_dos['partitions'][0]['bootable']
        self.sfdisk_info_dos['partitions'][0]['type'] = '0x80'
        with self.assertRaises(RuntimeError):
            block_meta.verify_ptable_flag(devpath, expected_flag,
                                          sfdisk_info=self.sfdisk_info_dos)

    def test_verify_ptable_flag_calls_block_sfdisk_if_info_none(self):
        devpath = '/dev/vda15'
        expected_flag = 'boot'
        self.m_block_sfdisk_info.return_value = self.sfdisk_info_gpt
        block_meta.verify_ptable_flag(devpath, expected_flag, sfdisk_info=None)
        self.assertEqual(
            [call(devpath)],
            self.m_block_sfdisk_info.call_args_list)

    def test_verify_ptable_flag_finds_boot_on_msdos(self):
        devpath = '/dev/vdb1'
        expected_flag = 'boot'
        block_meta.verify_ptable_flag(devpath, expected_flag,
                                      sfdisk_info=self.sfdisk_info_dos)

    def test_verify_ptable_flag_finds_linux_on_dos_primary_partition(self):
        devpath = '/dev/vdb2'
        expected_flag = 'linux'
        block_meta.verify_ptable_flag(devpath, expected_flag,
                                      sfdisk_info=self.sfdisk_info_dos)

    def test_verify_ptable_flag_finds_dos_extended_partition(self):
        devpath = '/dev/vdb3'
        expected_flag = 'extended'
        block_meta.verify_ptable_flag(devpath, expected_flag,
                                      sfdisk_info=self.sfdisk_info_dos)

    def test_verify_ptable_flag_finds_dos_logical_partition(self):
        devpath = '/dev/vdb5'
        expected_flag = 'logical'
        self.m_block_get_blockdev_for_partition.return_value = (
            ('/dev/vdb', '5'))
        block_meta.verify_ptable_flag(devpath, expected_flag,
                                      sfdisk_info=self.sfdisk_info_dos)


# vi: ts=4 expandtab syntax=python
