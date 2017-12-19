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
The intent point of this module is that it can be called
and exit success or fail, indicating that deps should be there.
  python -m curtin.deps.check [-v]
"""
import argparse
import sys

from . import find_missing_deps


def debug(level, msg_level, msg):
    if level >= msg_level:
        if msg[-1] != "\n":
            msg += "\n"
        sys.stderr.write(msg)


def main():
    parser = argparse.ArgumentParser(
        prog='curtin-check-deps',
        description='check dependencies for curtin.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        dest='verbosity')
    args, extra = parser.parse_known_args(sys.argv[1:])

    errors = find_missing_deps()

    if len(errors) == 0:
        # exit 0 means all dependencies are available.
        debug(args.verbosity, 1, "No missing dependencies")
        sys.exit(0)

    missing_pkgs = []
    fatal = []
    for e in errors:
        if e.fatal:
            fatal.append(e)
        debug(args.verbosity, 2, str(e))
        missing_pkgs += e.deps

    if len(fatal):
        for e in fatal:
            debug(args.verbosity, 1, str(e))
        sys.exit(1)

    debug(args.verbosity, 1,
          "Fix with:\n  apt-get -qy install %s\n" %
          ' '.join(sorted(missing_pkgs)))

    # we exit higher with less deps needed.
    # exiting 99 means just 1 dep needed.
    sys.exit(100-len(missing_pkgs))


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab syntax=python
