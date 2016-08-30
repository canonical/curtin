#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

"""
This module provides a mechanism for shutting down virtual storage layers on
top of a block device, making it possible to reuse the block device without
having to reboot the system
"""

import os

from curtin import (block, udev, util)
from curtin.block import lvm
from curtin.log import LOG


def _define_handlers_registry():
    """
    returns instantiated dev_types
    """
    return {
        'partition': {'shutdown': wipe_superblock,
                      'ident': identify_partition},
        'lvm': {'shutdown': shutdown_lvm, 'ident': identify_lvm},
        'crypt': {'shutdown': shutdown_crypt, 'ident': identify_crypt},
        'raid': {'shutdown': shutdown_mdadm, 'ident': identify_mdadm},
        'bcache': {'shutdown': shutdown_bcache, 'ident': identify_bcache},
        'disk': {'ident': lambda x: False, 'shutdown': wipe_superblock},
    }


def get_dmsetup_uuid(device):
    """
    get the dm uuid for a specified dmsetup device
    """
    blockdev = block.sysfs_to_devpath(device)
    (out, _) = util.subp(['dmsetup', 'info', blockdev, '-C', '-o', 'uuid',
                          '--noheadings'], capture=True)
    return out.strip()


def get_bcache_using_dev(device):
    """
    Get the /sys/fs/bcache/ path of the bcache volume using specified device
    """
    # FIXME: when block.bcache is written this should be moved there
    sysfs_path = block.sys_block_path(device)
    return os.path.realpath(os.path.join(sysfs_path, 'bcache', 'cache'))


def shutdown_bcache(device):
    """
    Shut down bcache for specified bcache device
    """
    bcache_shutdown_message = ('shutdown_bcache running on {} has determined '
                               'that the device has already been shut down '
                               'during handling of another bcache dev. '
                               'skipping'.format(device))
    if not os.path.exists(device):
        LOG.info(bcache_shutdown_message)
        return

    bcache_sysfs = get_bcache_using_dev(device)
    if not os.path.exists(bcache_sysfs):
        LOG.info(bcache_shutdown_message)
        return

    LOG.debug('stopping bcache at: %s', bcache_sysfs)
    util.write_file(os.path.join(bcache_sysfs, 'stop'), '1', mode=None)


def shutdown_lvm(device):
    """
    Shutdown specified lvm device.
    """
    device = block.sys_block_path(device)
    # lvm devices have a dm directory that containes a file 'name' containing
    # '{volume group}-{logical volume}'. The volume can be freed using lvremove
    name_file = os.path.join(device, 'dm', 'name')
    (vg_name, lv_name) = lvm.split_lvm_name(util.load_file(name_file))
    # use two --force flags here in case the volume group that this lv is
    # attached two has been damaged
    LOG.debug('running lvremove on %s/%s', vg_name, lv_name)
    util.subp(['lvremove', '--force', '--force',
               '{}/{}'.format(vg_name, lv_name)], rcs=[0, 5])
    # if that was the last lvol in the volgroup, get rid of volgroup
    if len(lvm.get_lvols_in_volgroup(vg_name)) == 0:
        util.subp(['vgremove', '--force', '--force', vg_name], rcs=[0, 5])
    # refresh lvmetad
    lvm.lvm_scan()


def shutdown_crypt(device):
    """
    Shutdown specified cryptsetup device
    """
    blockdev = block.sysfs_to_devpath(device)
    util.subp(['cryptsetup', 'remove', blockdev], capture=True)


def shutdown_mdadm(device):
    """
    Shutdown specified mdadm device.
    """
    blockdev = block.sysfs_to_devpath(device)
    LOG.debug('using mdadm.mdadm_stop on dev: %s', blockdev)
    block.mdadm.mdadm_stop(blockdev)
    block.mdadm.mdadm_remove(blockdev)


def wipe_superblock(device):
    """
    Wrapper for block.wipe_volume compatible with shutdown function interface
    """
    blockdev = block.sysfs_to_devpath(device)
    # when operating on a disk that used to have a dos part table with an
    # extended partition, attempting to wipe the extended partition will fail
    if block.is_extended_partition(blockdev):
        LOG.info("extended partitions do not need wiping, so skipping: '%s'",
                 blockdev)
    else:
        LOG.info('wiping superblock on %s', blockdev)
        block.wipe_volume(blockdev, mode='superblock')


