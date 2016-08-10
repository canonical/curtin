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

from curtin import (block, log)
from . import populate_one_subcmd


def clear_holders_main(args):
    """wrapper for clear_holders accepting cli args"""
    if (not all(block.is_block_device(device) for device in args.devices) or
            len(args.devices) == 0):
        raise ValueError('invalid devices specified')
    block.clear_holders.start_clear_holders_deps()
    block.clear_holders.clear_holders(args.devices)
    block.clear_holders.assert_clear(args.devices)


CMD_ARGUMENTS = (
    (('devices',
      {'help': 'devices to free', 'default': [], 'nargs': '+'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, clear_holders_main)
