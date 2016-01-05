#   Copyright (C) 2015 Canonical Ltd.
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

import curtin.config
from curtin import config
from curtin import util
from . import populate_one_subcmd
from curtin.block.mkfs import mkfs_from_config
from curtin.block.mkfs import mkfs as run_mkfs
from curtin.commands.block_meta import get_path_to_storage_volume

from collections import OrderedDict

import os
import sys

CMD_ARGUMENTS = (
    (('devices',
      {'help': 'create filesystem on the target volume(s) or storage config \
                item(s)',
       'metavar': 'DEVICE', 'action': 'store', 'nargs': '+'}),
     (('-f', '--fstype'),
      {'help': 'filesystem type to use. default is ext4',
       'default': 'ext4', 'action': 'store'}),
     (('-c', '--config'),
      {'help': 'read configuration from cfg', 'action': 'append',
       'metavar': 'CONFIG', 'dest': 'cfgopts', 'default': []})
     )
)


def format_blockdev(volume_path, fstype, part_id=None, flags=None):
    if flags is None:
        flags = []
    if part_id is not None:
        flags.append(("label", part_id))
    run_mkfs(volume_path, fstype, flags)


def format_storage_item(info, storage_config):
    volume = info.get('volume')
    if not volume:
        raise ValueError("volume must be specified for partition '%s'" %
                         info.get('id'))

    # Get path to volume
    volume_path = get_path_to_storage_volume(volume, storage_config)

    # Call mkfs_from_config
    mkfs_from_config(volume_path, info)


def mkfs(args):
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    if args.cfgopts:
        for filename in args.cfgopts:
            curtin.config.merge_config_fp(cfg, open(filename))

    if "storage" in cfg:
        storage_config = OrderedDict((d["id"], d) for (i, d) in
                                     enumerate(cfg.get("storage")))
    else:
        storage_config = {}

    for device in args.devices:
        if device in storage_config:
            # Device is in storage config
            format_storage_item(storage_config.get(device), storage_config)
        elif "/dev/" in device and os.path.exists(device):
            # Device is path to block dev
            format_blockdev(device, args.fstype)
        else:
            # Bad argument
            raise ValueError("device '%s' is neither an item in storage "
                             "config nor a block device" % device)

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, mkfs)

# vi: ts=4 expandtab syntax=python
