# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path
import tempfile

from curtin import util


def btrfs_subvolume_create(device, subvol_path):

    if not device:
        raise ValueError('device is required')
    if not subvol_path:
        raise ValueError('subvol path is required and must be relative')
    if '/' in subvol_path:
        raise ValueError(
            'nested subvolume paths not supported: %s' % subvol_path)

    with tempfile.TemporaryDirectory(prefix='curtin-btrfs-') as mnt:
        with util.mount(device, mnt):
            mount = Path(mnt)
            target = mount / subvol_path
            util.subp(["btrfs", "subvolume", "create", "--", str(target)],
                      capture=True)
