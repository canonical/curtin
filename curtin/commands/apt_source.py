#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
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

import sys

from curtin import (config, util)

from . import populate_one_subcmd

CUSTOM = 'custom'


def apt_source(args):
    """ apt_source
        Entry point for curtin apt_source
        Handling of apt_source: dict as custom config for apt. This allows
        writing custom source.list files, adding ppa's and PGP keys.
        It is especially useful to provide a fully isolated derived repository
    """
    #  curtin apt_source custom
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    if args.mode != CUSTOM:
        raise NotImplementedError("mode=%s is not implemented" % args.mode)

    apt_source_cfg = cfg.get("apt_source")
    if apt_source_cfg is None:
        raise ValueError("apt_source needs a custom config to be defined")

    try:
        handle_apt_source(apt_source_cfg)
    except Exception as e:
        sys.stderr.write("Failed to configure apt_source:\n%s\nExeption: %s" %
                         (apt_source_cfg, e))
        sys.exit(1)
    sys.exit(0)


CMD_ARGUMENTS = (
    ('mode', {'help': 'meta-mode to use',
              'choices': [CUSTOM]}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, apt_source)

# vi: ts=4 expandtab syntax=python
