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
from . import find_missing_deps

if __name__ == '__main__':
    import sys
    verbose = False
    if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--verbose"):
        verbose = True
    errors = find_missing_deps()
    if verbose:
        for emsg in errors:
            sys.stderr.write("%s\n" % emsg)

    if len(errors) == 0:
        # exit 0 means we need no depends
        if verbose:
            sys.stderr.write("No missing dependencies.\n")
        sys.exit(0)

    missing_pkgs = []
    for e in errors:
        missing_pkgs += e.deps

    if verbose:
        sys.stderr.write(
            "Fix with:\n  apt-get -qy install %s\n" %
            ' '.join(sorted(missing_pkgs)))
    # we exit higher with less deps needed.
    # exiting 99 means just 1 dep needed.
    sys.exit(100-len(missing_pkgs))

# vi: ts=4 expandtab syntax=python
