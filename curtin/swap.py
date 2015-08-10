#   Copyright (C) 2014 Canonical Ltd.
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

import os

from .log import LOG
from . import util


def suggested_swapsize(memsize=None, maxsize=None, fsys=None):
    # make a suggestion on the size of swap for this system.
    if memsize is None:
        memsize = util.get_meminfo()['total']

    GB = 2 ** 30
    sugg_max = 8 * GB

    if fsys is None and maxsize is None:
        # set max to 8GB default if no filesystem given
        maxsize = sugg_max
    elif fsys:
        avail = util.get_fs_use_info(fsys)[1]
        if maxsize is None:
            # set to 25% of filesystem space
            maxsize = min(int(avail / 4), sugg_max)
        elif maxsize > ((avail * .9)):
            # set to 90% of available disk space
            maxsize = int(avail * .9)

    formulas = [
        # < 1G: swap = double memory
        (1 * GB, lambda x: x * 2),
        # < 2G: swap = 2G
        (2 * GB, lambda x: 2 * GB),
        # < 4G: swap = memory
        (4 * GB, lambda x: x),
        # < 16G: 4G
        (16 * GB, lambda x: 4 * GB),
        # < 64G: 1/2 M up to max
        (64 * GB, lambda x: x / 2),
    ]

    size = None
    for top, func in formulas:
        if memsize <= top:
            size = min(func(memsize), maxsize)
            if size < (memsize / 2) and size < 4 * GB:
                return 0
            return size

    return maxsize


def setup_swapfile(target, fstab=None, swapfile=None, size=None, maxsize=None):
    if size is None:
        size = suggested_swapsize(fsys=target, maxsize=maxsize)

    if size == 0:
        LOG.debug("Not creating swap: suggested size was 0")
        return

    if swapfile is None:
        swapfile = "/swap.img"

    if not swapfile.startswith("/"):
        swapfile = "/" + swapfile

    mbsize = str(int(size / (2 ** 20)))
    msg = "creating swap file '%s' of %sMB" % (swapfile, mbsize)
    fpath = os.path.sep.join([target, swapfile])
    try:
        util.ensure_dir(os.path.dirname(fpath))
        with util.LogTimer(LOG.debug, msg):
            util.subp(
                ['sh', '-c',
                 ('rm -f "$1" && umask 0066 && '
                  '{ fallocate -l "${2}M" "$1" || '
                  '  dd if=/dev/zero "of=$1" bs=1M "count=$2"; } && '
                  'mkswap "$1" || { r=$?; rm -f "$1"; exit $r; }'),
                 'setup_swap', fpath, mbsize])
    except Exception:
        LOG.warn("failed %s" % msg)
        raise

    if fstab is None:
        return

    try:
        line = '\t'.join([swapfile, 'none', 'swap', 'sw', '0', '0'])
        with open(fstab, "a") as fp:
            fp.write(line + "\n")

    except Exception:
        os.unlink(fpath)
        raise
