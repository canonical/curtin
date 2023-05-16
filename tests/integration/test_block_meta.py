# This file is part of curtin. See LICENSE file for copyright and license info.

import dataclasses
from dataclasses import dataclass
import contextlib
import json
import os
from parameterized import parameterized
from pathlib import Path
import re
import stat
import sys
from typing import Optional
import tempfile
from unittest import skipIf
import yaml

from curtin import block, compat, distro, log, udev, util
from curtin.commands.block_meta import _get_volume_fstype
from curtin.commands.block_meta_v2 import ONE_MIB_BYTES

from tests.unittests.helpers import CiTestCase
from tests.integration.webserv import ImageServer


class IntegrationTestCase(CiTestCase):
    allowed_subp = True


@contextlib.contextmanager
def loop_dev(image, sector_size=512):
    cmd = ['losetup', '--show', '--find', image]
    if sector_size != 512:
        cmd.extend(('--sector-size', str(sector_size)))
    dev = util.subp(cmd, capture=True, decode='ignore')[0].strip()
    util.subp(['partprobe', dev])
    try:
        udev.udevadm_trigger([dev])
        yield dev
    finally:
        util.subp(['losetup', '--detach', dev])


@dataclass(order=True)
class PartData:
    number: Optional[int] = None
    offset: Optional[int] = None
    size: Optional[int] = None
    boot: Optional[bool] = None
    partition_type: Optional[str] = None

    # test cases may initialize the values they care about
    # test utilities shall initialize all fields
    def assertFieldsAreNotNone(self):
        for field in dataclasses.fields(self):
            assert getattr(self, field.name) is not None

    def __eq__(self, other):
        for field in dataclasses.fields(self):
            myval = getattr(self, field.name)
            otherval = getattr(other, field.name)
            if myval is not None and otherval is not None \
                    and myval != otherval:
                return False
        return True


def _get_ext_size(dev, part_action):
    num = part_action['number']
    cmd = ['dumpe2fs', '-h', f'{dev}p{num}']
    out = util.subp(cmd, capture=True)[0]
    for line in out.splitlines():
        if line.startswith('Block count'):
            block_count = line.split(':')[1].strip()
        if line.startswith('Block size'):
            block_size = line.split(':')[1].strip()
    return int(block_count) * int(block_size)


def _get_ntfs_size(dev, part_action):
    num = part_action['number']
    cmd = ['ntfsresize',
           '--no-action',
           '--force',  # needed post-resize, which otherwise demands a CHKDSK
           '--info', f'{dev}p{num}']
    out = util.subp(cmd, capture=True)[0]
    # Sample input:
    # Current volume size: 41939456 bytes (42 MB)
    volsize_matcher = re.compile(r'^Current volume size: ([0-9]+) bytes')
    for line in out.splitlines():
        m = volsize_matcher.match(line)
        if m:
            return int(m.group(1))
    raise Exception('ntfs volume size not found')


_get_fs_sizers = {
    'ext2': _get_ext_size,
    'ext3': _get_ext_size,
    'ext4': _get_ext_size,
    'ntfs': _get_ntfs_size,
}


def _get_filesystem_size(dev, part_action, fstype='ext4'):
    if fstype not in _get_fs_sizers.keys():
        raise Exception(f'_get_filesystem_size: no support for {fstype}')
    return _get_fs_sizers[fstype](dev, part_action)


def _get_disk_label_id(dev):
    ptable_json = util.subp(['sfdisk', '-J', dev], capture=True)[0]
    ptable = json.loads(ptable_json)
    # string in lowercase hex
    return ptable['partitiontable']['id']


def summarize_partitions(dev):
    parts = []
    ptable_json = util.subp(['sfdisk', '-J', dev], capture=True)[0]
    ptable = json.loads(ptable_json)['partitiontable']
    sectorsize = ptable.get('sectorsize', 512)
    assert dev == ptable['device']
    sysfs_data = block.sysfs_partition_data(dev)
    for part in ptable['partitions']:
        node = part['node']
        (unused, s_number, s_offset, s_size) = [
                entry for entry in sysfs_data
                if '/dev/' + entry[0] == node][0]
        assert node.startswith(f'{dev}p')
        number = int(node[len(dev) + 1:])
        ptype = part['type']
        offset = part['start'] * sectorsize
        size = part['size'] * sectorsize
        boot = part.get('bootable', False)
        assert s_number == number
        assert s_offset == offset
        if ptype not in ('5', 'f'):  # extended sizes known to be bad in sysfs
            assert s_size == size
        pd = PartData(
                number=number, offset=offset, size=size,
                boot=boot, partition_type=ptype)
        pd.assertFieldsAreNotNone()
        parts.append(pd)
    return sorted(parts)


class StorageConfigBuilder:

    def __init__(self, *, version):
        self.version = version
        self.config = []
        self.cur_image = None

    def render(self):
        return {
            'storage': {
                'config': self.config,
                'version': self.version,
                },
            }

    def _add(self, *, type, **kw):
        if type not in ['image', 'device'] and self.cur_image is None:
            raise Exception("no current image")
        action = {'id': 'id' + str(len(self.config))}
        action.update(type=type, **kw)
        self.config.append(action)
        return action

    def add_image(self, *, path, size, create=False, **kw):
        if create:
            util.subp(['truncate', '-s', str(size), path])
        action = self._add(type='image', path=path, size=size, **kw)
        self.cur_image = action['id']
        return action

    def add_device(self, *, path, **kw):
        action = self._add(type='device', path=path, **kw)
        self.cur_image = action['id']
        return action

    def add_part(self, *, size, **kw):
        fstype = kw.pop('fstype', None)
        part = self._add(type='partition', device=self.cur_image, size=size,
                         **kw)
        if fstype:
            self.add_format(part=part, fstype=fstype)
        return part

    def add_format(self, *, part, fstype='ext4', **kw):
        return self._add(type='format', volume=part['id'], fstype=fstype, **kw)

    def set_preserve(self):
        for action in self.config:
            action['preserve'] = True

    def add_dmcrypt(self, *, volume, dm_name=None, **kw):
        if dm_name is None:
            dm_name = CiTestCase.random_string()
        return self._add(
            type='dm_crypt',
            volume=volume['id'],
            dm_name=dm_name,
            **kw)


