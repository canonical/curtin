#   Copyright (C) 2016 Canonical Ltd.
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

import sys
import curtin.block as block
from . import populate_one_subcmd


def wipe_main(args):
    #  curtin clear-holders device [device2 [device3]]
    for blockdev in args.devices:
        try:
            block.wipe_volume(blockdev, mode=args.mode)
        except Exception as e:
            sys.stderr.write(
                "Failed to wipe volume %s in mode %s: %s" %
                (blockdev, args.mode, e))
            sys.exit(1)
    sys.exit(0)


CMD_ARGUMENTS = (
    ((('-m', '--mode'),
      {'help': 'mode for wipe.', 'action': 'store',
       'default': 'superblocks',
       'choices': ['zero', 'superblock', 'superblock-recursive', 'random']}),
     ('devices',
      {'help': 'devices to wipe', 'default': [], 'nargs': '+'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, wipe_main)

# vi: ts=4 expandtab syntax=python
