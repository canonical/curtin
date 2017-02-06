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

import os
from . import populate_one_subcmd
from curtin import (block, util)


def block_info_main(args):
    """get information about block devices, similar to lsblk"""
    if not args.devices:
        raise ValueError('devices to scan must be specified')
    if not all(block.is_block_device(d) for d in args.devices):
        raise ValueError('invalid device(s)')

    def add_size_to_holders_tree(tree):
        """add size information to generated holders trees"""
        size_file = os.path.join(tree['device'], 'size')
        # size file is always represented in 512 byte sectors even if
        # underlying disk uses a larger logical_block_size
        size = ((512 * int(util.load_file(size_file)))
                if os.path.exists(size_file) else None)
        tree['size'] = util.bytes2human(size) if args.human else str(size)
        for holder in tree['holders']:
            add_size_to_holders_tree(holder)
        return tree

    def format_name(tree):
        """format information for human readable display"""
        res = {
            'name': ' - '.join((tree['name'], tree['dev_type'], tree['size'])),
            'holders': []
        }
        for holder in tree['holders']:
            res['holders'].append(format_name(holder))
        return res

    trees = [add_size_to_holders_tree(t) for t in
             [block.clear_holders.gen_holders_tree(d) for d in args.devices]]

    print(util.json_dumps(trees) if args.json else
          '\n'.join(block.clear_holders.format_holders_tree(t) for t in
                    [format_name(tree) for tree in trees]))

    return 0


CMD_ARGUMENTS = (
    ('devices',
     {'help': 'devices to get info for', 'default': [], 'nargs': '+'}),
    ('--human',
     {'help': 'output size in human readable format', 'default': False,
      'action': 'store_true'}),
    (('-j', '--json'),
     {'help': 'output data in json format', 'default': False,
      'action': 'store_true'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_info_main)
