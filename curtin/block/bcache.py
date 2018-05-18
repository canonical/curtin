# This file is part of curtin. See LICENSE file for copyright and license info.

import os

from curtin import util
from curtin.log import LOG
from . import sys_block_path


def superblock_asdict(device=None, data=None):
    """ Convert output from bcache-super-show into a dictionary"""

    if not device and not data:
        raise ValueError('Supply a device name, or data to parse')

    if not data:
        data, _err = util.subp(['bcache-super-show', device], capture=True)
    bcache_super = {}
    for line in data.splitlines():
        if not line:
            continue
        values = [val for val in line.split('\t') if val]
        bcache_super.update({values[0]: values[1]})

    return bcache_super


def parse_sb_version(sb_version):
    """ Convert sb_version string to integer if possible"""
    try:
        # 'sb.version': '1 [backing device]'
        # 'sb.version': '3 [caching device]'
        version = int(sb_version.split()[0])
    except (AttributeError, ValueError):
        LOG.warning("Failed to parse bcache 'sb.version' field"
                    " as integer: %s", sb_version)
        return None

    return version


def is_backing(device, superblock=False):
    """ Test if device is a bcache backing device

    A runtime check for an active bcache backing device is to
    examine /sys/class/block/<kname>/bcache/label

    However if a device is not active then read the superblock
    of the device and check that sb.version == 1"""

    if not superblock:
        sys_block = sys_block_path(device)
        bcache_sys_attr = os.path.join(sys_block, 'bcache', 'label')
        return os.path.exists(bcache_sys_attr)
    else:
        bcache_super = superblock_asdict(device=device)
        sb_version = parse_sb_version(bcache_super['sb.version'])
        return bcache_super and sb_version == 1


def is_caching(device, superblock=False):
    """ Test if device is a bcache caching device

    A runtime check for an active bcache backing device is to
    examine /sys/class/block/<kname>/bcache/cache_replacement_policy

    However if a device is not active then read the superblock
    of the device and check that sb.version == 3"""

    if not superblock:
        sys_block = sys_block_path(device)
        bcache_sysattr = os.path.join(sys_block, 'bcache',
                                      'cache_replacement_policy')
        return os.path.exists(bcache_sysattr)
    else:
        bcache_super = superblock_asdict(device=device)
        sb_version = parse_sb_version(bcache_super['sb.version'])
        return bcache_super and sb_version == 3


def write_label(label, device):
    """ write label to bcache device """
    sys_block = sys_block_path(device)
    bcache_sys_attr = os.path.join(sys_block, 'bcache', 'label')
    util.write_file(bcache_sys_attr, content=label)

# vi: ts=4 expandtab syntax=python
