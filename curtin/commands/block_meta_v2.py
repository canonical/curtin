# This file is part of curtin. See LICENSE file for copyright and license info.

import os
from typing import (
    List,
    Optional,
    )

import attr

from curtin import (block, compat, util)
from curtin.commands.block_meta import (
    _get_volume_fstype,
    disk_handler as disk_handler_v1,
    get_path_to_storage_volume,
    make_dname,
    partition_handler as partition_handler_v1,
    verify_ptable_flag,
    verify_size,
    )
from curtin.log import LOG
from curtin.storage_config import (
    GPT_GUID_TO_CURTIN_MAP,
    MBR_TYPE_TO_CURTIN_MAP,
    select_configs,
    )
from curtin.udev import udevadm_settle


def to_utf8_hex_notation(string: str) -> str:
    ''' Convert a string into a valid ASCII string where all characters outside
    the alphanumerical range (according to bytes.isalnum()) are translated to
    their corresponding \\x notation. E.g.:
        to_utf8_hex_notation("hello") => "hello"
        to_utf8_hex_notation("réservée") => "r\\xc3\\xa9serv\\xc3\\xa9e"
        to_utf8_hex_notation("sp ace") => "sp\\x20ace"
    '''
    result = ''
    for c in bytearray(string, 'utf-8'):
        if bytes([c]).isalnum():
            result += bytes([c]).decode()
        else:
            result += f'\\x{c:02x}'
    return result


@attr.s(auto_attribs=True)
class PartTableEntry:
    # The order listed here matches the order sfdisk represents these fields
    # when using the --dump argument.
    number: int
    start: int
    size: int
    type: str
    uuid: Optional[str]
    # name here is the sfdisk term - quoted descriptive text of the partition -
    # not to be confused with what make_dname() does.
    # Offered in the partition command as 'partition_name'.
    name: Optional[str]
    attrs: Optional[List[str]]
    bootable: bool = False

    def render(self):
        r = '{}: '.format(self.number)
        for a in 'start', 'size', 'type', 'uuid':
            v = getattr(self, a)
            if v is not None:
                r += ' {}={}'.format(a, v)
        if self.name is not None:
            # Partition names are basically free-text fields. Injecting some
            # characters such as '"', '\' and '\n' will result in lots of
            # trouble.  Fortunately, sfdisk supports \x notation, so we can
            # rely on it.
            r += ' name="{}"'.format(to_utf8_hex_notation(self.name))
        if self.attrs:
            r += ' attrs="{}"'.format(' '.join(self.attrs))
        if self.bootable:
            r += ' bootable'
        return r

    def preserve(self, part_info):
        """for an existing partition,
        initialize unset values to current values"""
        for a in 'uuid', 'name':
            if getattr(self, a) is None:
                setattr(self, a, part_info.get(a))
        attrs = part_info.get('attrs')
        if attrs is not None and self.attrs is None:
            self.attrs = attrs.split(' ')


ONE_MIB_BYTES = 1 << 20


def align_up(size, block_size):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size):
    return size & ~(block_size - 1)


def resize_ext(path, size):
    util.subp(['e2fsck', '-p', '-f', path])
    size_k = size // 1024
    util.subp(['resize2fs', path, '{}k'.format(size_k)])


def resize_ntfs(path, size):
    util.subp(['ntfsresize', '--no-progress-bar', '-f', '-s', str(size), path],
              data=b'y\n',
              capture=True)


def perform_resize(kname, resize):
    path = block.kname_to_path(kname)
    fstype = resize['fstype']
    size = resize['size']
    direction = resize['direction']
    LOG.debug('Resizing %s of type %s %s to %s',
              path, fstype, direction, size)
    resizers[fstype](path, size)


resizers = {
    'ext2': resize_ext,
    'ext3': resize_ext,
    'ext4': resize_ext,
    'ntfs': resize_ntfs,
}


FLAG_TO_GUID = {
    flag: guid for (guid, flag) in GPT_GUID_TO_CURTIN_MAP.items()
    }
FLAG_TO_MBR_TYPE = {
    flag: typecode for (typecode, flag) in MBR_TYPE_TO_CURTIN_MAP.items()
    }
FLAG_TO_MBR_TYPE['extended'] = '05'


