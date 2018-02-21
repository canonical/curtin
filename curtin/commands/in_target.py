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

    daemons = args.allow_daemons
    if util.target_path(args.target) == "/":
        sys.stderr.write("WARN: Target is /, daemons are allowed.\n")
        daemons = True
    cmd = args.command_args
    with util.ChrootableTarget(target, allow_daemons=daemons) as chroot:
        exit = 0
        if not args.interactive:
            try:
                chroot.subp(cmd, capture=args.capture)
            except util.ProcessExecutionError as e:
                exit = e.exit_code
        else:
            if chroot.target != "/":
                cmd = ["chroot", chroot.target] + args.command_args

            # in python 3.4 pty.spawn started returning a value.
            # There, it is the status from os.waitpid.  From testing (py3.6)
            # that seemse to be exit_code * 256.
            ret = pty.spawn(cmd)  # pylint: disable=E1111
            if ret is not None:
                exit = int(ret / 256)
        sys.exit(exit)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, in_target_main)

# vi: ts=4 expandtab syntax=python
