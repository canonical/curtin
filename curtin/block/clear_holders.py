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

from curtin import (block, util, udev)
from curtin.log import LOG

import functools
import os


def split_vg_lv_name(full):
    """
    Break full logical volume device name into volume group and logical volume
    """
    # FIXME: when block.lvm is written this should be moved there
    # just using .split('-') will not work because when a logical volume or
    # volume group has a name containing a '-', '--' is used to denote this in
    # the /sys/block/{name}/dm/name (LP:1591573)

    # handle newline if present
    full = full.strip()

    # get index of first - not followed by or preceeded by another -
    indx = None
    try:
        indx = next(i + 1 for (i, c) in enumerate(full[1:-1])
                    if c == '-' and '-' not in (full[i], full[i + 2]))
    except StopIteration:
        pass

    if not indx:
        raise ValueError("vg-lv full name does not contain a '-': {}'".format(
            full))

    return (full[:indx].replace('--', '-'),
            full[indx + 1:].replace('--', '-'))


def get_bcache_using_dev(device):
    """
    Get the /sys/fs/bcache/ path of the bcache volume using specified device

    The specified device can either be a device held by bcache or the bcache
    device itself

    Device can be specified either as a path in /dev or a path in /sys/block
    """
    # FIXME: when block.bcache is written this should be moved there
    sysfs_path = block.sys_block_path(device)
    bcache_cache_d = os.path.realpath(os.path.join(
        sysfs_path, 'bcache', 'cache'))
    if not os.path.exists(bcache_cache_d):
        raise OSError('Could not find /sys/fs path for bcache: {}'
                      .format(sysfs_path))
    return bcache_cache_d


def shutdown_bcache(state, device):
    """
    Shut down bcache for specified bcache device or bcache backing/cache
    device

    Will not io errors but will collect and return them

    May return a function that should be run by the caller to wipe out metadata
    """
    try:
        bcache_sysfs = get_bcache_using_dev(device)
    except OSError:
        # bcache not running, so nothing need be done
        return
    LOG.debug('stopping bcache at: {}'.format(bcache_sysfs))
    with open(os.path.join(bcache_sysfs, 'stop'), 'w') as fp:
        fp.write('1')


def shutdown_mdadm(state, device):
    """
    Shutdown specified mdadm device. Device can be either a blockdev or a path
    in /sys/block

    May raise process execution errors, but these should be allowed, since this
    function should not have been run by clear_holders unless there was a valid
    mdadm device to shut down
    """
    blockdev = block.dev_path(block.dev_short(device))
    LOG.debug('using mdadm.mdadm_stop on dev: {}'.format(blockdev))
    block.mdadm.mdadm_stop(blockdev)
    block.mdadm.mdadm_remove(blockdev)


def shutdown_lvm(state, device):
    """
    Shutdown specified lvm device. Device may be given as a path in /sys/block
    or in /dev

    Will not raise io errors, but will collect and return them

    May return a function that should be run by the caller to wipe out metadata
    """
    device = block.sys_block_path(device)
    # lvm devices have a dm directory that containes a file 'name' containing
    # '{volume group}-{logical volume}'. The volume can be freed using lvremove
    (vg_name, lv_name) = (None, None)
    name_file = os.path.join(device, 'dm', 'name')
    full_name = util.load_file(name_file)
    (vg_name, lv_name) = split_vg_lv_name(full_name)
    # use two --force flags here in case the volume group that this lv is
    # attached two has been damaged by a disk being wiped or other storage
    # volumes being shut down.
    # if something has already destroyed the logical volume, such as another
    # partition being forcibly removed from the volume group, then lvremove
    # will return 5.
    # if this happens, then we should not halt installation, it
    # is most likely not an issue. However, we will record the error and pass
    # it up the clear_holders stack so that if other clear_holders calls fail
    # and this is a potential cause it will be written to install log
    LOG.debug('running lvremove on {}/{}'.format(vg_name, lv_name))
    util.subp(['lvremove', '--force', '--force',
               '{}/{}'.format(vg_name, lv_name)], rcs=[0, 5])


def wipe_superblock(state, device):
    """
    Wrapper for block.wipe_volume compatible with shutdown function interface
    """
    device = block.dev_path(block.dev_short(device))
    LOG.info('wiping superblock on %s', device)
    block.wipe_volume(device, mode='superblock')


def _subfile_exists(subfile, basedir):
    """tests if 'subfile' exists under basedir"""
    return os.path.exists(os.path.join(basedir, subfile))


# types of devices that could be encountered by clear holders and functions to
# identify them and shut them down
DEV_TYPES = {
    'partition': {'shutdown': wipe_superblock,
                  'ident': functools.partial(_subfile_exists, 'partition')},
    # FIXME: below is not the best way to identify lvm, it should be replaced
    #        once there is a method in place to differentiate plain
    #        devicemapper from lvm controlled devicemapper
    'lvm': {'shutdown': shutdown_lvm,
            'ident': functools.partial(_subfile_exists, 'dm')},
    'raid': {'shutdown': shutdown_mdadm,
             'ident': functools.partial(_subfile_exists, 'md')},
    'bcache': {'shutdown': shutdown_bcache,
               'ident': functools.partial(_subfile_exists, 'bcache')},
    'disk': {'ident': lambda x: False, 'shutdown': wipe_superblock},
}

# anything that is not identified can assumed to be a 'disk' or similar
# which does not requre special action to shutdown
DEFAULT_DEV_TYPE = 'disk'


def get_holders(device):
    """
    Look up any block device holders, return list of knames
    Can handle devices and partitions as devnames (vdb, md0, vdb7)
    Can also handle devices and partitions by path in /sys/
    Will not raise io errors, but will collect and return them
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
    holder_paths = ([block.sys_block_path(h) for h in get_holders(device)] +
                    block.get_sysfs_partitions(device))
    dev_type = next((k for k, v in DEV_TYPES.items() if v['ident'](device)),
                    DEFAULT_DEV_TYPE)
    return {
        'device': device, 'dev_type': dev_type,
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
        result = [block.dev_short(tree['device'])]
        holders = tree['holders']
        for (holder_no, holder) in enumerate(holders):
            spacer_style = spacers[min(len(holders) - (holder_no + 1), 1)]
            subtree_lines = format_tree(holder)
            for (line_no, line) in enumerate(subtree_lines):
                result.append(spacer_style[min(line_no, 1)] + line)
        return result

    return '\n'.join(format_tree(holders_tree))


def assert_clear(base_paths):
    """Check if all paths in base_paths are clear to use"""

    def holder_types(tree):
        # get flattened list of all holder types present in holders_tree and
        # the device they are present on
        types = [(tree['dev_type'], tree['device'])]
        for holder in tree['holders']:
            types.extend(holder_types(holder))
        return types

    valid = ('disk', 'partition')
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]
    base_paths = [block.sys_block_path(path) for path in base_paths]
    for holders_tree in [gen_holders_tree(p) for p in base_paths]:
        if any(holder_type not in valid and path not in base_paths
               for (holder_type, path) in holder_types(holders_tree)):
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
        shutdown_function({}, dev_info['device'])
        udev.udevadm_settle()
