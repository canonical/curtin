#   Copyright (C) 2015 Canonical Ltd.
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

"""
The intent of this module is that it can be called to install deps
  python -m curtin.deps.install [-v]
"""

import argparse
import sys

from . import install_deps


def main():
    parser = argparse.ArgumentParser(
        prog='curtin-install-deps',
        description='install dependencies for curtin.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        dest='verbosity')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--no-allow-daemons', action='store_false',
                        default=True)
    args = parser.parse_args(sys.argv[1:])

    ret = install_deps(verbosity=args.verbosity, dry_run=args.dry_run,
                       allow_daemons=True)
    sys.exit(ret)


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab syntax=python