class TestBlockMeta(IntegrationTestCase):
    def setUp(self):
        self.data = self.random_string()
        log.basicConfig(verbosity=3)

    def assertPartitions(self, *args):
        with loop_dev(self.img) as dev:
            self.assertEqual([*args], summarize_partitions(dev))

    @contextlib.contextmanager
    def mount(self, dev, partition_cfg):
        mnt_point = self.tmp_dir()
        num = partition_cfg['number']
        with util.mount(f'{dev}p{num}', mnt_point):
            yield mnt_point

    @contextlib.contextmanager
    def open_file_on_part(self, dev, part_action, mode):
        with self.mount(dev, part_action) as mnt_point:
            with open(f'{mnt_point}/data.txt', mode) as fp:
                yield fp

    def create_data(self, dev, part_action):
        with self.open_file_on_part(dev, part_action, 'w') as fp:
            fp.write(self.data)

    def check_data(self, dev, part_action):
        with self.open_file_on_part(dev, part_action, 'r') as fp:
            self.assertEqual(self.data, fp.read())

    def check_fssize(self, dev, part_action, fstype, expected):
        tolerance = 0
        if fstype == 'ntfs':
            # Per ntfsresize manpage, the actual fs size is at least one sector
            # less than requested.
            # In these tests it has been consistently 7 sectors fewer.
            tolerance = 512 * 10
        actual_fssize = _get_filesystem_size(dev, part_action, fstype)
        diff = expected - actual_fssize
        self.assertTrue(0 <= diff <= tolerance, f'difference of {diff}')

    def run_bm(self, config, *args, **kwargs):
        config_path = self.tmp_path('config.yaml')
        with open(config_path, 'w') as fp:
            yaml.dump(config, fp)

        self.fstab_dir = self.tmp_dir()
        cmd_env = kwargs.pop('env', {})
        cmd_env.update({
            'PATH': os.environ['PATH'],
            'CONFIG': config_path,
            'WORKING_DIR': '/tmp',
            'OUTPUT_FSTAB': self.tmp_path('fstab', _dir=self.fstab_dir),
            'OUTPUT_INTERFACES': '',
            'OUTPUT_NETWORK_STATE': '',
            'OUTPUT_NETWORK_CONFIG': '',
            'TARGET_MOUNT_POINT': self.tmp_dir(),
        })

        cmd = [
            sys.executable, '-m', 'curtin', '--showtrace', '-vv',
            '-c', config_path, 'block-meta', '--testmode', 'custom',
            *args,
            ]

        # Set debug=True to halt the integration test and run curtin manually,
        # with the integration tests having setup the environment for you.
        # To see the script name run with "pytest-3 -s", or look at fp.name.
        if not kwargs.pop('debug', False):
            util.subp(cmd, env=cmd_env, **kwargs)
            return

        env = cmd_env.copy()
        env.update(PYTHONPATH=os.getcwd())
        import pprint
        pp = pprint.PrettyPrinter(indent=4)
        code = '''\
#!/usr/bin/python3
import subprocess
cmd = {cmd}
env = {env}
subprocess.run(cmd, env=env)
'''.format(cmd=pp.pformat(cmd), env=pp.pformat(env))

        opts = dict(mode='w', delete=False, suffix='.py')
        with tempfile.NamedTemporaryFile(**opts) as fp:
            fp.write(code)
        try:
            os.chmod(fp.name, 0o700)
            print('\nThe integration test is paused.')
            print('Use script {} to run curtin manually.'.format(fp.name))
            import pdb
            pdb.set_trace()
        finally:
            os.unlink(fp.name)

    def _test_default_offsets(self, ptable, version, sector_size=512):
        psize = 40 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=version)
        disk_action = config.add_image(
            path=img, size='200M', ptable=ptable, sector_size=sector_size)
        p1 = config.add_part(size=psize, number=1)
        p2 = config.add_part(size=psize, number=2)
        p3 = config.add_part(size=psize, number=3)
        c = config.render()

        # Request that curtin dump the device node path for each action
        dmp = c['storage']['device_map_path'] = self.tmp_path('map.json')

        self.run_bm(c)

        # We can't check a whole lot about the device map, but we can
        # check all actions are in the map and each action should be
        # /dev/loopXXpX were /dev/loopXX is the device for the image.
        with open(dmp) as fp:
            device_map = json.load(fp)
            image_device = device_map[disk_action['id']]
            for action in c['storage']['config']:
                self.assertIn(action['id'], device_map)
                self.assertTrue(
                    device_map[action['id']].startswith(image_device))

        with loop_dev(img, sector_size) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,             size=psize),
                    PartData(number=2, offset=(1 << 20) + psize,   size=psize),
                    PartData(number=3, offset=(1 << 20) + 2*psize, size=psize),
                ])
        p1['offset'] = 1 << 20
        p2['offset'] = (1 << 20) + psize
        p3['offset'] = (1 << 20) + 2*psize
        config.set_preserve()
        self.run_bm(config.render())

    def test_default_offsets_gpt_v1(self):
        self._test_default_offsets('gpt', 1)

    def test_default_offsets_msdos_v1(self):
        self._test_default_offsets('msdos', 1)

    def test_default_offsets_gpt_v2(self):
        self._test_default_offsets('gpt', 2)

    def test_default_offsets_msdos_v2(self):
        self._test_default_offsets('msdos', 2)

    @skipIf(not compat.supports_large_sectors(), 'test is for large sectors')
    def test_default_offsets_gpt_v1_4k(self):
        self._test_default_offsets('gpt', 1, 4096)

    @skipIf(not compat.supports_large_sectors(), 'test is for large sectors')
    def test_default_offsets_msdos_v1_4k(self):
        self._test_default_offsets('msdos', 1, 4096)

    @skipIf(not compat.supports_large_sectors(), 'test is for large sectors')
    def test_default_offsets_gpt_v2_4k(self):
        self._test_default_offsets('gpt', 2, 4096)

    @skipIf(not compat.supports_large_sectors(), 'test is for large sectors')
    def test_default_offsets_msdos_v2_4k(self):
        self._test_default_offsets('msdos', 2, 4096)

    def _test_specified_offsets(self, ptable, version):
        psize = 20 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=version)
        config.add_image(path=img, size='100M', ptable=ptable)
        config.add_part(size=psize, number=1, offset=psize)
        config.add_part(size=psize, number=2, offset=psize * 3)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=psize,   size=psize),
                    PartData(number=2, offset=psize*3, size=psize),
                ])
        config.set_preserve()
        self.run_bm(config.render())

    def DONT_test_specified_offsets_gpt_v1(self):
        self._test_specified_offsets('gpt', 1)

    def DONT_test_specified_offsets_msdos_v1(self):
        self._test_specified_offsets('msdos', 1)

    def test_specified_offsets_gpt_v2(self):
        self._test_specified_offsets('gpt', 2)

    def test_specified_offsets_msdos_v2(self):
        self._test_specified_offsets('msdos', 2)

    def test_minimum_gpt_offset_v2(self):
        # The default first-lba for a GPT is 2048 (i.e. one megabyte
        # into the disk) but it is possible to create a GPT with a
        # value as low as 34 and curtin shouldn't get in the way of
        # you doing that.
        psize = 20 << 20
        offset = 34*512
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='gpt')
        config.add_part(size=psize, number=1, offset=offset)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=offset, size=psize),
                ])
        config.set_preserve()
        self.run_bm(config.render())

    def _test_non_default_numbering(self, ptable, version):
        psize = 40 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=version)
        config.add_image(path=img, size='100M', ptable=ptable)
        config.add_part(size=psize, number=1)
        config.add_part(size=psize, number=4)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,           size=psize),
                    PartData(number=4, offset=(1 << 20) + psize, size=psize),
                ])

    def test_non_default_numbering_gpt_v1(self):
        self._test_non_default_numbering('gpt', 1)

    def BROKEN_test_non_default_numbering_msdos_v1(self):
        self._test_non_default_numbering('msdos', 2)

    def test_non_default_numbering_gpt_v2(self):
        self._test_non_default_numbering('gpt', 2)

    def test_non_default_numbering_msdos_v2(self):
        self._test_non_default_numbering('msdos', 2)

    def _test_logical(self, version):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=version)
        config.add_image(path=img, size='100M', ptable='msdos')
        # curtin adds 1MiB to the size of the extend partition per contained
        # logical partition, but only in v1 mode
        size = '97M' if version == 1 else '99M'
        config.add_part(size=size, number=1, flag='extended',
                        wipe='superblock')
        config.add_part(size='10M', number=5, flag='logical')
        config.add_part(size='10M', number=6, flag='logical')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,  size=99 << 20),
                    PartData(number=5, offset=2 << 20,  size=10 << 20),
                    # part 5 goes to 12 MiB offset, curtin leaves a 1 MiB gap.
                    PartData(number=6, offset=13 << 20, size=10 << 20),
                ])

            if distro.lsb_release()['release'] >= '20.04':
                p1kname = block.partition_kname(block.path_to_kname(dev), 1)
                self.assertTrue(block.is_extended_partition('/dev/' + p1kname))
            else:
                # on Bionic and earlier, the block device for the extended
                # partition is not functional, so attempting to verify it is
                # expected to fail.  So just read the value directly from the
                # expected signature location.
                signature = util.load_file(dev, decode=False,
                                           read_len=2, offset=0x1001fe)
                self.assertEqual(b'\x55\xAA', signature)

    def test_logical_v1(self):
        self._test_logical(1)

    def test_logical_v2(self):
        self._test_logical(2)

    def _test_replace_partition(self, ptable):
        psize = 20 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable=ptable)
        config.add_part(size=psize, number=1)
        config.add_part(size=psize, number=2)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,           size=psize),
                    PartData(number=2, offset=(1 << 20) + psize, size=psize),
                ])

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable=ptable, preserve=True)
        config.add_part(size=psize, number=1, offset=1 << 20, preserve=True)
        config.add_part(size=psize*2, number=2)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,           size=psize),
                    PartData(number=2, offset=(1 << 20) + psize, size=2*psize),
                ])

    def test_replace_partition_gpt_v2(self):
        self._test_replace_partition('gpt')

    def test_replace_partition_msdos_v2(self):
        self._test_replace_partition('msdos')

    def test_delete_logical_partition(self):
        # The test case that resulted in a lot of hair-pulling:
        # deleting a logical partition renumbers any later partitions
        # (so you cannot stably refer to partitions by number!)
        psize = 20 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='msdos')
        config.add_part(size='90M', number=1, flag='extended')
        config.add_part(size=psize, number=5, flag='logical')
        config.add_part(size=psize, number=6, flag='logical')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=90 << 20),
                    PartData(number=5, offset=(2 << 20), size=psize),
                    PartData(number=6, offset=(3 << 20) + psize, size=psize),
                ])

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='msdos', preserve=True)
        config.add_part(size='90M', number=1, flag='extended', preserve=True)
        config.add_part(
            size=psize, number=5, flag='logical', offset=(3 << 20) + psize,
            preserve=True)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=90 << 20),
                    PartData(number=5, offset=(3 << 20) + psize, size=psize),
                ])

    def _test_wiping(self, ptable):
        # Test wiping behaviour.
        #
        # Paritions that should be (superblock, i.e. first and last
        # megabyte) wiped:
        #
        # 1) New partitions
        # 2) Partitions that are being removed, i.e. no longer present
        # 3) Preserved partitions with an explicit wipe
        #
        # Partitions that should not be wiped:
        #
        # 4) Preserved partitions with no wipe field.
        #
        # We test this by creating some partitions with block-meta,
        # writing content to them, then running block-meta again, with
        # each partition matching one of the conditions above.
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='30M', ptable=ptable)
        config.add_part(size='5M', number=1, offset='5M')
        config.add_part(size='5M', number=2, offset='10M')
        config.add_part(size='5M', number=3, offset='15M')
        config.add_part(size='5M', number=4, offset='20M')
        self.run_bm(config.render())

        part_offset_sizes = {}
        with loop_dev(img) as dev:
            for kname, number, offset, size in block.sysfs_partition_data(dev):
                content = bytes([number])
                with open(block.kname_to_path(kname), 'wb') as fp:
                    fp.write(content*size)
                part_offset_sizes[number] = (offset, size)

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='30M', ptable=ptable, preserve=True)
        config.add_part(size='5M', number=1, offset='5M')
        # Partition 2 is being deleted.
        config.add_part(
            size='5M', number=3, offset='15M', preserve=True,
            wipe='superblock')
        config.add_part(size='5M', number=4, offset='20M', preserve=True)
        self.run_bm(config.render())

        expected_content = {1: {0}, 2: {0}, 3: {0}, 4: {4}}

        with loop_dev(img) as dev:
            with open(dev, 'rb') as fp:
                for nr, (offset, size) in part_offset_sizes.items():
                    expected = expected_content[nr]
                    fp.seek(offset)
                    first = set(fp.read(ONE_MIB_BYTES))
                    fp.seek(offset + size - ONE_MIB_BYTES)
                    last = set(fp.read(ONE_MIB_BYTES))
                    self.assertEqual(first, expected)
                    self.assertEqual(last, expected)

    def test_wiping_gpt(self):
        self._test_wiping('gpt')

    def test_wiping_msdos(self):
        self._test_wiping('msdos')

    def test_raw_image(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=1)
        config.add_image(path=img, size='2G', ptable='gpt', create=True)

        curtin_cfg = config.render()
        server = ImageServer()
        try:
            server.start()
            sources = {
                'sources': {
                    '00': {
                        'uri': server.base_url + '/static/lvm-disk.dd',
                        'type': 'dd-raw',
                    },
                },
            }
            curtin_cfg.update(**sources)
            mnt_point = self.tmp_dir()
            cmd_env = {
                'TARGET_MOUNT_POINT': mnt_point,
            }
            with loop_dev(img) as dev:
                try:
                    self.run_bm(curtin_cfg, f'--devices={dev}', env=cmd_env)
                finally:
                    util.subp(['umount', mnt_point])
                    udev.udevadm_settle()
                    util.subp(
                        ['dmsetup', 'remove', '/dev/mapper/vmtests-root']
                    )
        finally:
            server.stop()

    def _do_test_resize(self, start, end, fstype):
        start <<= 20
        end <<= 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        p1 = config.add_part(size=start, offset=1 << 20, number=1,
                             fstype=fstype)
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.assertEqual(fstype, _get_volume_fstype(f'{dev}p1'))
            self.create_data(dev, p1)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=start),
                ])
            self.check_fssize(dev, p1, fstype, start)

        config.set_preserve()
        p1['resize'] = True
        p1['size'] = end
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.check_data(dev, p1)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=end),
                ])
            self.check_fssize(dev, p1, fstype, end)

    def test_multi_resize(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')

        def size_to(size):
            p1['size'] = size
            self.run_bm(config.render())
            with loop_dev(img) as dev:
                self.assertEqual('ntfs', _get_volume_fstype(f'{dev}p1'))
                self.create_data(dev, p1)
                self.assertEqual(
                    summarize_partitions(dev), [
                        PartData(number=1, offset=1 << 20, size=size),
                    ])
                self.check_fssize(dev, p1, 'ntfs', size)

        p1 = config.add_part(size=180 << 20, offset=1 << 20, number=1,
                             fstype='ntfs')
        size_to(180 << 20)

        config.set_preserve()
        p1['resize'] = True

        size_to(160 << 20)
        size_to(140 << 20)

    def test_resize_up_ext2(self):
        self._do_test_resize(40, 80, 'ext2')

    def test_resize_down_ext2(self):
        self._do_test_resize(80, 40, 'ext2')

    def test_resize_up_ext3(self):
        self._do_test_resize(40, 80, 'ext3')

    def test_resize_down_ext3(self):
        self._do_test_resize(80, 40, 'ext3')

    def test_resize_up_ext4(self):
        self._do_test_resize(40, 80, 'ext4')

    def test_resize_down_ext4(self):
        self._do_test_resize(80, 40, 'ext4')

    def test_resize_up_ntfs(self):
        self._do_test_resize(40, 80, 'ntfs')

    def test_resize_down_ntfs(self):
        self._do_test_resize(80, 40, 'ntfs')

    def test_resize_logical(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='msdos')
        config.add_part(size='50M', number=1, flag='extended', offset=1 << 20)
        config.add_part(size='10M', number=5, flag='logical', offset=2 << 20)
        p6 = config.add_part(size='10M', number=6, flag='logical',
                             offset=13 << 20, fstype='ext4')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.create_data(dev, p6)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,  size=50 << 20),
                    PartData(number=5, offset=2 << 20,  size=10 << 20),
                    # part 5 goes to 12 MiB offset, curtin leaves a 1 MiB gap.
                    PartData(number=6, offset=13 << 20, size=10 << 20),
                ])

        config.set_preserve()
        p6['resize'] = True
        p6['size'] = '20M'
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.check_data(dev, p6)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,  size=50 << 20),
                    PartData(number=5, offset=2 << 20,  size=10 << 20),
                    PartData(number=6, offset=13 << 20, size=20 << 20),
                ])

    @skipIf(distro.lsb_release()['release'] < '20.04',
            'old lsblk will not list info about extended partitions')
    def test_resize_extended(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='msdos')
        p1 = config.add_part(size='50M', number=1, flag='extended',
                             offset=1 << 20)
        p5 = config.add_part(size='49M', number=5, flag='logical',
                             offset=2 << 20)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=50 << 20),
                    PartData(number=5, offset=2 << 20, size=49 << 20),
                ])

        config.set_preserve()
        p1['resize'] = True
        p1['size'] = '99M'
        p5['resize'] = True
        p5['size'] = '98M'
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,  size=99 << 20),
                    PartData(number=5, offset=2 << 20,  size=98 << 20),
                ])

    def test_split(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        config.add_part(size=9 << 20, offset=1 << 20, number=1)
        p2 = config.add_part(size='180M', offset=10 << 20, number=2,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.create_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=180 << 20),
                ])
            self.assertEqual(180 << 20, _get_filesystem_size(dev, p2))

        config.set_preserve()
        p2['resize'] = True
        p2['size'] = '80M'
        p3 = config.add_part(size='100M', offset=90 << 20, number=3,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.check_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=80 << 20),
                    PartData(number=3, offset=90 << 20, size=100 << 20),
                ])
            self.assertEqual(80 << 20, _get_filesystem_size(dev, p2))
            self.assertEqual(100 << 20, _get_filesystem_size(dev, p3))

    def test_partition_unify(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        config.add_part(size=9 << 20, offset=1 << 20, number=1)
        p2 = config.add_part(size='40M', offset=10 << 20, number=2,
                             fstype='ext4')
        p3 = config.add_part(size='60M', offset=50 << 20, number=3,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.create_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=40 << 20),
                    PartData(number=3, offset=50 << 20, size=60 << 20),
                ])
            self.assertEqual(40 << 20, _get_filesystem_size(dev, p2))
            self.assertEqual(60 << 20, _get_filesystem_size(dev, p3))

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        config.add_part(size=9 << 20, offset=1 << 20, number=1)
        p2 = config.add_part(size='100M', offset=10 << 20, number=2,
                             fstype='ext4', resize=True)
        config.set_preserve()
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.check_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=100 << 20),
                ])
            self.assertEqual(100 << 20, _get_filesystem_size(dev, p2))

    def test_mix_of_operations_gpt(self):
        # a test that keeps, creates, resizes, and deletes a partition
        # 200 MiB disk, using full disk
        #      init size preserve     final size
        # p1 -  9 MiB    yes            9MiB
        # p2 - 90 MiB    yes, resize  139MiB
        # p3 - 99 MiB    no            50MiB
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        config.add_part(size=9 << 20, offset=1 << 20, number=1)
        p2 = config.add_part(size='90M', offset=10 << 20, number=2,
                             fstype='ext4')
        p3 = config.add_part(size='99M', offset=100 << 20, number=3,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.create_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=90 << 20),
                    PartData(number=3, offset=100 << 20, size=99 << 20),
                ])
            self.assertEqual(90 << 20, _get_filesystem_size(dev, p2))
            self.assertEqual(99 << 20, _get_filesystem_size(dev, p3))

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='gpt')
        config.add_part(size=9 << 20, offset=1 << 20, number=1)
        p2 = config.add_part(size='139M', offset=10 << 20, number=2,
                             fstype='ext4', resize=True)
        config.set_preserve()
        p3 = config.add_part(size='50M', offset=149 << 20, number=3,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.check_data(dev, p2)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=139 << 20),
                    PartData(number=3, offset=149 << 20, size=50 << 20),
                ])
            self.assertEqual(139 << 20, _get_filesystem_size(dev, p2))
            self.assertEqual(50 << 20, _get_filesystem_size(dev, p3))

    @skipIf(distro.lsb_release()['release'] < '20.04',
            'old lsblk will not list info about extended partitions')
    def test_mix_of_operations_msdos(self):
        # a test that keeps, creates, resizes, and deletes a partition
        # including handling of extended/logical
        # 200 MiB disk, initially only using front 100MiB
        #      flag     init size preserve     final size
        # p1 - primary   9MiB     yes            9MiB
        # p2 - extended 89MiB     yes, resize  189MiB
        # p3 - logical  37MiB     yes, resize  137MiB
        # p4 - logical  50MiB     no            50MiB
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='msdos')
        p1 = config.add_part(size='9M', offset=1 << 20, number=1,
                             fstype='ext4')
        config.add_part(size='89M', offset=10 << 20, number=2, flag='extended')
        p5 = config.add_part(size='36M', offset=11 << 20, number=5,
                             flag='logical', fstype='ext4')
        p6 = config.add_part(size='50M', offset=49 << 20, number=6,
                             flag='logical', fstype='ext4')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.create_data(dev, p1)
            self.create_data(dev, p5)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,  size=9 << 20),
                    PartData(number=2, offset=10 << 20, size=89 << 20),
                    PartData(number=5, offset=11 << 20, size=36 << 20),
                    PartData(number=6, offset=49 << 20, size=50 << 20),
                ])
            self.assertEqual(9 << 20, _get_filesystem_size(dev, p1))
            self.assertEqual(36 << 20, _get_filesystem_size(dev, p5))
            self.assertEqual(50 << 20, _get_filesystem_size(dev, p6))

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='200M', ptable='msdos')
        p1 = config.add_part(size='9M', offset=1 << 20, number=1,
                             fstype='ext4')
        config.add_part(size='189M', offset=10 << 20, number=2,
                        flag='extended', resize=True)
        p5 = config.add_part(size='136M', offset=11 << 20, number=5,
                             flag='logical', fstype='ext4', resize=True)
        config.set_preserve()
        p6 = config.add_part(size='50M', offset=149 << 20, number=6,
                             flag='logical', fstype='ext4')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.check_data(dev, p1)
            self.check_data(dev, p5)
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20,   size=9 << 20),
                    PartData(number=2, offset=10 << 20,  size=189 << 20),
                    PartData(number=5, offset=11 << 20,  size=136 << 20),
                    PartData(number=6, offset=149 << 20, size=50 << 20),
                ])
            self.assertEqual(9 << 20, _get_filesystem_size(dev, p1))
            self.assertEqual(136 << 20, _get_filesystem_size(dev, p5))
            self.assertEqual(50 << 20, _get_filesystem_size(dev, p6))

    def test_split_and_wiping(self):
        # regression test for a bug where a partition wipe would happen before
        # a resize was performed, resulting in data loss.
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='gpt')
        p1 = config.add_part(size=98 << 20, offset=1 << 20, number=1,
                             fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=98 << 20),
                ])
            with self.mount(dev, p1) as mnt_point:
                # Attempt to create files across the partition with gaps
                for i in range(1, 41):
                    with open(f'{mnt_point}/{str(i)}', 'wb') as fp:
                        fp.write(bytes([i]) * (2 << 20))
                for i in range(1, 41):
                    if i % 5 != 0:
                        os.remove(f'{mnt_point}/{str(i)}')

        config = StorageConfigBuilder(version=2)
        config.add_image(path=img, size='100M', ptable='gpt')
        p1 = config.add_part(size=49 << 20, offset=1 << 20, number=1,
                             fstype='ext4', resize=True)
        config.set_preserve()
        config.add_part(size=49 << 20, offset=50 << 20, number=2,
                        fstype='ext4')
        self.run_bm(config.render())
        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(number=1, offset=1 << 20, size=49 << 20),
                    PartData(number=2, offset=50 << 20, size=49 << 20),
                ])
            with self.mount(dev, p1) as mnt_point:
                for i in range(5, 41, 5):
                    with open(f'{mnt_point}/{i}', 'rb') as fp:
                        self.assertEqual(bytes([i]) * (2 << 20), fp.read())

    def test_parttype_dos(self):
        # msdos partition table partitions shall retain their type
        # create initial situation similar to this
        # Device     Boot     Start       End   Sectors  Size Id Type
        # /dev/sda1  *         2048    104447    102400   50M  7 HPFS/NTFS/exFA
        # /dev/sda2          104448 208668781 208564334 99.5G  7 HPFS/NTFS/exFA
        # /dev/sda3       208670720 209711103   1040384  508M 27 Hidden NTFS Wi
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='200M', ptable='msdos')
        config.add_part(size=50 << 20, offset=1 << 20, number=1,
                        fstype='ntfs', flag='boot', partition_type='0x7')
        config.add_part(size=100 << 20, offset=51 << 20, number=2,
                        fstype='ntfs', partition_type='0x7')
        config.add_part(size=48 << 20, offset=151 << 20, number=3,
                        fstype='ntfs', partition_type='0x27')
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=50 << 20,
                     partition_type='7', boot=True),
            PartData(number=2, offset=51 << 20, size=100 << 20,
                     partition_type='7', boot=False),
            PartData(number=3, offset=151 << 20, size=48 << 20,
                     partition_type='27', boot=False))

    def test_parttype_gpt(self):
        # gpt partition table partitions shall retain their type
        # create initial situation similar to this
        # #  Start (sector)    End (sector)   Size        Code  Name
        # 1            2048          206847   100.0 MiB   EF00  EFI system part
        # 2          206848          239615   16.0 MiB    0C01  Microsoft reser
        # 3          239616       103811181   49.4 GiB    0700  Basic data part
        # 4       103813120       104853503   508.0 MiB   2700
        esp = 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B'
        msreserved = 'E3C9E316-0B5C-4DB8-817D-F92DF00215AE'
        msdata = 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7'
        winre = 'DE94BBA4-06D1-4D40-A16A-BFD50179D6AC'
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='100M', ptable='gpt')
        config.add_part(number=1, offset=1 << 20, size=9 << 20,
                        flag='boot', fstype='ntfs')
        config.add_part(number=2, offset=10 << 20, size=20 << 20,
                        partition_type=msreserved)
        config.add_part(number=3, offset=30 << 20, size=50 << 20,
                        partition_type=msdata, fstype='ntfs')
        config.add_part(number=4, offset=80 << 20, size=19 << 20,
                        partition_type=winre, fstype='ntfs')
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=9 << 20,
                     partition_type=esp),
            PartData(number=2, offset=10 << 20, size=20 << 20,
                     partition_type=msreserved),
            PartData(number=3, offset=30 << 20, size=50 << 20,
                     partition_type=msdata),
            PartData(number=4, offset=80 << 20, size=19 << 20,
                     partition_type=winre))

    @parameterized.expand([('msdos',), ('gpt',)])
    def test_disk_label_id_persistent(self, ptable):
        # when the disk is preserved, the disk label id shall also be preserved
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable=ptable)
        config.add_part(number=1, offset=1 << 20, size=18 << 20)
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=18 << 20))
        with loop_dev(self.img) as dev:
            orig_label_id = _get_disk_label_id(dev)

        config.set_preserve()
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=18 << 20))
        with loop_dev(self.img) as dev:
            self.assertEqual(orig_label_id, _get_disk_label_id(dev))

    def test_gpt_uuid_persistent(self):
        # A persistent partition with an unspecified uuid shall keep the uuid
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        config.add_part(number=1, offset=1 << 20, size=18 << 20)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            expected_uuid = sfdisk_info['partitions'][0]['uuid']

        config.set_preserve()
        self.run_bm(config.render())
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            actual_uuid = sfdisk_info['partitions'][0]['uuid']
            self.assertEqual(expected_uuid, actual_uuid)

    def test_gpt_set_name(self):
        self.img = self.tmp_path('image.img')
        name = self.random_string() + ' ' + self.random_string()
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        config.add_part(number=1, offset=1 << 20, size=18 << 20,
                        partition_name=name)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            actual_name = sfdisk_info['partitions'][0]['name']
        self.assertEqual(name, actual_name)

    @parameterized.expand([
        ('random', CiTestCase.random_string(),),
        # "écrasé" means "overwritten"
        ('unicode', "'name' must not be écrasé/덮어쓴!"),
    ])
    def test_gpt_name_persistent(self, title, name):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        p1 = config.add_part(number=1, offset=1 << 20, size=18 << 20,
                             partition_name=name)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            actual_name = sfdisk_info['partitions'][0]['name']
        self.assertEqual(name, actual_name)

        del p1['partition_name']
        config.set_preserve()
        self.run_bm(config.render())
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            actual_name = sfdisk_info['partitions'][0]['name']
        self.assertEqual(name, actual_name)

    def test_gpt_set_single_attr(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        attrs = ['GUID:63']
        config.add_part(number=1, offset=1 << 20, size=18 << 20,
                        attrs=attrs)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            attrs_str = sfdisk_info['partitions'][0]['attrs']
            actual_attrs = set(attrs_str.split(' '))
        self.assertEqual(set(attrs), actual_attrs)

    @skipIf(distro.lsb_release()['release'] < '18.04',
            'old sfdisk no attr support')
    def test_gpt_set_multi_attr(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        attrs = ['GUID:63', 'RequiredPartition']
        config.add_part(number=1, offset=1 << 20, size=18 << 20,
                        attrs=attrs)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            attrs_str = sfdisk_info['partitions'][0]['attrs']
            actual_attrs = set(attrs_str.split(' '))
        self.assertEqual(set(attrs), actual_attrs)

    def test_gpt_attrs_persistent(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, size='20M', ptable='gpt')
        attrs = ['GUID:63']
        p1 = config.add_part(number=1, offset=1 << 20, size=18 << 20,
                             attrs=attrs)
        self.run_bm(config.render())
        pd = PartData(number=1, offset=1 << 20, size=18 << 20)
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            attrs_str = sfdisk_info['partitions'][0]['attrs']
            actual_attrs = set(attrs_str.split(' '))
        self.assertEqual(set(attrs), actual_attrs)

        del p1['attrs']
        config.set_preserve()
        self.run_bm(config.render())
        self.assertPartitions(pd)
        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            attrs_str = sfdisk_info['partitions'][0]['attrs']
            actual_attrs = set(attrs_str.split(' '))
        self.assertEqual(set(attrs), actual_attrs)

    def test_gpt_first_lba_persistent(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, create=True, size='20M', ptable='gpt',
                         preserve=True)
        # Set first-lba, and also a stub partition to keep older sfdisk happy.
        script = '''\
label: gpt
first-lba: 34
1MiB 1MiB L'''.encode()
        with loop_dev(self.img) as dev:
            cmd = ['sfdisk', dev]
            util.subp(cmd, data=script, capture=True)

        config.add_part(number=1, offset=1 << 20, size=1 << 20)
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20))

        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            # default is 2048
            self.assertEqual(34, sfdisk_info['firstlba'])

    def test_gpt_last_lba_persistent(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, create=True, size='20M', ptable='gpt',
                         preserve=True)
        # Set last-lba, and also a stub partition to keep older sfdisk happy.
        script = '''\
label: gpt
last-lba: 10240
1MiB 1MiB L'''.encode()
        with loop_dev(self.img) as dev:
            cmd = ['sfdisk', dev]
            util.subp(cmd, data=script)

        config.add_part(number=1, offset=1 << 20, size=1 << 20)
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20))

        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            # default is disk size in sectors - 17 KiB
            self.assertEqual(10240, sfdisk_info['lastlba'])

    @skipIf(distro.lsb_release()['release'] < '18.04',
            'old sfdisk has no table-length support')
    def test_gpt_table_length_persistent(self):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, create=True, size='20M', ptable='gpt',
                         preserve=True)
        script = '''\
label: gpt
table-length: 256'''.encode()
        with loop_dev(self.img) as dev:
            cmd = ['sfdisk', dev]
            util.subp(cmd, data=script)

        config.add_part(number=1, offset=1 << 20, size=1 << 20)
        self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20))

        with loop_dev(self.img) as dev:
            sfdisk_info = block.sfdisk_info(dev)
            # default is 128
            self.assertEqual(256, int(sfdisk_info['table-length']))

    def test_device_action(self):
        self.img = self.tmp_path('image.img')
        with open(self.img, 'w') as fp:
            fp.truncate(10 << 20)
        with loop_dev(self.img) as dev:
            config = StorageConfigBuilder(version=2)
            config.add_device(path=dev, ptable='gpt')
            config.add_part(number=1, offset=1 << 20, size=1 << 20)
            self.run_bm(config.render())
        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20))

    @parameterized.expand(((1,), (2,)))
    def test_swap(self, sv):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=sv)
        config.add_image(path=self.img, create=True, size='20M',
                         ptable='msdos')
        config.add_part(number=1, offset=1 << 20, size=1 << 20, flag='swap')
        self.run_bm(config.render())

        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20, boot=False,
                     partition_type='82'))

    @parameterized.expand(((1,), (2,)))
    def test_cryptoswap(self, sv=2):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=sv)
        config.add_image(path=self.img, create=True, size='200M',
                         ptable='msdos')
        p1 = config.add_part(
            number=1, offset=1 << 20, size=19 << 20, flag='swap'
        )
        cryptoswap = f"cryptoswap-{self.random_string(length=6)}"
        dmc1 = config.add_dmcrypt(
            volume=p1,
            dm_name=cryptoswap,
            keyfile="/dev/urandom",
            options=["swap", "initramfs"],
        )
        config.add_format(part=dmc1, fstype="swap")
        self.run_bm(config.render())

        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=19 << 20, boot=False,
                     partition_type='82'))

        crypttab_path = Path(self.fstab_dir) / "crypttab"
        with open(crypttab_path) as fp:
            crypttab = fp.read()
        tokens = re.split(r'\s+', crypttab)
        self.assertEqual(cryptoswap, tokens[0])
        self.assertEqual("/dev/urandom", tokens[2])
        self.assertEqual("swap,initramfs", tokens[3])

        cmd = ["cryptsetup", "status", cryptoswap]
        status = util.subp(cmd, capture=True)[0]
        for line in status.splitlines():
            key, _, value = line.strip().partition(':')
            if key == "type":
                self.assertEqual("PLAIN", value.strip())

    def test_zfs_luks_keystore(self):
        self.img = self.tmp_path('image.img')
        keyfile = self.tmp_path('zfs-luks-keystore-keyfile')
        with open(keyfile, "w") as fp:
            fp.write(self.random_string())
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, create=True, size='200M', ptable='gpt')
        p1 = config.add_part(number=1, offset=1 << 20, size=198 << 20)
        poolname = self.random_string()
        config._add(
            type='zpool',
            pool=poolname,
            vdevs=[p1["id"]],
            mountpoint="/",
            pool_properties=dict(ashift=12, autotrim="on", version=None),
            encryption_style="luks_keystore",
            keyfile=keyfile,
        )
        self.run_bm(config.render())

        keystore_volume = f"/dev/zvol/{poolname}/keystore"
        dm_name = f"keystore-{poolname}"
        dmpath = f"/dev/mapper/{dm_name}"
        util.subp([
            "cryptsetup", "open", "--type", "luks", keystore_volume,
            dm_name, "--key-file", keyfile,
        ])
        mntdir = self.tmp_dir()
        try:
            with util.mount(dmpath, mntdir):
                system_key = Path(mntdir) / "system.key"
                st_mode = system_key.stat().st_mode
                self.assertEqual(0o400, stat.S_IMODE(st_mode))
                self.assertTrue(stat.S_ISREG(st_mode))
        finally:
            util.subp(["cryptsetup", "close", dmpath])

    @parameterized.expand(((1,), (2,)))
    def test_msftres(self, sv):
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=sv)
        config.add_image(path=self.img, create=True, size='20M',
                         ptable='gpt')
        config.add_part(number=1, offset=1 << 20, size=1 << 20, flag='msftres')
        self.run_bm(config.render())

        self.assertPartitions(
            PartData(number=1, offset=1 << 20, size=1 << 20, boot=False,
                     partition_type='E3C9E316-0B5C-4DB8-817D-F92DF00215AE'))

    def test_quick_zero_loop(self):
        """ attempt to provoke ordering problems in partition wiping with
            superblock-recursive """
        self.img = self.tmp_path('image.img')
        config = StorageConfigBuilder(version=2)
        config.add_image(path=self.img, create=True, size='20M',
                         ptable='gpt', wipe='superblock-recursive')
        parts = []
        for i in range(1, 19):
            config.add_part(number=i, offset=i << 20, size=1 << 20)
            parts.append(PartData(number=1, offset=i << 20, size=1 << 20))
        for run in range(5):
            self.run_bm(config.render())
            self.assertPartitions(*parts)
