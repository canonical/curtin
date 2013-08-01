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

SOURCE_FORMATS = ['root-tar']


def extract(args):
    print("This is extract: %s" % args)
    raise Exception("extract is not implemented")


# curtin extract [--root TARGET_MOUNT_POINT] [--path=/] [--format=auto] url
CMD_ARGUMENTS = (
    ((('-t', '--target'),
      {'help': ('target directory to extract to (root) '
                '[default TARGET_MOUNT_DIR]'),
       'action': 'store'}),
     (('-p', '--path'),
      {'help': 'path under target to extract to', 'default': ''}),
     (('-f', '--format'),
      {'help': 'what format is the source in',
       'choices': SOURCE_FORMATS}),
     )
)
CMD_HANDLER = extract

# vi: ts=4 expandtab syntax=python
