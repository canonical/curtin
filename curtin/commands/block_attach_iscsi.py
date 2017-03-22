#   Copyright (C) 2017 Canonical Ltd.
#
#   Author: Nishanth Aravamudan <nish.aravamudan@canonical.com>
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
from curtin.block import iscsi


def block_attach_iscsi_main(args):
    iscsi.ensure_disk_connected(args.disk, args.save_config)

    return 0


CMD_ARGUMENTS = (
    ('disk',
     {'help': 'RFC4173 specification of iSCSI disk to attach'}),
    ('--save-config',
     {'help': 'save access configuration to local filesystem',
      'default': False, 'action': 'store_true'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_attach_iscsi_main)
