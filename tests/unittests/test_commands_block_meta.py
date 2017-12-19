from mock import patch, call
from argparse import Namespace

from curtin.commands import block_meta
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
        self.add_patch('curtin.util.subp', 'mock_subp')
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
                     'wipe': 'superblock'}
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
