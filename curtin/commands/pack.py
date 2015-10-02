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

from curtin import pack

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-o', '--output'),
      {'help': 'where to write the archive to', 'action': 'store',
       'metavar': 'FILE', 'default': "-", }),
     (('-a', '--add'),
      {'help': 'include FILE_PATH in archive at ARCHIVE_PATH',
       'action': 'append', 'metavar': 'ARCHIVE_PATH:FILE_PATH',
       'default': []}),
     ('command_args',
      {'help': 'command to run after extracting', 'nargs': '*'}),
     )
)


def pack_main(args):
    if args.output == "-":
        fdout = sys.stdout
    else:
        fdout = open(args.output, "w")

    delim = ":"
    addl = []
    for tok in args.add:
        if delim not in tok:
            raise ValueError("'--add' argument '%s' did not have a '%s'",
                             (tok, delim))
        (archpath, filepath) = tok.split(":", 1)
        addl.append((archpath, filepath),)

    pack.pack(fdout, command=args.command_args, copy_files=addl)

    if args.output != "-":
        fdout.close()

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, pack_main)

# vi: ts=4 expandtab syntax=python
