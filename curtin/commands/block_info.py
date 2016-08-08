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

from . import populate_one_subcmd
from curtin import block


def block_info_main(args):
    if not args.devices:
        raise ValueError('devices to scan must be specified')
    if not all(block.is_block_device(d) for d in args.devices):
        raise ValueError('invalid device(s)')

    holders_trees = [block.clear_holders.gen_holders_tree(d)
                     for d in args.devices]

    def add_size_to_name(tree):
        pass

    print('\n'.join(block.clear_holders.format_holders_tree(t)
                    for t in holders_trees))


CMD_ARGUMENTS = (
    ('devices',
     {'help': 'devices to get info for', 'default': [], 'nargs': '+'}),
    (('-j', '--json'),
     {'help': 'output data in json format', 'default': False,
      'action': 'store_true'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_info_main)
