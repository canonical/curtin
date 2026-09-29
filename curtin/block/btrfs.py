# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin import util


def btrfs_subvolume_create(device, subvol_name):

    if not device:
        raise ValueError('device is required')
    if not subvol_name:
        raise ValueError('subvol name is required')
    if '/' in subvol_name:
        raise ValueError(
            'nested subvolume paths not supported: %s' % subvol_name)

    with util.temporary_mount(device) as mnt:
        target = mnt / subvol_name
        util.subp(["btrfs", "subvolume", "create", "--", str(target)],
                  capture=True)
