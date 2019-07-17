# This file is part of curtin. See LICENSE file for copyright and license info.

from argparse import Namespace
from collections import OrderedDict
import copy
from mock import patch, call
import os

from curtin.commands import block_meta
from curtin import paths, util
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
        self.add_patch('curtin.block.rescan_block_devices',
                       'mock_block_rescan')

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
        self.mock_subp.assert_has_calls(
            [call(['parted', disk_kname, '--script',
                   'mkpart', 'primary', '2048s', '1001471s'], capture=True)])

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
        self.assertIn("/dev/disk2", lines[1])
        self.assertIn("/dev/disk1", lines[2])

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
        self.assertEqual(
            ["/dev/disk2", "/mnt", "btrfs", "noatime", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())

    def test_fstab_line_for_data_with_passno_and_freq(self):
        """fstab_line_for_data should respect passno and freq."""
        fdata = block_meta.FstabData(
            spec="/dev/d1", path="/mnt", fstype='ext4', freq="1", passno="2")
        self.assertEqual(
            ["1", "2"], block_meta.fstab_line_for_data(fdata).split()[4:6])

    def test_fstab_line_for_data_raises_error_without_spec_or_device(self):
        """fstab_line_for_data should raise ValueError if no spec or device."""
        fdata = block_meta.FstabData(
            spec=None, device=None, path="/", fstype='ext3')
        match = r".*missing.*spec.*device"
        with self.assertRaisesRegexp(ValueError, match):
            block_meta.fstab_line_for_data(fdata)

    @patch('curtin.block.get_volume_uuid')
    def test_fstab_line_for_data_uses_uuid(self, m_get_uuid):
        """fstab_line_for_data with a device mounts by uuid."""
        fdata = block_meta.FstabData(
            device="/dev/disk2", path="/mnt", fstype='ext4')
        uuid = 'b30d2389-5152-4fbc-8f18-0385ef3046c5'
        m_get_uuid.side_effect = lambda d: uuid if d == "/dev/disk2" else None
        self.assertEqual(
            ["UUID=%s" % uuid, "/mnt", "ext4", "defaults", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())
        self.assertEqual(1, m_get_uuid.call_count)

    @patch('curtin.block.get_volume_uuid')
    def test_fstab_line_for_data_uses_device_if_no_uuid(self, m_get_uuid):
        """fstab_line_for_data with a device and no uuid uses device."""
        fdata = block_meta.FstabData(
            device="/dev/disk2", path="/mnt", fstype='ext4')
        m_get_uuid.return_value = None
        self.assertEqual(
            ["/dev/disk2", "/mnt", "ext4", "defaults", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())
        self.assertEqual(1, m_get_uuid.call_count)

    @patch('curtin.block.get_volume_uuid')
    def test_fstab_line_for_data__spec_and_dev_prefers_spec(self, m_get_uuid):
        """fstab_line_for_data should prefer spec over device."""
        spec = "/dev/xvda1"
        fdata = block_meta.FstabData(
            spec=spec, device="/dev/disk/by-uuid/7AC9-DEFF",
            path="/mnt", fstype='ext4')
        m_get_uuid.return_value = None
        self.assertEqual(
            ["/dev/xvda1", "/mnt", "ext4", "defaults", "0", "0"],
            block_meta.fstab_line_for_data(fdata).split())
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


class TestLvmPartitionHandler(CiTestCase):

    def setUp(self):
        super(TestLvmPartitionHandler, self).setUp()

        self.add_patch('curtin.commands.block_meta.lvm', 'm_lvm')
        self.add_patch('curtin.commands.block_meta.distro', 'm_distro')
        self.add_patch('curtin.commands.block_meta.util.subp', 'm_subp')
        self.add_patch('curtin.commands.block_meta.make_dname', 'm_dname')

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


# vi: ts=4 expandtab syntax=python
