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
