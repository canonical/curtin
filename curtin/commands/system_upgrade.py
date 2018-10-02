# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys

import curtin.util as util

from . import populate_one_subcmd
from curtin.log import LOG
from curtin import distro


def system_upgrade_main(args):
    #  curtin system-upgrade [--target=/]
    if args.target is None:
        args.target = "/"

    exit_code = 0
    try:
        distro.system_upgrade(target=args.target,
                              allow_daemons=args.allow_daemons)
    except util.ProcessExecutionError as e:
        LOG.warn("system upgrade failed: %s" % e)
        exit_code = e.exit_code

    sys.exit(exit_code)


CMD_ARGUMENTS = (
    ((('--allow-daemons',),
      {'help': ('do not disable running of daemons during upgrade.'),
       'action': 'store_true', 'default': False}),
     (('-t', '--target'),
      {'help': ('target root to upgrade. '
                'default is env[TARGET_MOUNT_POINT]'),
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, system_upgrade_main)

# vi: ts=4 expandtab syntax=python
