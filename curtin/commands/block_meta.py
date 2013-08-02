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

import curtin.block
from curtin.log import LOG


def block_meta(args):
    # main entry point for the block-meta command.
    if args.mode == "simple":
        meta_simple(args)
    else:
        raise NotImplementedError("mode=%s is not implemenbed" % args.mode)


def meta_simple(args):
    devices = args.devices
    if devices is None:
        LOG.warn("simple mode, no devices given, guessing")
        devices = ("vda", "sda")

    if len(devices) > 1:
        if args.devices is not None:
            LOG.warn("simple mode but multiple devices given. "
                     "using first found")
        available = [f for f in devices
                     if curtin.block.is_valid_device(f)]
        target = available[0]
        LOG.warn("mode is 'simple'. multiple devices given. using '%s' "
                 "(first available)", target)
    else:
        target = devices[0]

    if not curtin.block.is_valid_device(target):
        raise Exception("target device '%s' is not a valid device" % target)

    (devname, devnode) = curtin.block.get_dev_name_entry(target)

    LOG.info("installing in simple mode to '%s'", devname)


CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'default': None, }),
     ('mode', {'help': 'meta-mode to use', 'choices': ['raid0', 'simple']}),
     )
)
CMD_HANDLER = block_meta

# vi: ts=4 expandtab syntax=python
