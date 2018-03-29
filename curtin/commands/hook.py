# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys

import curtin.config
from curtin.log import LOG
import curtin.util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('target',),
      {'help': 'finalize the provided directory [default TARGET_MOUNT_POINT]',
       'action': 'store', 'default': os.environ.get('TARGET_MOUNT_POINT'),
       'nargs': '?'}),
     )
)


def hook(args):
    if not args.target:
        raise ValueError("Target must be provided or set in environment")

    LOG.debug("Finalizing %s" % args.target)
    curtin.util.run_hook_if_exists(args.target, "finalize")

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, hook)

# vi: ts=4 expandtab syntax=python
