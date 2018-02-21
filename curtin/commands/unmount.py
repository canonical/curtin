# This file is part of curtin. See LICENSE file for copyright and license info.

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

# vi: ts=4 expandtab syntax=python
