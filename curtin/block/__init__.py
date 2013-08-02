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

import errno
import os
import stat


def get_dev_name_entry(devname):
    bname = os.path.basename(devname)
    return (bname, "/dev/" + bname)


def is_valid_device(devname):
    devent = get_dev_name_entry(devname)[1]
    try:
        return stat.S_ISBLK(os.stat(devent).st_mode)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    return False


# vi: ts=4 expandtab syntax=python
