# This file is part of curtin. See LICENSE file for copyright and license info.

from typing import Optional

import attr

from curtin import (block, util)
from curtin.commands.block_meta import (
    disk_handler as disk_handler_v1,
    get_path_to_storage_volume,
    partition_handler as partition_handler_v1,
    partition_verify_sfdisk,
    )
from curtin.log import LOG
from curtin.storage_config import (
    GPT_GUID_TO_CURTIN_MAP,
    )
from curtin.udev import udevadm_settle


@attr.s(auto_attribs=True)
class PartTableEntry:
    number: int
    start: int
    size: int
    type: str
    uuid: Optional[str]
    bootable: bool = False

    def render(self):
        r = f'{self.number}: '
        for a in 'start', 'size', 'type', 'uuid':
            v = getattr(self, a)
            if v is not None:
                r += f' {a}={v}'
        if self.bootable:
            r += ' bootable'
        return r


ONE_MIB_BYTES = 1 << 20
SECTOR_BYTES = 512
ONE_MIB_SECTORS = ONE_MIB_BYTES // SECTOR_BYTES


def align_up(size, block_size):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size):
    return size & ~(block_size - 1)


FLAG_TO_GUID = {
    flag: guid for (guid, (flag, typecode)) in GPT_GUID_TO_CURTIN_MAP.items()
    }


class SFDiskPartTable:

    label = None

    def __init__(self):
        self.entries = []

    def render(self):
        r = ['label: ' + self.label, ''] + [e.render() for e in self.entries]
        return '\n'.join(r)

    def apply(self, device):
        sfdisk_script = self.render()
        LOG.debug("sfdisk input:\n---\n%s\n---\n", sfdisk_script)
        util.subp(['sfdisk', device], data=sfdisk_script.encode('ascii'))
        # sfdisk (as invoked here) uses ioctls to inform the kernel that the
        # partition table has changed so it can add and remove device nodes for
        # the partitions as needed. Unfortunately this is asynchronous: sfdisk
        # can exit before the nodes are present in /dev (or /sys for that
        # matter). Calling "udevadm settle" is slightly incoherent as udev has
        # nothing to do with creating these nodes, but at the same time, udev
        # won't finish processing the events triggered by the sfdisk until
        # after the nodes for the partitions have been updated by the kernel.
        udevadm_settle()


class GPTPartTable(SFDiskPartTable):

    label = 'gpt'

    def add(self, action):
        number = action.get('number', len(self.entries) + 1)
        if 'offset' in action:
            start = int(util.human2bytes(action['offset'])) // SECTOR_BYTES
        else:
            if self.entries:
                prev = self.entries[-1]
                start = align_up(prev.start + prev.size, ONE_MIB_SECTORS)
            else:
                start = ONE_MIB_SECTORS
        size = int(util.human2bytes(action['size'])) // SECTOR_BYTES
        uuid = action.get('uuid')
        type = FLAG_TO_GUID.get(action.get('flag'))
        entry = PartTableEntry(number, start, size, type, uuid)
        self.entries.append(entry)
        return entry


class DOSPartTable(SFDiskPartTable):

    label = 'dos'
    _extended = None

    def add(self, action):
        flag = action.get('flag', None)
        start = action.get('offset', None)
        if start is not None:
            start = int(util.human2bytes(start)) // SECTOR_BYTES
        if flag == 'logical':
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
                        self._extended.start + ONE_MIB_SECTORS,
                        ONE_MIB_SECTORS)
            else:
                number = prev.number + 1
                if start is None:
                    start = align_up(
                        prev.start + prev.size + ONE_MIB_SECTORS,
                        ONE_MIB_SECTORS)
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
                        break
                if prev is None:
                    start = ONE_MIB_SECTORS
                else:
                    start = align_up(prev.start + prev.size, ONE_MIB_SECTORS)
        size = int(util.human2bytes(action['size'])) // SECTOR_BYTES
        FLAG_TO_TYPE = {
            'extended': 'extended',
            'boot': 'uefi',
            'swap': 'swap',
            'lvm': 'lvm',
            'raid': 'raid',
            }
        type = FLAG_TO_TYPE.get(flag)
        if flag == 'boot':
            bootable = True
        else:
            bootable = None
        entry = PartTableEntry(
            number, start, size, type, uuid=None, bootable=bootable)
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
    # If a wipe action is specified, do that.
    if 'wipe' in action:
        return action['wipe']
    # Existing partitions are left alone by default.
    if action.get('preserve', False):
        return None
    # New partitions are wiped by default apart from extended partitions, where
    # it would destroy the EBR.
    if action.get('flag') == 'extended':
        return None
    return 'superblock'


def disk_handler_v2(info, storage_config, handlers):
    disk_handler_v1(info, storage_config, handlers)

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
            partition_handler_v1(action, storage_config, handlers)
        return

    disk = get_path_to_storage_volume(info.get('id'), storage_config)
    table = table_cls()
    preserved_offsets = set()
    wipes = {}

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
            partition_verify_sfdisk(action, sfdisk_info['label'], part_info)
            preserved_offsets.add(entry.start)
        wipes[entry.start] = _wipe_for_action(action)

    # Do a superblock wipe of any partitions that are being deleted.
    for kname, nr, offset, sz in block.sysfs_partition_data(disk):
        offset_sectors = offset // SECTOR_BYTES
        if offset_sectors not in preserved_offsets:
            block.wipe_volume(block.kname_to_path(kname), 'superblock')

    table.apply(disk)

    # Wipe the new partitions as needed.
    for kname, number, offset, size in block.sysfs_partition_data(disk):
        offset_sectors = offset // SECTOR_BYTES
        mode = wipes[offset_sectors]
        if mode is not None:
            block.wipe_volume(block.kname_to_path(kname), mode)


def partition_handler_v2(info, storage_config, handlers):
    pass


# vi: ts=4 expandtab syntax=python