class SFDiskPartTable:

    label = None

    def __init__(self, sector_bytes):
        self.entries = []
        self.label_id = None
        self._sector_bytes = sector_bytes
        if ONE_MIB_BYTES % sector_bytes != 0:
            raise Exception(
                f"sector_bytes {sector_bytes} does not divide 1MiB, cannot "
                "continue!")
        self.one_mib_sectors = ONE_MIB_BYTES // sector_bytes

    def bytes2sectors(self, amount):
        return int(util.human2bytes(amount)) // self._sector_bytes

    def sectors2bytes(self, amount):
        return amount * self._sector_bytes

    def render(self):
        r = ['label: ' + self.label]
        if self.label_id is not None:
            r.extend(['label-id: ' + self.label_id])
        r.extend(self._headers())
        r.extend([''])
        r.extend([e.render() for e in self.entries])
        return '\n'.join(r)

    def apply(self, device):
        sfdisk_script = self.render()
        LOG.debug("sfdisk input:\n---\n%s\n---\n", sfdisk_script)
        cmd = ['sfdisk', '--no-reread', device]
        if compat.supports_sfdisk_no_tell_kernel():
            cmd.append('--no-tell-kernel')
        util.subp(cmd, data=sfdisk_script.encode('ascii'))
        util.subp(['partprobe', device])
        # sfdisk and partprobe (as invoked here) use ioctls to inform the
        # kernel that the partition table has changed so it can add and remove
        # device nodes for the partitions as needed. Unfortunately this is
        # asynchronous: we can return before the nodes are present in /dev (or
        # /sys for that matter). Calling "udevadm settle" is slightly
        # incoherent as udev has nothing to do with creating these nodes, but
        # at the same time, udev won't finish processing the events triggered
        # by the sfdisk until after the nodes for the partitions have been
        # updated by the kernel.
        udevadm_settle()

    def preserve(self, sfdisk_info):
        """for an existing disk,
        initialize unset values to current values"""
        if sfdisk_info is None:
            return
        if self.label_id is None:
            self.label_id = sfdisk_info.get('id')
        self._preserve(sfdisk_info)

    def _preserve(self, sfdisk_info):
        """table-type specific value preservation"""
        pass

    def _headers(self):
        """table-type specific headers for render()"""
        return []


class GPTPartTable(SFDiskPartTable):

    label = 'gpt'

    def __init__(self, sector_bytes):
        #                           json name    script name
        self.first_lba = None     # firstlba     first-lba
        self.last_lba = None      # lastlba      last-lba
        self.table_length = None  # table-length table-length
        super().__init__(sector_bytes)

    def add(self, action):
        number = action.get('number', len(self.entries) + 1)
        if 'offset' in action:
            start = self.bytes2sectors(action['offset'])
        else:
            if self.entries:
                prev = self.entries[-1]
                start = align_up(prev.start + prev.size, self.one_mib_sectors)
            else:
                start = self.one_mib_sectors
        size = self.bytes2sectors(action['size'])
        uuid = action.get('uuid')
        type = action.get('partition_type',
                          FLAG_TO_GUID.get(action.get('flag')))
        name = action.get('partition_name')
        attrs = action.get('attrs')
        entry = PartTableEntry(
            number, start, size, type,
            uuid=uuid, name=name, attrs=attrs)
        self.entries.append(entry)
        return entry

    def _preserve(self, sfdisk_info):
        if self.first_lba is None:
            self.first_lba = sfdisk_info.get('firstlba')
        if self.last_lba is None:
            self.last_lba = sfdisk_info.get('lastlba')
        if self.table_length is None:
            table_length = sfdisk_info.get('table-length')
            if table_length is not None:
                self.table_length = int(table_length)

    def _headers(self):
        r = []
        first_lba = self.first_lba
        if first_lba is None:
            min_start = min(
                [entry.start for entry in self.entries], default=2048)
            if min_start < 2048:
                first_lba = min_start
        if first_lba is not None:
            r.extend(['first-lba: ' + str(first_lba)])
        if self.last_lba is not None:
            r.extend(['last-lba: ' + str(self.last_lba)])
        if self.table_length is not None:
            r.extend(['table-length: ' + str(self.table_length)])
        return r


