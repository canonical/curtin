#   Copyright (C) 2015 Canonical Ltd.
#
#   Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
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

from . import populate_one_subcmd
from curtin.block.mkfs import mkfs as run_mkfs

import sys

CMD_ARGUMENTS = (
    (('devices',
      {'help': 'create filesystem on the target volume(s) or storage config \
                item(s)',
       'metavar': 'DEVICE', 'action': 'store', 'nargs': '+'}),
     (('-f', '--fstype'),
      {'help': 'filesystem type to use. default is ext4',
       'default': 'ext4', 'action': 'store'}),
     (('-l', '--label'),
      {'help': 'label to use for filesystem', 'action': 'store'}),
     (('-u', '--uuid'),
      {'help': 'uuid to use for filesystem', 'action': 'store'}),
     (('-F', '--force'),
      {'help': 'continue if minor errors encountered', 'action': 'store_true',
       'default': False})
     )
)


def mkfs(args):
    for device in args.devices:
        run_mkfs(device, args.fstype, strict=(not args.force),
                 uuid=args.uuid, label=args.label, force=args.force)

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, mkfs)

# vi: ts=4 expandtab syntax=python