def identify_lvm(device):
    """
    determine if specified device is a lvm device
    """
    return (block.path_to_kname(device).startswith('dm') and
            get_dmsetup_uuid(device).startswith('LVM'))


def identify_crypt(device):
    """
    determine if specified device is dm-crypt device
    """
    return (block.path_to_kname(device).startswith('dm') and
            get_dmsetup_uuid(device).startswith('CRYPT'))


def identify_mdadm(device):
    """
    determine if specified device is a mdadm device
    """
    return block.path_to_kname(device).startswith('md')


def identify_bcache(device):
    """
    determine if specified device is a bcache device
    """
    return block.path_to_kname(device).startswith('bcache')


def identify_partition(device):
    """
    determine if specified device is a partition
    """
    path = os.path.join(block.sys_block_path(device), 'partition')
    return os.path.exists(path)


def get_holders(device):
    """
    Look up any block device holders, return list of knames
    """
    # block.sys_block_path works when given a /sys or /dev path
    sysfs_path = block.sys_block_path(device)
    # get holders
    holders = os.listdir(os.path.join(sysfs_path, 'holders'))
    LOG.debug("devname '%s' had holders: %s", device, holders)
    return holders


def gen_holders_tree(device):
    """
    generate a tree representing the current storage hirearchy above 'device'
    """
    device = block.sys_block_path(device)
    dev_name = block.path_to_kname(device)
    # the holders for a device should consist of the devices in the holders/
    # dir in sysfs and any partitions on the device. this ensures that a
    # storage tree starting from a disk will include all devices holding the
    # disk's partitions
    holder_paths = ([block.sys_block_path(h) for h in get_holders(device)] +
                    block.get_sysfs_partitions(device))
    # the DEV_TYPE registry contains a function under the key 'ident' for each
    # device type entry that returns true if the device passed to it is of the
    # correct type. there should never be a situation in which multiple
    # identify functions return true. therefore, it will always work to take
    # the device type with the first identify function that returns true as the
    # device type for the current device. in the event that no identify
    # functions return true, the device will be treated as a disk
    # (DEFAULT_DEV_TYPE). the identify function for disk never returns true.
    # the next() builtin in python will not raise a StopIteration exception if
    # there is a default value defined
    dev_type = next((k for k, v in DEV_TYPES.items() if v['ident'](device)),
                    DEFAULT_DEV_TYPE)
    return {
        'device': device, 'dev_type': dev_type, 'name': dev_name,
        'holders': [gen_holders_tree(h) for h in holder_paths],
    }


def plan_shutdown_holder_trees(holders_trees):
    """
    plan best order to shut down holders in, taking into account high level
    storage layers that may have many devices below them

    returns a sorted list of descriptions of storage config entries including
    their path in /sys/block and their dev type

    can accept either a single storage tree or a list of storage trees assumed
    to start at an equal place in storage hirearchy (i.e. a list of trees
    starting from disk)
    """
    # holds a temporary registry of holders to allow cross references
    # key = device sysfs path, value = {} of priority level, shutdown function
    reg = {}

    # normalize to list of trees
    if not isinstance(holders_trees, (list, tuple)):
        holders_trees = [holders_trees]

    def flatten_holders_tree(tree, level=0):
        """
        add entries from holders tree to registry with level key corresponding
        to how many layers from raw disks the current device is at
        """
        device = tree['device']

        # always go with highest level if current device has been
        # encountered already. since the device and everything above it is
        # re-added to the registry it ensures that any increase of level
        # required here will propagate down the tree
        # this handles a scenario like mdadm + bcache, where the backing
        # device for bcache is a 3nd level item like mdadm, but the cache
        # device is 1st level (disk) or second level (partition), ensuring
        # that the bcache item is always considered higher level than
        # anything else regardless of whether it was added to the tree via
        # the cache device or backing device first
        if device in reg:
            level = max(reg[device]['level'], level)

        reg[device] = {'level': level, 'device': device,
                       'dev_type': tree['dev_type']}

        # handle holders above this level
        for holder in tree['holders']:
            flatten_holders_tree(holder, level=level + 1)

    # flatten the holders tree into the registry
    for holders_tree in holders_trees:
        flatten_holders_tree(holders_tree)

    # return list of entry dicts with highest level first
    return [reg[k] for k in sorted(reg, key=lambda x: reg[x]['level'] * -1)]


