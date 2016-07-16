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

import errno
import functools
import glob
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
        raise OSError(2, 'Could not find /sys/fs path for bcache: {}'
                      .format(sysfs_path))
    return bcache_cache_d


def shutdown_bcache(device):
    """
    Shut down bcache for specified bcache device or bcache backing/cache
    device

    Will not io errors but will collect and return them

    May return a function that should be run by the caller to wipe out metadata
    """
    catcher = util.ForgiveIoError()
    bcache_sysfs = None
    with catcher:
        bcache_sysfs = get_bcache_using_dev(device)
    if bcache_sysfs is None:
        return (None, catcher.caught)

    # emit wipe functions for all involved devices, since the bcache holder
    # will dissappear soon, and we will lose the data to determine which disks
    # need to be wiped
    wipe_devs = set()
    glob_expr = os.path.join(bcache_sysfs, 'bdev*/dev/slaves/*')
    with catcher:
        wipe_devs.update(block.dev_path(block.dev_short(p))
                         for p in glob.glob(glob_expr))
    # generate wipe functions
    LOG.debug('shutdown_bcache needs to wipe: {}'.format(wipe_devs))
    wipe = [functools.partial(block.wipe_volume, dev, mode='superblock')
            for dev in wipe_devs]

    # stop the bcache device via sysfs
    LOG.debug('stopping bcache at: {}'.format(bcache_sysfs))
    with catcher:
        util.write_file(os.path.join(bcache_sysfs, 'stop'), '1')

    return (wipe, catcher.caught)


def shutdown_mdadm(device):
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
    return (None, [])


def shutdown_lvm(device):
    """
    Shutdown specified lvm device. Device may be given as a path in /sys/block
    or in /dev

    Will not raise io errors, but will collect and return them

    May return a function that should be run by the caller to wipe out metadata
    """
    device = block.sys_block_path(device)
    # lvm devices have a dm directory that containes a file 'name' containing
    # '{volume group}-{logical volume}'. The volume can be freed using lvremove
    catcher = util.ForgiveIoError()
    with catcher:
        (vg_name, lv_name) = (None, None)
        name_file = os.path.join(device, 'dm', 'name')
        full_name = util.load_file(name_file)
        try:
            (vg_name, lv_name) = split_vg_lv_name(full_name)
        except ValueError:
            pass

    if vg_name is None or lv_name is None:
        err = OSError(errno.ENOENT, 'file: {} missing or has invalid contents'
                      .format(name_file))
        catcher.add_exc(err)
        return (None, catcher.caught)

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
    cmd = ['lvremove', '--force', '--force', '{}/{}'.format(vg_name, lv_name)]
    LOG.debug('running lvremove on {}/{}'.format(vg_name, lv_name))
    try:
        util.subp(cmd)
    except util.ProcessExecutionError as e:
        catcher.add_exc(e)
        if not (hasattr(e, 'exit_code') and e.exit_code == 5):
            raise

    # The underlying volume can be freed of its lvm metadata using
    # block.wipe_volume with wipe mode 'pvremove'
    blockdev = block.dev_path(block.dev_short(device))
    wipe_func = functools.partial(block.wipe_volume, blockdev, mode='pvremove')
    return (wipe_func, catcher.caught)


def _subfile_exists(subfile, basedir):
    """tests if 'subfile' exists under basedir"""
    return os.path.exists(os.path.join(basedir, subfile))


# types of devices that could be encountered by clear holders and functions to
# identify them and shut them down
# both ident and shutdown methods should have a signature taking 1 parameter
# for sysfs path to device to operate on
# a none type for shutdown means take no action
DEV_TYPES = (
    {'name': 'partition', 'shutdown': None,
     'ident': functools.partial(_subfile_exists, 'partition')},
    # FIXME: below is not the best way to identify lvm, it should be replaced
    #        once there is a method in place to differentiate plain
    #        devicemapper from lvm controlled devicemapper
    {'name': 'lvm', 'shutdown': shutdown_lvm,
     'ident': functools.partial(_subfile_exists, 'dm')},
    {'name': 'raid', 'shutdown': shutdown_mdadm,
     'ident': functools.partial(_subfile_exists, 'md')},
    {'name': 'bcache', 'shutdown': shutdown_bcache,
     'ident': functools.partial(_subfile_exists, 'bcache')},
)

# anything that is not identified can assumed to be a 'disk' or similar
# which does not requre special action to shutdown
DEFAULT_DEV_TYPE = {'name': 'disk', 'ident': lambda x: True, 'shutdown': None}


