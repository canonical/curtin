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


def get_holders(devname=None, sysfs_path=None):
    """
    Look up any block device holders.
    Can handle devices and partitions as devnames (vdb, md0, vdb7)
    Can also handle devices and partitions by path in /sys/
    Will not raise io errors, but will collect and return them
    """
    if not devname and not sysfs_path:
        raise ValueError("either devname or sysfs_path must be supplied")

    holders = []
    catcher = util.ForgiveIoError()

    # get sysfs path if missing
    if not sysfs_path:
        with catcher:
            sysfs_path = block.sys_block_path(devname)

    # block.sys_block_path may have failed
    if not sysfs_path:
        LOG.debug('get_holders: did not find sysfs path for %s', devname)
        return (holders, catcher.caught)

    # get holders
    with catcher:
        holders = os.listdir(os.path.join(sysfs_path, 'holders'))

    LOG.debug("devname '%s' had holders: %s", devname, ','.join(holders))
    return (holders, catcher.caught)
