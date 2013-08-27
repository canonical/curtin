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

import sys

from curtin import util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-o', '--output'),
      {'help': 'where to write the archive to', 'action': 'store',
       'metavar': 'FILE', 'default': "-", }),
     (('-a', '--add'),
      {'help': 'include in archive (under data/)',
       'action': 'append', 'metavar': 'DIR'}),
     ('command_args',
      {'help': 'command to run after extracting', 'nargs': '*'}),
     )
)


def pack_main(args):
    if args.output == "-":
        fdout = sys.stdout
    else:
        fdout = open(args.output, "w")

    util.pack(fdout, command=args.command_args, addl=args.add)

    if args.output != "-":
        fdout.close()


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, pack_main)

# vi: ts=4 expandtab syntax=python
