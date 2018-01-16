#   Copyright (C) 2017 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
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

from curtin.log import LOG
from curtin import util
from . import populate_one_subcmd

import os

try:
    FileMissingError = FileNotFoundError
except NameError:
    FileMissingError = IOError


def unmount_main(args):
    """
    run util.umount(target, recursive=True)
    """
    if args.target is None:
        msg = "Missing target.  Please provide target path parameter"
        raise ValueError(msg)

    if not os.path.exists(args.target):
        msg = "Cannot unmount target path %s: it does not exist" % args.target
        raise FileMissingError(msg)

    LOG.info("Unmounting devices from target path: %s", args.target)
    recursive_mode = not args.disable_recursive_mounts
    util.do_umount(args.target, recursive=recursive_mode)


CMD_ARGUMENTS = (
     (('-t', '--target'),
      {'help': ('Path to mountpoint to be unmounted.'
                'The default is env variable "TARGET_MOUNT_POINT"'),
       'metavar': 'TARGET', 'action': 'store',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('-d', '--disable-recursive-mounts'),
      {'help': 'Disable unmounting recursively under target',
       'default': False, 'action': 'store_true'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, unmount_main)
