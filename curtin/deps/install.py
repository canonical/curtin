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
    import time
    if sys.version_info[0] == 2:
        pkgs = ['python-yaml']
    else:
        pkgs = ['python3-yaml']
    apt_update = ['apt-get', '--quiet', 'update']
    apt_install = ['apt-get', 'install', '--quiet', '--assume-yes']

    cmds = [apt_update, apt_install + pkgs]
    for cmd in cmds:
        # Retry each command with a wait between. The final wait time in this
        # list is zero because we don't need to wait at the end of the last
        # call.
        wait_times = [0.5, 1, 2, 0]
        for i, wait in enumerate(wait_times):
            try:
                subprocess.check_call(cmd)
                returncode = 0
            except subprocess.CalledProcessError as e:
                returncode = e.returncode
            if returncode == 0:
                break
            else:
                time.sleep(wait)
        if returncode != 0:
            sys.exit(returncode)
    sys.exit(0)
