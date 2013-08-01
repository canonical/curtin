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


def block_meta(args):
    #    curtin block-wipe --all-unused
    #    curtin block-meta --devices all raid0
    #    curtin block-meta --devices disk0 simple
    print("This is block_meta: %s" % args)
    raise Exception("block_meta is not implemented")


CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE'}),
     ('mode', {'help': 'meta-mode to use', 'choices': ['raid0', 'simple']}),
     )
)
CMD_HANDLER = block_meta

# vi: ts=4 expandtab syntax=python
