#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
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

from collections import OrderedDict
from curtin import block
from curtin import util
from curtin.log import LOG

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'default': None, }),
     ('--fstype', {'help': 'root filesystem type',
                   'choices': ['ext4', 'ext3'], 'default': 'ext4'}),
     ('mode', {'help': 'meta-mode to use', 'choices': ['raid0', 'simple']}),
     )
)


def block_meta(args):
    # main entry point for the block-meta command.
    if args.mode == "simple":
        meta_simple(args)
    else:
        raise NotImplementedError("mode=%s is not implemenbed" % args.mode)


def logtime(msg, func, *args, **kwargs):
    with util.LogTimer(LOG.debug, msg):
        return func(*args, **kwargs)


def meta_simple(args):
    state = util.load_command_environment()

    cfg = util.load_command_config(args, state)

    devices = args.devices
    if devices is None:
        devices = cfg.get('block-meta', {}).get('devices', [])

    # Remove duplicates but maintain ordering.
    devices = list(OrderedDict.fromkeys(devices))

    if len(devices) == 0:
        devices = block.get_installable_blockdevs()
        LOG.warn("simple mode, no devices given. unused list: %s", devices)

    if len(devices) > 1:
        if args.devices is not None:
            LOG.warn("simple mode but multiple devices given. "
                     "using first found")
        available = [f for f in devices
                     if block.is_valid_device(f)]
        target = sorted(available)[0]
        LOG.warn("mode is 'simple'. multiple devices given. using '%s' "
                 "(first available)", target)
    else:
        target = devices[0]

    if not block.is_valid_device(target):
        raise Exception("target device '%s' is not a valid device" % target)

    (devname, devnode) = block.get_dev_name_entry(target)

    LOG.info("installing in simple mode to '%s'", devname)

    # helper partition will forcibly set up partition there
    logtime("partition %s" % devnode, util.subp, ("partition", devnode))

    rootdev = devnode + "1"

    cmd = ['mkfs.%s' % args.fstype, '-q', '-L', 'cloudimg-rootfs', rootdev]
    logtime(' '.join(cmd), util.subp, cmd)

    util.subp(['mount', rootdev, state['target']])

    with open(state['fstab'], "w") as fp:
        fp.write("LABEL=%s / %s defaults 0 0\n" % ('cloudimg-rootfs', 'ext4'))

    return 0


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_meta)

# vi: ts=4 expandtab syntax=python
