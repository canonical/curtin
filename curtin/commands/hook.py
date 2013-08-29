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

import curtin.config
from curtin.log import LOG
import curtin.util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('target',),
      {'help': 'finalize the provided directory [default TARGET_MOUNT_POINT]',
       'action': 'store', 'default': os.environ.get('TARGET_MOUNT_POINT'),
       'nargs': '?'}),
     )
)


def hook(args):
    if not args.target:
        raise ValueError("Target must be provided or set in environment")

    LOG.debug("Finalizing %s" % args.target)

    target_hook = os.path.join(args.target, "/opt/curtin/finalize")
    if os.path.exists(target_hook):
        LOG.debug("running %s" % target_hook)
        curtin.util.subp(target_hook)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, hook)

# vi: ts=4 expandtab syntax=python
