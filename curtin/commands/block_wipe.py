# This file is part of curtin. See LICENSE file for copyright and license info.

import sys
import curtin.block as block
from . import populate_one_subcmd
from .. import log

LOG = log.LOG


def wipe_main(args):
    for blockdev in args.devices:
        try:
            LOG.debug('Wiping volume %s with mode=%s', blockdev, args.mode)
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
       'default': 'superblock',
       'choices': ['zero', 'superblock', 'superblock-recursive', 'random']}),
     ('devices',
      {'help': 'devices to wipe', 'default': [], 'nargs': '+'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, wipe_main)

# vi: ts=4 expandtab syntax=python
