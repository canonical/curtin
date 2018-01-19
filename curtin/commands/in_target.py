# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import pty
import sys

from curtin import util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-a', '--allow-daemons'),
      {'help': 'do not disable daemons via invoke-rc.d',
       'action': 'store_true', 'default': False, }),
     (('-i', '--interactive'),
      {'help': 'use command invoked interactively',
       'action': 'store_true', 'default': False}),
     (('--capture',),
      {'help': 'capture/swallow output of command',
       'action': 'store_true', 'default': False}),
     (('-t', '--target'),
      {'help': 'chroot to target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     ('command_args',
      {'help': 'run a command chrooted in the target', 'nargs': '*'}),
     )
)


def run_command(cmd, interactive, capture=False):
    exit = 0
    if interactive:
        pty.spawn(cmd)
    else:
        try:
            util.subp(cmd, capture=capture)
        except util.ProcessExecutionError as e:
            exit = e.exit_code
    return exit


def in_target_main(args):
    if args.target is not None:
        target = args.target
    else:
        state = util.load_command_environment()
        target = state['target']

    if args.target is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    if os.path.abspath(target) == "/":
        cmd = args.command_args
    else:
        cmd = ['chroot', target] + args.command_args

    if target == "/" and args.allow_daemons:
        ret = run_command(cmd, args.interactive, capture=args.capture)
    else:
        with util.ChrootableTarget(target, allow_daemons=args.allow_daemons):
            ret = run_command(cmd, args.interactive)

    sys.exit(ret)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, in_target_main)

# vi: ts=4 expandtab syntax=python
