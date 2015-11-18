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
from curtin.log import LOG
from curtin import config
from curtin import util
from . import populate_one_subcmd
from curtin.commands.block_meta import get_path_to_storage_volume

from collections import OrderedDict

import os
import sys
import string

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


def format_blockdev(volume_path, fstype, part_id=None):
    if not part_id:
        part_id = volume_path.split("/")[-1]

    # Generate mkfs command and run
    if fstype in ["ext4", "ext3"]:
        if len(part_id) > 16:
            raise ValueError("ext3/4 partition labels cannot be longer than \
                16 characters")
        cmd = ['mkfs.%s' % fstype, '-F', '-q', '-L', part_id, volume_path]
    elif fstype in ["fat12", "fat16", "fat32", "fat"]:
        cmd = ["mkfs.fat"]
        fat_size = fstype.strip(string.ascii_letters)
        if fat_size in ["12", "16", "32"]:
            cmd.extend(["-F", fat_size])
        if len(part_id) > 11:
            raise ValueError("fat partition names cannot be longer than \
                11 characters")
        cmd.extend(["-n", part_id, volume_path])
    else:
        # See if mkfs.<fstype> exists. If so try to run it.
        try:
            util.subp(["which", "mkfs.%s" % fstype])
            cmd = ["mkfs.%s" % fstype, volume_path]
        except util.ProcessExecutionError:
            raise ValueError("fstype '%s' not supported" % fstype)
    LOG.info("formatting volume '%s' with format '%s'" % (volume_path, fstype))
    util.subp(cmd)


def format_storage_item(info, storage_config):
    fstype = info.get('fstype')
    volume = info.get('volume')
    part_id = info.get('id')
    if not volume:
        raise ValueError("volume must be specified for partition '%s'" %
                         info.get('id'))

    # Get path to volume
    volume_path = get_path_to_storage_volume(volume, storage_config)

    # Call format_blockdev
    format_blockdev(volume_path, fstype, part_id=part_id)


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
