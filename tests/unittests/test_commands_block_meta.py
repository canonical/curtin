# This file is part of curtin. See LICENSE file for copyright and license info.

from argparse import Namespace
from collections import OrderedDict
from mock import patch, call

from curtin.commands import block_meta
from curtin import util
from .helpers import CiTestCase


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
        paths = ["curtin", "system-data/var/lib/snapd"]
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
        paths = ["curtin", "system-data/var/lib/snapd"]
        self.mock_block_get_root_device.assert_called_with([devname],
                                                           paths=paths)

    @patch('curtin.commands.block_meta.write_image_to_disk')
    def test_meta_simple_calls_write_img(self, mock_write_image):
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
                         boot_fstype=None, fstype=None)

        block_meta.meta_simple(args)

        mock_write_image.assert_called_with(sources.get('unittest'), devname)
        self.mock_subp.assert_has_calls(
            [call(['mount', devname, self.target])])


class TestBlockMeta(CiTestCase):

    def setUp(self):
        super(TestBlockMeta, self).setUp()

        basepath = 'curtin.commands.block_meta.'
        self.add_patch(basepath + 'get_path_to_storage_volume', 'mock_getpath')
        self.add_patch(basepath + 'make_dname', 'mock_make_dname')
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
        self.add_patch('curtin.block.zero_file_at_offsets',
                       'mock_block_zero_file')

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

        block_meta.partition_handler(part_info, self.storage_config)
        part_offset = 2048 * 512
        self.mock_block_zero_file.assert_called_with(disk_kname, [part_offset],
                                                     exclusive=False)
        self.mock_subp.assert_called_with(['parted', disk_kname, '--script',
                                           'mkpart', 'primary', '2048s',
                                           '1001471s'], capture=True)

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
        self.mock_block_get_volume_uuid.return_value = None

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        expected = "%s %s %s %s 0 0\n" % (disk_info['path'],
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
        self.mock_block_get_volume_uuid.return_value = None

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'ro'
        expected = "%s %s %s %s 0 0\n" % (disk_info['path'],
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
        self.mock_block_get_volume_uuid.return_value = None

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        expected = "%s %s %s %s 0 0\n" % (disk_info['path'],
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
        self.mock_block_get_volume_uuid.return_value = None

        block_meta.mount_handler(mount_info, self.storage_config)
        options = 'defaults'
        expected = "#curtin-test\n%s %s %s %s 0 0\n" % (disk_info['path'],
                                                        mount_info['path'],
                                                        fs_info['fstype'],
                                                        options)

        with open(fstab, 'r') as fh:
            rendered_fstab = fh.read()

        print(rendered_fstab)
        self.assertEqual(rendered_fstab, expected)


class TestZFSRootUpdates(CiTestCase):
    def test_basic_zfsroot_update_storage_config(self):
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

        zfsroot_volname = "/ROOT/zfsroot"
        pool_id = zfsroot_id + '_zfsroot_pool'
        newents = [
            {'type': 'zpool', 'id': pool_id,
             'pool': 'rpool', 'vdevs': ['disk1p1'], 'mountpoint': '/'},
            {'type': 'zfs', 'id': zfsroot_id + '_zfsroot_container',
             'pool': pool_id, 'volume': '/ROOT',
             'properties': {'canmount': 'off', 'mountpoint': 'none'}},
            {'type': 'zfs', 'id': zfsroot_id + '_zfsroot_fs',
             'pool': pool_id, 'volume': zfsroot_volname,
             'properties': {'canmount': 'noauto', 'mountpoint': '/'}},
        ]
        expected = OrderedDict(
            [(i['id'], i) for i in base + newents + extra])

        scfg = block_meta.extract_storage_ordered_dict(
            {'storage': {'version': 1, 'config': base + zfsroots + extra}})
        found = block_meta.zfsroot_update_storage_config(scfg)
        print(util.json_dumps([(k, v) for k, v in found.items()]))
        self.assertEqual(expected, found)

# vi: ts=4 expandtab syntax=python
