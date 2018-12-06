# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import resource

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


def is_swap_device(path):
    """
    Determine if specified device is a swap device.  Linux swap devices write
    a magic header value on kernel PAGESIZE - 10.

    https://github.com/torvalds/linux/blob/master/include/linux/swap.h#L111
    """
    LOG.debug('Checking if %s is a swap device', path)
    pagesize = resource.getpagesize()
    magic_offset = pagesize - 10
    size = util.file_size(path)
    if size < magic_offset:
        LOG.debug("%s is to small for swap (size=%d < pagesize=%d)",
                  path, size, pagesize)
        return False
    magic = util.load_file(
        path, read_len=10, offset=magic_offset, decode=False)
    LOG.debug('Found swap magic: %s' % magic)
    return magic in [b'SWAPSPACE2', b'SWAP-SPACE']
# vi: ts=4 expandtab syntax=python
