# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys

import curtin.swap as swap
import curtin.util as util

from . import populate_one_subcmd


def swap_main(args):
    #  curtin swap [--size=4G] [--target=/] [--fstab=/etc/fstab] [swap]
    state = util.load_command_environment()

    if args.target is not None:
        state['target'] = args.target

    if args.fstab is not None:
        state['fstab'] = args.fstab

    if state['target'] is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    size = args.size
    if size is not None and size.lower() == "auto":
        size = None

    if size is not None:
        try:
            size = util.human2bytes(size)
        except ValueError as e:
            sys.stderr.write("%s\n" % e)
            sys.exit(2)

    if args.maxsize is not None:
        args.maxsize = util.human2bytes(args.maxsize)

    swap.setup_swapfile(target=state['target'], fstab=state['fstab'],
                        swapfile=args.swapfile, size=size,
                        maxsize=args.maxsize)
    sys.exit(2)


CMD_ARGUMENTS = (
    ((('-f', '--fstab'),
      {'help': 'file to write to. defaults to env["OUTPUT_FSTAB"]',
       'metavar': 'FSTAB', 'action': 'store',
       'default': os.environ.get('OUTPUT_FSTAB')}),
     (('-t', '--target'),
      {'help': ('target filesystem root to add swap file to. '
                'default is env[TARGET_MOUNT_POINT]'),
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('-s', '--size'),
      {'help': 'size of swap file (eg: 1G, 1500M, 1024K, 100000. def: "auto")',
               'default': None, 'action': 'store'}),
     (('-M', '--maxsize'),
      {'help': 'maximum size of swap file (assuming "auto")',
               'default': None, 'action': 'store'}),
     ('swapfile', {'help': 'path to swap file under target',
                   'default': 'swap.img', 'nargs': '?'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, swap_main)

# vi: ts=4 expandtab syntax=python
