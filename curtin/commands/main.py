#!/usr/bin/python
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

import argparse
import os
import sys
import traceback

from curtin import log
from curtin import util

SUB_COMMAND_MODULES = ['block-meta', 'curthooks', 'extract', 'hook',
                       'in-target', 'install', 'net-meta', 'pack', 'swap']


def add_subcmd(subparser, subcmd):
    modname = subcmd.replace("-", "_")
    subcmd_full = "curtin.commands.%s" % modname
    __import__(subcmd_full)
    try:
        popfunc = getattr(sys.modules[subcmd_full], 'POPULATE_SUBCMD')
    except AttributeError:
        raise AttributeError("No 'POPULATE_SUBCMD' in %s" % subcmd_full)

    popfunc(subparser.add_parser(subcmd))


def main(args=None):
    if args is None:
        args = sys.argv

    parser = argparse.ArgumentParser()

    stacktrace = (os.environ.get('CURTIN_STACKTRACE', "0").lower()
                  not in ("0", "false", ""))

    try:
        verbosity = int(os.environ.get('CURTIN_VERBOSITY', "0"))
    except ValueError:
        verbosity = 1

    parser.add_argument('--showtrace', action='store_true', default=stacktrace)
    parser.add_argument('--verbose', '-v', action='count', default=verbosity)
    parser.add_argument('--log-file', default=sys.stderr,
                        type=argparse.FileType('w'))

    subps = parser.add_subparsers(dest="subcmd")
    for subcmd in SUB_COMMAND_MODULES:
        add_subcmd(subps, subcmd)
    args = parser.parse_args(sys.argv[1:])

    # if user gave cmdline arguments, then lets set environ so subsequent
    # curtin calls get stacktraces.
    if args.showtrace and not stacktrace:
        os.environ['CURTIN_STACKTRACE'] = "1"

    if args.verbose and not verbosity:
        os.environ['CURTIN_VERBOSITY'] = str(args.verbose)

    if not getattr(args, 'func', None):
        # http://bugs.python.org/issue16308
        parser.print_help()
        sys.exit(1)

    log.basicConfig(stream=args.log_file, verbosity=args.verbose)

    paths = util.get_paths()

    if paths['helpers'] is None or paths['curtin_exe'] is None:
        raise OSError("Unable to find helpers or 'curtin' exe to add to path")

    path = os.environ['PATH'].split(':')

    for cand in (paths['helpers'], os.path.dirname(paths['curtin_exe'])):
        if cand not in [os.path.abspath(d) for d in path]:
            path.insert(0, cand)

    os.environ['PATH'] = ':'.join(path)

    try:
        sys.exit(args.func(args))
    except Exception as e:
        if args.showtrace:
            traceback.print_exc()
        sys.stderr.write("%s\n" % e)
        sys.exit(3)

# vi: ts=4 expandtab syntax=python
