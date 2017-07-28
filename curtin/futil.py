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

import grp
import pwd
import os

from .util import write_file, target_path
from .log import LOG


def chownbyid(fname, uid=None, gid=None):
    if uid in [None, -1] and gid in [None, -1]:
        return
    os.chown(fname, uid, gid)


def decode_perms(perm, default=0o644):
    try:
        if perm is None:
            return default
        if isinstance(perm, (int, float)):
            # Just 'downcast' it (if a float)
            return int(perm)
        else:
            # Force to string and try octal conversion
            return int(str(perm), 8)
    except (TypeError, ValueError):
        return default


def chownbyname(fname, user=None, group=None):
    uid = -1
    gid = -1
    try:
        if user:
            uid = pwd.getpwnam(user).pw_uid
        if group:
            gid = grp.getgrnam(group).gr_gid
    except KeyError as e:
        raise OSError("Unknown user or group: %s" % (e))
    chownbyid(fname, uid, gid)


def extract_usergroup(ug_pair):
    if not ug_pair:
        return (None, None)
    ug_parted = ug_pair.split(':', 1)
    u = ug_parted[0].strip()
    if len(ug_parted) == 2:
        g = ug_parted[1].strip()
    else:
        g = None
    if not u or u == "-1" or u.lower() == "none":
        u = None
    if not g or g == "-1" or g.lower() == "none":
        g = None
    return (u, g)


def write_finfo(path, content, owner="-1:-1", perms="0644"):
    (u, g) = extract_usergroup(owner)
    omode = "w"
    if isinstance(content, bytes):
        omode = "wb"
    write_file(path, content, mode=decode_perms(perms), omode=omode)
    chownbyname(path, u, g)


def write_files(files, base_dir=None):
    """Write files described in the dictionary 'files'

    paths are assumed under 'base_dir', which will default to '/'.
    A trailing '/' will be applied if not present.

    files is a dictionary where each entry has:
       path: /file1
       content: (bytes or string)
       permissions: (optional, default=0644)
       owner: (optional, default -1:-1): string of 'uid:gid'."""
    for (key, info) in files.items():
        if not info.get('path'):
            LOG.warn("Warning, write_files[%s] had no 'path' entry", key)
            continue

        write_finfo(path=target_path(base_dir, info['path']),
                    content=info.get('content', ''),
                    owner=info.get('owner', "-1:-1"),
                    perms=info.get('permissions', info.get('perms', "0644")))