def format_holders_tree(holders_tree):
    """
    draw a nice dirgram of the holders tree
    """
    # spacer styles based on output of 'tree --charset=ascii'
    spacers = (('`-- ', ' ' * 4), ('|-- ', '|' + ' ' * 3))

    def format_tree(tree):
        """
        format entry and any subentries
        """
        result = [tree['name']]
        holders = tree['holders']
        for (holder_no, holder) in enumerate(holders):
            spacer_style = spacers[min(len(holders) - (holder_no + 1), 1)]
            subtree_lines = format_tree(holder)
            for (line_no, line) in enumerate(subtree_lines):
                result.append(spacer_style[min(line_no, 1)] + line)
        return result

    return '\n'.join(format_tree(holders_tree))


def get_holder_types(tree):
    """
    get flattened list of types of holders in holders tree and the devices
    they correspond to
    """
    types = {(tree['dev_type'], tree['device'])}
    for holder in tree['holders']:
        types.update(get_holder_types(holder))
    return types


def assert_clear(base_paths):
    """
    Check if all paths in base_paths are clear to use
    """
    valid = ('disk', 'partition')
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]
    base_paths = [block.sys_block_path(path) for path in base_paths]
    for holders_tree in [gen_holders_tree(p) for p in base_paths]:
        if any(holder_type not in valid and path not in base_paths
               for (holder_type, path) in get_holder_types(holders_tree)):
            raise OSError('Storage not clear, remaining:\n{}'
                          .format(format_holders_tree(holders_tree)))


def clear_holders(base_paths, try_preserve=False):
    """
    Clear all storage layers depending on the devices specified in 'base_paths'
    A single device or list of devices can be specified.
    Device paths can be specified either as paths in /dev or /sys/block
    Will throw OSError if any holders could not be shut down
    """
    # handle single path
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]

    # get current holders and plan how to shut them down
    holder_trees = [gen_holders_tree(path) for path in base_paths]
    LOG.info('Current device storage tree:\n%s',
             '\n'.join(format_holders_tree(tree) for tree in holder_trees))
    ordered_devs = plan_shutdown_holder_trees(holder_trees)

    # run shutdown functions
    for dev_info in ordered_devs:
        dev_type = DEV_TYPES.get(dev_info['dev_type'])
        shutdown_function = dev_type.get('shutdown')
        if not shutdown_function:
            continue
        if try_preserve and shutdown_function in DATA_DESTROYING_HANDLERS:
            LOG.info('shutdown function for holder type: %s is destructive. '
                     'attempting to preserve data, so not skipping' %
                     dev_info['dev_type'])
            continue
        LOG.info("shutdown running on holder type: '%s' syspath: '%s'",
                 dev_info['dev_type'], dev_info['device'])
        shutdown_function(dev_info['device'])
        udev.udevadm_settle()


def start_clear_holders_deps():
    """
    prepare system for clear holders to be able to scan old devices
    """
    # a mdadm scan has to be started in case there is a md device that needs to
    # be detected. if the scan fails, it is either because there are no mdadm
    # devices on the system, or because there is a mdadm device in a damaged
    # state that could not be started. due to the nature of mdadm tools, it is
    # difficult to know which is the case. if any errors did occur, then ignore
    # them, since no action needs to be taken if there were no mdadm devices on
    # the system, and in the case where there is some mdadm metadata on a disk,
    # but there was not enough to start the array, the call to wipe_volume on
    # all disks and partitions should be sufficient to remove the mdadm
    # metadata
    block.mdadm.mdadm_assemble(scan=True, ignore_errors=True)
    # the bcache module needs to be present to properly detect bcache devs
    # on some systems (precise without hwe kernel) it may not be possible to
    # lad the bcache module bcause it is not present in the kernel. if this
    # happens then there is no need to halt installation, as the bcache devices
    # will never appear and will never prevent the disk from being reformatted
    util.subp(['modprobe', 'bcache'], rcs=[0, 1])


# anything that is not identified can assumed to be a 'disk' or similar
DEFAULT_DEV_TYPE = 'disk'
# handlers that should not be run if an attempt is being made to preserve data
DATA_DESTROYING_HANDLERS = [wipe_superblock]
# types of devices that could be encountered by clear holders and functions to
# identify them and shut them down
DEV_TYPES = _define_handlers_registry()
