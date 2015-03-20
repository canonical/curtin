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

if __name__ == '__main__':
    import subprocess
    import sys
    if sys.version_info[0] == 2:
        pkgs = ['python-yaml']
    else:
        pkgs = ['python3-yaml']
    apt_update = ['apt-get', '--quiet', 'update']
    apt_install = ['apt-get', 'install', '--quiet', '--assume-yes']

    cmds = [apt_update, apt_install + pkgs]
    for cmd in cmds:
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
    sys.exit(0)
