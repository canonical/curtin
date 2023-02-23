# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys

import curtin.util as util

from . import populate_one_subcmd, MutuallyExclusiveGroup
from curtin.log import LOG
from curtin import distro


def system_install_pkgs_main(args):
    #  curtin system-install [--target=/] [pkg, [pkg...]]
    if args.target is None:
        args.target = "/"

    exit_code = 0
    try:
        distro.install_packages(
            pkglist=args.packages, target=args.target,
            allow_daemons=args.allow_daemons,
            download_retries=args.download_retry_after,
            download_only=args.download_only, no_download=args.no_download)
    except util.ProcessExecutionError as e:
        LOG.warn("system install failed for %s: %s" % (args.packages, e))
        exit_code = e.exit_code

    sys.exit(exit_code)


MUTUALLY_EXCLUSIVE_DOWNLOAD_OPTIONS = (
    ((('--no-download',),
      {'help': ('assume packages to install have already been downloaded.'
                ' not supported on SUSE distro family.'),
       'action': 'store_true'}),
     (('--download-only',),
      {'help': ('do not install/upgrade packages, only perform download.'
                ' not supported on SUSE distro family.'),
       'action': 'store_true'}),
     )
)


CMD_ARGUMENTS = (
    ((('--allow-daemons',),
      {'help': ('do not disable running of daemons during upgrade.'),
       'action': 'store_true', 'default': False}),
     (('-t', '--target'),
      {'help': ('target root to upgrade. '
                'default is env[TARGET_MOUNT_POINT]'),
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('--download-retry-after',),
      {'help': ('when a download fails, wait N seconds and try again.'
                ' can be specified multiple times.'
                ' not supported on SUSE distro family.'),
       'action': 'append', 'nargs': '*'}),
     MutuallyExclusiveGroup(MUTUALLY_EXCLUSIVE_DOWNLOAD_OPTIONS),
     ('packages',
      {'help': 'the list of packages to install',
       'metavar': 'PACKAGES', 'action': 'store', 'nargs': '+'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, system_install_pkgs_main)

# vi: ts=4 expandtab syntax=python
