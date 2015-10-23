#   Copyright (C) 2015 Canonical Ltd.
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
import sys

import curtin.util as util

from . import populate_one_subcmd
from curtin.log import LOG


def system_install_pkgs_main(args):
    #  curtin system-install [--target=/] [pkg, [pkg...]]
    if args.target is None:
        args.target = "/"

    exit_code = 0
    try:
        util.install_packages(
            pkglist=args.packages, target=args.target,
            allow_daemons=args.allow_daemons)
    except util.ProcessExecutionError as e:
        LOG.warn("system install failed for %s: %s" % (args.packages, e))
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
     ('packages',
      {'help': 'the list of packages to install',
       'metavar': 'PACKAGES', 'action': 'store', 'nargs': '+'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, system_install_pkgs_main)

# vi: ts=4 expandtab syntax=python