class DOSPartTable(SFDiskPartTable):

    label = 'dos'
    _extended = None

    @staticmethod
    def is_logical(action) -> bool:
        flag = action.get('flag', None)
        if flag == 'logical':
            return True
        # In some scenarios, a swap partition can be in the extended
        # partition. When it does, the flag is set to 'swap'.
        # In some other scenarios, a bootable partition can also be in the
        # extended partition. This is not a supported use-case but is
        # yet another scenario where flag is not set to 'logical'.
        return action.get('number', 0) > 4

    def add(self, action):
        flag = action.get('flag', None)
        start = action.get('offset', None)
        if start is not None:
            start = self.bytes2sectors(start)
        if self.is_logical(action):
            if self._extended is None:
                raise Exception("logical partition without extended partition")
            prev = None
            for entry in reversed(self.entries):
                if entry.number > 4:
                    prev = entry
                    break
            # The number of an logical partition cannot be specified (so the
            # 'number' from the action is completely ignored here) as the
            # partitions are numbered by the order they are found in the linked
            # list of logical partitions. sfdisk just cares that we put a
            # number > 4 here, in fact we could "number" every logical
            # partition as "5" but it's not hard to put the number that the
            # partition will end up getting into the sfdisk input.
            if prev is None:
                number = 5
                if start is None:
                    start = align_up(
                        self._extended.start + self.one_mib_sectors,
                        self.one_mib_sectors)
            else:
                number = prev.number + 1
                if start is None:
                    start = align_up(
                        prev.start + prev.size + self.one_mib_sectors,
                        self.one_mib_sectors)
        else:
            number = action.get('number', len(self.entries) + 1)
            if number > 4:
                raise Exception(
                    "primary partition cannot have number %s" % (number,))
            if start is None:
                prev = None
                for entry in self.entries:
                    if entry.number <= 4:
                        prev = entry
                if prev is None:
                    start = self.one_mib_sectors
                else:
                    start = align_up(
                        prev.start + prev.size,
                        self.one_mib_sectors)
        size = self.bytes2sectors(action['size'])
        type = action.get('partition_type', FLAG_TO_MBR_TYPE.get(flag))
        if flag == 'boot':
            bootable = True
        else:
            bootable = None
        entry = PartTableEntry(
            number, start, size, type,
            uuid=None, name=None, bootable=bootable, attrs=None)
        if flag == 'extended':
            self._extended = entry
        self.entries.append(entry)
        return entry


def _find_part_info(sfdisk_info, offset):
    for part in sfdisk_info['partitions']:
        if part['start'] == offset:
            return part
    else:
        raise Exception(
            "could not find existing partition by offset")


def _wipe_for_action(action):
    # New partitions are wiped by default apart from extended partitions, where
    # it would destroy the EBR.
    if action.get('flag') == 'extended':
        LOG.debug('skipping wipe of extended partition %s' % action['id'])
        return None
    # If a wipe action is specified, do that.
    if 'wipe' in action:
        return action['wipe']
    # Existing partitions are left alone by default.
    if action.get('preserve', False):
        return None
    return 'superblock'


def _prepare_resize(storage_config, part_action, table, part_info):
    if not part_action.get('preserve') or not part_action.get('resize'):
        return None

    devpath = os.path.realpath(part_info['node'])
    fstype = _get_volume_fstype(devpath)
    if fstype == '':
        return None

    volume = part_action['id']
    format_actions = select_configs(storage_config, type='format',
                                    volume=volume)
    if len(format_actions) > 1:
        raise Exception('too many format actions for volume {}'.format(volume))

    if len(format_actions) == 1:
        if not format_actions[0].get('preserve'):
            return None

        target_fstype = format_actions[0]['fstype']
        msg = (
            'Verifying %s format, expecting %s, found %s' % (
             devpath, fstype, target_fstype))
        LOG.debug(msg)
        if fstype != target_fstype:
            raise RuntimeError(msg)

    msg = 'Resize requested for format %s' % (fstype, )
    LOG.debug(msg)
    if fstype not in resizers:
        raise RuntimeError(msg + ' is unsupported')

    start = table.sectors2bytes(part_info['size'])
    end = int(util.human2bytes(part_action['size']))
    if start > end:
        direction = 'down'
    elif start < end:
        direction = 'up'
    else:
        return None

    return {
        'fstype': fstype,
        'size': end,
        'direction': direction,
    }


def verify_offset(devpath, part_action, current_info, table):
    if 'offset' not in part_action:
        return
    current_offset = table.sectors2bytes(current_info['start'])
    action_offset = int(util.human2bytes(part_action['offset']))
    msg = (
        'Verifying %s offset, expecting %s, found %s' % (
         devpath, current_offset, action_offset))
    LOG.debug(msg)
    if current_offset != action_offset:
        raise RuntimeError(msg)


