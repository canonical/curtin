# This file is part of curtin. See LICENSE file for copyright and license info.

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
