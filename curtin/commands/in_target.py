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

import pty
import subprocess
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
     (('-t', '--target'),
      {'help': 'chroot to target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET', 'default': None}),
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

    interactive = sys.stdin.isatty()
    exit = 0

    cmd = ['chroot', target] + args.command_args

    with util.ChrootableTarget(target, allow_daemons=args.allow_daemons):
        if interactive:
            pty.spawn(cmd)
        else:
            sp = subprocess.Popen(cmd)
            sp.wait()
            exit = sp.returncode
    sys.exit(exit)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, in_target_main)

# vi: ts=4 expandtab syntax=python
