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

import subprocess
import sys
import time

from . import find_missing_deps
from ..util import (install_packages, ProcessExecutionError)


def runcmd(cmd, retries=[]):
    for wait in retries:
        try:
            subprocess.check_call(cmd)
            return 0
        except subprocess.CalledProcessError as e:
            sys.stderr.write("%s failed. sleeping %s\n" % (cmd, wait))
            time.sleep(wait)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        return e.returncode


if __name__ == '__main__':
    verbose = False
    args = sys.argv
    if len(args) > 1 and args[1] in ("-v", "--verbose"):
        verbose = True
        args = args[1:]

    install_deps = '--install-deps' in args

    errors = find_missing_deps()
    if len(errors) == 0:
        if verbose:
            sys.stderr.write("No missing dependencies\n")
        sys.exit(0)

    missing_pkgs = []
    for e in errors:
        missing_pkgs += e.deps

    if not install_deps:
        if verbose:
            sys.stderr.write("Missing dependencies: %s\n" %
                             ' '.join(sorted(missing_pkgs)))
        sys.exit(0)

    if verbose:
        sys.stderr.write(
            "Installing %s\n" % ' '.join(sorted(missing_pkgs)))

    ret = 0
    try:
        install_packages(missing_pkgs, allow_daemons=True)
    except ProcessExecutionError as e:
        sys.stderr.write("%s\n" % e)
        ret = e.exit_code

    sys.exit(ret)

# vi: ts=4 expandtab syntax=python
