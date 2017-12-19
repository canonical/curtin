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

from .. import log
from .. import util
from ..deps import install_deps
from .. import version

VERSIONSTR = version.version_string()

SUB_COMMAND_MODULES = [
    'apply_net', 'block-info', 'block-meta', 'block-wipe', 'curthooks',
    'clear-holders', 'extract', 'hook', 'in-target', 'install', 'mkfs',
    'net-meta', 'apt-config', 'pack', 'swap', 'system-install',
    'system-upgrade', 'version']


def add_subcmd(subparser, subcmd):
    modname = subcmd.replace("-", "_")
    subcmd_full = "curtin.commands.%s" % modname
    __import__(subcmd_full)
    try:
        popfunc = getattr(sys.modules[subcmd_full], 'POPULATE_SUBCMD')
    except AttributeError:
        raise AttributeError("No 'POPULATE_SUBCMD' in %s" % subcmd_full)

    popfunc(subparser.add_parser(subcmd))


class NoHelpParser(argparse.ArgumentParser):
    # ArgumentParser with forced 'add_help=False'
    def __init__(self, *args, **kwargs):
        kwargs.update({'add_help': False})
        super(NoHelpParser, self).__init__(*args, **kwargs)

    def error(self, message):
        # without overriding this, argparse exits with bad usage
        raise ValueError("failed parsing arguments: %s" % message)


def get_main_parser(stacktrace=False, verbosity=0,
                    parser_class=argparse.ArgumentParser):
    parser = parser_class(prog='curtin', epilog='Version %s' % VERSIONSTR)
    parser.add_argument('--showtrace', action='store_true', default=stacktrace)
    parser.add_argument('-v', '--verbose', action='count', default=verbosity,
                        dest='verbosity')
    parser.add_argument('--log-file', default=sys.stderr,
                        type=argparse.FileType('w'))
    parser.add_argument('-c', '--config', action=util.MergedCmdAppend,
                        help='read configuration from cfg',
                        metavar='FILE', type=argparse.FileType("rb"),
                        dest='main_cfgopts', default=[])
    parser.add_argument('--install-deps', action='store_true',
                        help='install dependencies as necessary',
                        default=False)
    parser.add_argument('--set', action=util.MergedCmdAppend,
                        help=('define a config variable. key can be a "/" '
                              'delimited path ("early_commands/cmd1=a"). if '
                              'key starts with "json:" then val is loaded as '
                              'json (json:stages="[\'early\']")'),
                        metavar='key=val', dest='main_cfgopts')
    parser.set_defaults(config={})
    parser.set_defaults(reportstack=None)

    return parser


def maybe_install_deps(args, stacktrace=True, verbosity=0):
    parser = get_main_parser(stacktrace=stacktrace, verbosity=verbosity,
                             parser_class=NoHelpParser)
    subps = parser.add_subparsers(dest="subcmd", parser_class=NoHelpParser)
    for subcmd in SUB_COMMAND_MODULES:
        subps.add_parser(subcmd)

    install_only_args = [
        ['-v', '--install-deps'],
        ['-vv', '--install-deps'],
        ['--install-deps', '-v'],
        ['--install-deps', '-vv'],
        ['--install-deps'],
    ]

    install_only = args in install_only_args

    if install_only:
        verbosity = 1
    else:
        try:
            ns, unknown = parser.parse_known_args(args)
            verbosity = ns.verbosity
            if not ns.install_deps:
                return
        except ValueError:
            # bad usage will be reported by the real reporter
            return

    ret = install_deps(verbosity=verbosity)

    if ret != 0 or install_only:
        sys.exit(ret)

    return


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    stacktrace = (os.environ.get('CURTIN_STACKTRACE', "0").lower()
                  not in ("0", "false", ""))

    try:
        verbosity = int(os.environ.get('CURTIN_VERBOSITY', "0"))
    except ValueError:
        verbosity = 1

    maybe_install_deps(argv, stacktrace=stacktrace,
                       verbosity=verbosity)

    # Above here, only standard library modules can be assumed.
    from .. import config
    from ..reporter import (events, update_configuration)

    parser = get_main_parser(stacktrace=stacktrace, verbosity=verbosity)
    subps = parser.add_subparsers(dest="subcmd")
    for subcmd in SUB_COMMAND_MODULES:
        add_subcmd(subps, subcmd)
    args = parser.parse_args(argv)

    # merge config flags into a single config dictionary
    cfg_opts = args.main_cfgopts
    if hasattr(args, 'cfgopts'):
        cfg_opts += getattr(args, 'cfgopts')

    cfg = {}
    if cfg_opts:
        for (flag, val) in cfg_opts:
            if flag in ('-c', '--config'):
                config.merge_config_fp(cfg, val)
                val.close()
            elif flag in ('--set'):
                config.merge_cmdarg(cfg, val)
    else:
        cfg = config.load_command_config(args, util.load_command_environment())

    args.config = cfg

    # if user gave cmdline arguments, then set environ so subsequent
    # curtin calls get those as default
    showtrace = args.showtrace
    if 'showtrace' in cfg:
        showtrace = str(cfg['showtrace']).lower() not in ("0", "false")
    os.environ['CURTIN_STACKTRACE'] = str(int(showtrace))

    verbosity = args.verbosity
    if 'verbosity' in cfg:
        verbosity = int(cfg['verbosity'])
    os.environ['CURTIN_VERBOSITY'] = str(verbosity)

    if not getattr(args, 'func', None):
        # http://bugs.python.org/issue16308
        parser.print_help()
        sys.exit(1)

    log.basicConfig(stream=args.log_file, verbosity=verbosity)

    paths = util.get_paths()

    if paths['helpers'] is None or paths['curtin_exe'] is None:
        raise OSError("Unable to find helpers or 'curtin' exe to add to path")

    path = os.environ['PATH'].split(':')

    for cand in (paths['helpers'], os.path.dirname(paths['curtin_exe'])):
        if cand not in [os.path.abspath(d) for d in path]:
            path.insert(0, cand)

    os.environ['PATH'] = ':'.join(path)

    # set up the reportstack
    update_configuration(cfg.get('reporting', {}))

    stack_prefix = (os.environ.get("CURTIN_REPORTSTACK", "") +
                    "/cmd-%s" % args.subcmd)
    if stack_prefix.startswith("/"):
        stack_prefix = stack_prefix[1:]
    os.environ["CURTIN_REPORTSTACK"] = stack_prefix
    args.reportstack = events.ReportEventStack(
        name=stack_prefix, reporting_enabled=True, level="DEBUG",
        description="curtin command %s" % args.subcmd)

    try:
        with args.reportstack:
            ret = args.func(args)
        sys.exit(ret)
    except Exception as e:
        if showtrace:
            traceback.print_exc()
        sys.stderr.write("%s\n" % e)
        sys.exit(3)


if __name__ == '__main__':
    sys.exit(main())

# vi: ts=4 expandtab syntax=python
