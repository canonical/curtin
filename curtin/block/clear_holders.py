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

from curtin import (block, util)
from curtin.log import LOG

import os


def shutdown_bcache(device):
    pass


def shutdown_mdadm(device):
    pass


def shutdown_lvm(device):
    pass


def get_holders(device):
    """
    Look up any block device holders.
    Can handle devices and partitions as devnames (vdb, md0, vdb7)
    Can also handle devices and partitions by path in /sys/
    Will not raise io errors, but will collect and return them
    """
    holders = []
    catcher = util.ForgiveIoError()

    # get sysfs path if missing
    # block.sys_block_path works when given a /sys or /dev path
    with catcher:
        sysfs_path = block.sys_block_path(device)

    # block.sys_block_path may have failed
    if not sysfs_path:
        LOG.debug('get_holders: did not find sysfs path for %s', device)
        return (holders, catcher.caught)

    # get holders
    with catcher:
        holders = os.listdir(os.path.join(sysfs_path, 'holders'))

    LOG.debug("devname '%s' had holders: %s", device, ','.join(holders))
    return (holders, catcher.caught)


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
    catcher.caught.extend(_err)
    LOG.info("clear_holders running on '%s', with holders '%s'" %
             (device, holders))

    # if there were no holders or the holders dir could not be accessed, skip
    if not holders:
        return (True, catcher.caught)

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
        catcher.caught.extend(_err)
        if not res:
            return (False, catcher.caught)

    # detect holder type
    holder_types = {
        'bcache': shutdown_bcache,
        'md': shutdown_mdadm,
        'dm': shutdown_lvm,
    }
    for (type_name, handler) in holder_types.items():
        if os.path.exists(os.path.join(device, type_name)):
            with catcher:
                handler(device)

    # only return true if there are no remaining holders
    (holders, _err) = get_holders(device)
    return ((len(holders) == 0 and len(_err) == 0), catcher.caught)


def check_clear(device):
    """
    Run clear_holders on device.

    If clear_holders fails, dump all exceptions caught by clear_holders to log
    and raise an OSError
    """
    (res, _err) = clear_holders(device)
    for e in _err:
        LOG.warn('clear_holders encountered error: {}'.format(e))
    if not res:
        raise OSError('could not clear holders for device: {}'.format(e))