def partition_verify_sfdisk_v2(part_action, label, sfdisk_part_info,
                               storage_config, table):
    devpath = os.path.realpath(sfdisk_part_info['node'])
    if not part_action.get('resize'):
        verify_size(devpath, int(util.human2bytes(part_action['size'])),
                    sfdisk_part_info)
    verify_offset(devpath, part_action, sfdisk_part_info, table)
    expected_flag = part_action.get('flag')
    if expected_flag:
        verify_ptable_flag(devpath, expected_flag, label, sfdisk_part_info)


def disk_handler_v2(info, storage_config, context):
    disk_handler_v1(info, storage_config, context)

    part_actions = []

    for action in storage_config.values():
        if action['type'] == 'partition' and action['device'] == info['id']:
            part_actions.append(action)

    table_cls = {
        'msdos': DOSPartTable,
        'gpt': GPTPartTable,
        }.get(info.get('ptable'))

    if table_cls is None:
        for action in part_actions:
            partition_handler_v1(action, storage_config, context)
        return

    disk = get_path_to_storage_volume(info.get('id'), storage_config)
    (sector_size, _) = block.get_blockdev_sector_size(disk)

    table = table_cls(sector_size)
    preserved_offsets = set()
    wipes = {}
    resizes = {}

    sfdisk_info = None
    for action in part_actions:
        entry = table.add(action)
        if action.get('preserve', False):
            if sfdisk_info is None:
                # Lazily computing sfdisk_info is slightly more efficient but
                # the real reason for doing this is that calling sfdisk_info on
                # a disk with no partition table logs messages that makes the
                # vmtest infrastructure unhappy.
                sfdisk_info = block.sfdisk_info(disk)
            part_info = _find_part_info(sfdisk_info, entry.start)
            partition_verify_sfdisk_v2(action, sfdisk_info['label'], part_info,
                                       storage_config, table)
            entry.preserve(part_info)
            resizes[entry.start] = _prepare_resize(storage_config, action,
                                                   table, part_info)
            preserved_offsets.add(entry.start)
        wipes[entry.start] = _wipe_for_action(action)

    if info.get('preserve'):
        if sfdisk_info is None:
            # See above block comment
            sfdisk_info = block.sfdisk_info(disk)
        table.preserve(sfdisk_info)

    for kname, nr, offset, size in block.sysfs_partition_data(disk):
        offset_sectors = table.bytes2sectors(offset)
        resize = resizes.get(offset_sectors)
        if resize and resize['direction'] == 'down':
            perform_resize(kname, resize)

    for kname, nr, offset, size in block.sysfs_partition_data(disk):
        offset_sectors = table.bytes2sectors(offset)
        if offset_sectors not in preserved_offsets:
            # Do a superblock wipe of any partitions that are being deleted.
            block.wipe_volume(block.kname_to_path(kname), 'superblock')
        elif wipes.get(offset_sectors) is not None:
            # We do a quick wipe of where any new partitions will be,
            # because if there is bcache or other metadata there, this
            # can cause the partition to be used by a storage
            # subsystem and preventing the exclusive open done by the
            # wipe_volume call below. See
            # https://bugs.launchpad.net/curtin/+bug/1718699 for all
            # the gory details.
            LOG.debug('Wiping 1M on %s at offset %s', disk, offset)
            block.zero_file_at_offsets(disk, [offset], exclusive=False)

    table.apply(disk)

    for kname, number, offset, size in block.sysfs_partition_data(disk):
        offset_sectors = table.bytes2sectors(offset)
        wipe = wipes[offset_sectors]
        if wipe is not None:
            # Wipe the new partitions as needed.
            block.wipe_volume(block.kname_to_path(kname), wipe)
        resize = resizes.get(offset_sectors)
        if resize and resize['direction'] == 'up':
            perform_resize(kname, resize)

    # Make the names if needed
    if 'name' in info:
        for action in part_actions:
            if action.get('flag') != 'extended':
                make_dname(action['id'], storage_config)


def partition_handler_v2(info, storage_config, context):
    context.id_to_device[info['id']] = get_path_to_storage_volume(
        info.get('id'), storage_config)


# vi: ts=4 expandtab syntax=python
