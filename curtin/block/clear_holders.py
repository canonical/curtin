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

# This module provides a mechanism for shutting down virtual storage layers on
# top of a block device, making it possible to reuse the block device without
# having to reboot the system

from curtin import (block, udev, util)
from curtin.block import lvm
from curtin.log import LOG

import os


def get_bcache_using_dev(device):
    """
    Get the /sys/fs/bcache/ path of the bcache volume using specified device
    """
    # FIXME: when block.bcache is written this should be moved there
    sysfs_path = block.sys_block_path(device)
    bcache_cache_d = os.path.realpath(os.path.join(
        sysfs_path, 'bcache', 'cache'))
    if not os.path.exists(bcache_cache_d):
        raise OSError('Could not find /sys/fs path for bcache: {}'
                      .format(sysfs_path))
    return bcache_cache_d


def shutdown_bcache(device):
    """
    Shut down bcache for specified bcache device
    """
    try:
        bcache_sysfs = get_bcache_using_dev(device)
    except OSError:
        # bcache not running, so nothing need be done
        # this happens whenever we are shutting down a bcache system where a
        # single cache device is used on two backing devices, because the same
        # bcache device in /sys/fs/bcache/ represents itself as two block devs
        # in /sys/block
        LOG.warn("shutdown_bcache did not find /sys/fs/ path for bcache dev: "
                 "'%s'. assuming caused by shared cache device, continuing",
                 device)
        return
    LOG.debug('stopping bcache at: {}'.format(bcache_sysfs))
    with open(os.path.join(bcache_sysfs, 'stop'), 'w') as fp:
        fp.write('1')


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
    LOG.debug('running lvremove on {}/{}'.format(vg_name, lv_name))
    util.subp(['lvremove', '--force', '--force',
               '{}/{}'.format(vg_name, lv_name)], rcs=[0, 5])
    # if that was the last lvol in the volgroup, get rid of volgroup
    if len(lvm.get_lvols_in_volgroup(vg_name)) == 0:
        util.subp(['vgremove', '--force', '--force', vg_name], rcs=[0, 5])
    # refresh lvmetad
    lvm.lvm_scan()


def shutdown_mdadm(device):
    """
    Shutdown specified mdadm device.
    """
    blockdev = block.dev_path(block.dev_short(device))
    LOG.debug('using mdadm.mdadm_stop on dev: {}'.format(blockdev))
    block.mdadm.mdadm_stop(blockdev)
    block.mdadm.mdadm_remove(blockdev)


def wipe_superblock(device):
    """
    Wrapper for block.wipe_volume compatible with shutdown function interface
    """
    blockdev = block.dev_path(block.dev_short(device))
    LOG.info('wiping superblock on %s', device)
    # when operating on a disk that used to have a dos part table with an
    # extended partition, attempting to wipe the extended partition will result
    # in a ENXIO err even though the actual device does exist
    # if the block dev is possibly an extended partition ignore the err
    try:
        block.wipe_volume(blockdev, mode='superblock')
    except (OSError, IOError) as err:
        # if not file not found then something went wrong
        if not util.is_file_not_found_exc(err):
            raise
        # trusty report 0 for size of extended part, newer report 2 sectors
        # partition file must exist to be a partition
        # partition number must be <= 4 to be on a dos disk
        if not (int(util.load_file(os.path.join(device, 'size'))) in [0, 2] and
                os.path.exists(os.path.join(device, 'partition')) and
                int(util.load_file(os.path.join(device, 'partition'))) <= 4):
            raise


def identify_lvm(device):
    """determine if specified device is a lvm device"""
    return block.path_to_kname(device).startswith('dm')


def identify_mdadm(device):
    """determine if specified device is a mdadm device"""
    return block.path_to_kname(device).startswith('md')


def identify_bcache(device):
    """determine if specified device is a bcache device"""
    return block.path_to_kname(device).startswith('bcache')


def identify_partition(device):
    """determine if specified device is a partition"""
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
    dev_name = block.dev_short(device)
    holder_paths = ([block.sys_block_path(h) for h in get_holders(device)] +
                    block.get_sysfs_partitions(device))
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
    """draw a nice dirgram of the holders tree"""
    # spacer styles based on output of 'tree --charset=ascii'
    spacers = (('`-- ', ' ' * 4), ('|-- ', '|' + ' ' * 3))

    def format_tree(tree):
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
    """Check if all paths in base_paths are clear to use"""
    valid = ('disk', 'partition')
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]
    base_paths = [block.sys_block_path(path) for path in base_paths]
    for holders_tree in [gen_holders_tree(p) for p in base_paths]:
        if any(holder_type not in valid and path not in base_paths
               for (holder_type, path) in get_holder_types(holders_tree)):
            raise OSError('Storage not clear, remaining:\n{}'
                          .format(format_holders_tree(holders_tree)))


def clear_holders(base_paths):
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
        LOG.info("shutdown running on holder type: '%s' syspath: '%s'",
                 dev_info['dev_type'], dev_info['device'])
        shutdown_function(dev_info['device'])
        udev.udevadm_settle()


def start_clear_holders_deps():
    """prepare system for clear holders to be able to scan old devices"""
    # a mdadm scan has to be started in case there is a md device that needs to
    # be detected
    block.mdadm.mdadm_assemble(scan=True)
    # the bcache module needs to be present to properly detect bcache devs
    util.subp(['modprobe', 'bcache'])


# anything that is not identified can assumed to be a 'disk' or similar
DEFAULT_DEV_TYPE = 'disk'

# types of devices that could be encountered by clear holders and functions to
# identify them and shut them down
DEV_TYPES = {
    'partition': {'shutdown': wipe_superblock, 'ident': identify_partition},
    # FIXME: below is not the best way to identify lvm, it should be replaced
    #        once there is a method in place to differentiate plain
    #        devicemapper from lvm controlled devicemapper
    'lvm': {'shutdown': shutdown_lvm, 'ident': identify_lvm},
    'raid': {'shutdown': shutdown_mdadm, 'ident': identify_mdadm},
    'bcache': {'shutdown': shutdown_bcache, 'ident': identify_bcache},
    'disk': {'ident': lambda x: False, 'shutdown': wipe_superblock},
}