def get_holders(device):
    """
    Look up any block device holders, return list of knames
    Can handle devices and partitions as devnames (vdb, md0, vdb7)
    Can also handle devices and partitions by path in /sys/
    Will not raise io errors, but will collect and return them
    """
    holders = []
    catcher = util.ForgiveIoError()
    sysfs_path = None

    # get sysfs path if missing
    # block.sys_block_path works when given a /sys or /dev path
    with catcher:
        sysfs_path = block.sys_block_path(device)

    # block.sys_block_path may have failed
    if not sysfs_path:
        LOG.info('get_holders: did not find sysfs path for %s', device)
        return (holders, catcher.caught)

    # get holders
    with catcher:
        holders = os.listdir(os.path.join(sysfs_path, 'holders'))

    LOG.debug("devname '%s' had holders: %s", device, ','.join(holders))
    # return (holders, catcher.caught)
    return holders


def gen_holders_tree(device):
    """
    starting from a base device generate a tree representing the current
    storage hirearchy

    can take input as path in /dev /sys/block or a knam
    """
    device = block.sys_block_path(device)
    res = {
        'device': device,
        'holders': [gen_holders_tree(h) for h in
                    ([block.sys_block_path(h) for h in get_holders(device)] +
                     block.get_sysfs_partitions(device))],
        'dev_type': next((t for t in DEV_TYPES if t['ident'](device)),
                         DEFAULT_DEV_TYPE),
    }
    return res


def merge_holders_tree(holders_trees):
    """
    merge holders tress together, detecting if holding devices are sharing
    multiple base devices, such as a lvm partition across multiple backing
    devices
    """
    pass


def clear_holders(device):
    """
    Shutdown all storage layers holding specified device.
    Device can be specified either with a path in /dev or /sys/block

    Will supress all io errors encountered while removing holders, as there may
    be situations in which shutting down one holding device may remove another,
    causing it to disappear. Once all handlers have been run, check if all
    holders have been shut down.

    Returns True is all holders could be shut down sucessfully, False
    otherwise. Also returns a list of all IOErrors encountered and ignored
    while running.
    """
    catcher = util.ForgiveIoError()

    # block.sys_block_path works when given a /sys path as well
    with catcher:
        device = block.sys_block_path(device)

    (holders, _err) = get_holders(device)
    catcher.add_exc(_err)
    LOG.info("clear_holders running on '%s', with holders '%s'" %
             (device, holders))

    # go through all found holders, get their real path, detect what type they
    # are, and shut them down
    for holder in holders:
        # get realpath, skip holder if cannot get it, as holder may be gone
        # already
        holder_realpath = None
        with catcher:
            holder_realpath = os.path.realpath(os.path.join(
                device, "holders", holder))
        if not holder_realpath:
            continue

        # run clear holders on all found holders, if it fails, give up
        (res, _err) = clear_holders(holder_realpath)
        catcher.add_exc(_err)
        if not res:
            return (False, catcher.caught)

    # detect holder type, if holder returns any functions to be called for disk
    # wiping, run them, and log the output
    wipe_cmds = []
    holder_types = {
        'dm': shutdown_lvm,
        'md': shutdown_mdadm,
        'bcache': shutdown_bcache,
    }
    for (type_name, handler) in holder_types.items():
        if os.path.exists(os.path.join(device, type_name)):
            (wipe_cmd, _err) = handler(device)
            catcher.add_exc(_err)
            if wipe_cmd is not None:
                if isinstance(wipe_cmd, (list, tuple)):
                    wipe_cmds.extend(wipe_cmd)
                else:
                    wipe_cmds.append(wipe_cmd)

    # if any wipe commands were generated by clear handlers, run them
    # they are run here instead of during shutdown functions since it
    # is possible that a single device may have multiple layers on top of it
    # that need to be shutdown correctly before wiping
    for wipe_cmd in wipe_cmds:
        with catcher:
            wipe_cmd()

    # make sure changes are fully applied before looking for remaining holders
    udev.udevadm_settle()

    # only return true if there are no remaining holders or if the path to this
    # device in /sys/block no longer exists because it was shut down
    (holders, _err) = get_holders(device)
    catcher.add_exc(_err)
    res = ((not os.path.exists(device)) or
           (len(holders) == 0 and (len(_err) == 0)))
    if not res:
        catcher.add_exc(OSError('device: {} still has holders: {}'.format(
            device, holders)))
    return (res, catcher.caught)


def check_clear(device):
    """
    Run clear_holders on device.

    If clear_holders fails, dump all exceptions caught by clear_holders to log
    and raise an OSError
    """
    (res, _err) = clear_holders(device)
    log_fn = LOG.warn if res else LOG.error
    for e in _err:
        log_fn('clear_holders encountered error: {}'.format(e))
    if not res:
        raise OSError('could not clear holders for device: {}'.format(device))
    LOG.info('clear_holders finished successfully on device: {}'
             .format(device))
