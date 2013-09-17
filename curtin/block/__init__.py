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
import shlex

from curtin import util


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


def _lsblock_pairs_to_dict(lines, key="NAME"):
    ret = {}
    for line in lines.splitlines():
        toks = shlex.split(line)
        cur = {}
        for tok in toks:
            k, v = tok.split("=", 1)
            cur[k] = v
        cur['device_path'] = get_dev_name_entry(cur['NAME'])[1]
        ret[cur['NAME']] = cur
    return ret


def _lsblock(args=None):
    # lsblk  --help | sed -n '/Available/,/^$/p' |
    #     sed -e 1d -e '$d' -e 's,^[ ]\+,,' -e 's, .*,,' | sort
    keys = ['ALIGNMENT', 'DISC-ALN', 'DISC-GRAN', 'DISC-MAX', 'DISC-ZERO',
            'FSTYPE', 'GROUP', 'KNAME', 'LABEL', 'LOG-SEC', 'MAJ:MIN',
            'MIN-IO', 'MODE', 'MODEL', 'MOUNTPOINT', 'NAME', 'OPT-IO', 'OWNER',
            'PHY-SEC', 'RM', 'RO', 'ROTA', 'RQ-SIZE', 'SCHED', 'SIZE', 'STATE',
            'TYPE', 'UUID']
    if args is None:
        args = []
    # in order to avoid a very odd error with '-o' and all output fields above
    # we just drop one.  doesn't really matter which one.
    keys.remove('SCHED')
    basecmd = ['lsblk', '--noheadings', '--bytes', '--pairs',
               '--out=' + ','.join(keys)]
    (out, _err) = util.subp(basecmd + list(args), capture=True)
    return _lsblock_pairs_to_dict(out)


def get_unused_blockdev_info():
    # return a list of unused block devices. These are devices that
    # do not have anything mounted on them.

    # get a list of top level block devices, then iterate over it to get
    # devices dependent on those.  If the lsblk call for that specific
    # call has nothing 'MOUNTED", then this is an unused block device
    bdinfo = _lsblock(['--nodeps'])
    unused = {}
    for devname, data in bdinfo.items():
        cur = _lsblock([data['device_path']])
        mountpoints = [x for x in cur if cur[x].get('MOUNTPOINT')]
        if len(mountpoints) == 0:
            unused[devname] = data
    return unused


def get_installable_blockdevs():
    good = []
    unused = get_unused_blockdev_info()
    for devname, data in unused.iteritems():
        if data.get('RO') == "0" and data.get('TYPE') == "disk":
            good.append(devname)
    return good


# vi: ts=4 expandtab syntax=python
