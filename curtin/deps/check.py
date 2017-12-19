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
_imports = (
    "from ..commands import main",
    "import yaml",
)


def _check_imports(imports=_imports):
    errors = []
    for istr in _imports:
        try:
            exec(istr)
        except ImportError as e:
            errors.append("failed '%s': %s" % (istr, e))

    return errors

if __name__ == '__main__':
    import sys
    verbose = False
    if len(sys.argv) > 1 and sys.argv[1] in ("-v", "--verbose"):
        verbose = True
    errors = _check_imports()
    if verbose:
        for emsg in errors:
            sys.stderr.write("%s\n" % emsg)
    sys.exit(len(errors))
