#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
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

# This module wraps calls to mkfs.<fstype> and determines the appropriate flags
# for each filesystem type

from curtin import util

import string

mkfs_commands = {
        "ext4": "mkfs.ext4",
        "ext3": "mkfs.ext3",
        "ext2": "mkfs.ext2",
        "fat12": "mkfs.fat",
        "fat16": "mkfs.fat",
        "fat32": "mkfs.fat",
        "fat": "mkfs.fat",
        "btrfs": "mkfs.btrfs",
        "swap": "mkswap"
        }

specific_to_family = {
        "ext4": "ext",
        "ext3": "ext",
        "ext2": "ext",
        "fat12": "fat",
        "fat16": "fat",
        "fat32": "fat",
        "fat": "fat",
        "btrfs": "btrfs",
        "swap": "swap"
        }

family_flag_mappings = {
        "label": {"ext": "-L",
                  "btrfs": "-L",
                  "fat": "-n",
                  "label": "-L"},
        "uuid": {"ext": "-U",
                 "btrfs": "-U",
                 "swap": "-U"},
        "force": {"ext": "-F",
                  "btrfs": "-f",
                  "swap": "-f"},
        "fatsize": {"fat": "-F"}
        }


def mkfs(path, fstype, flags):
    """Make filesystem on block device with given path using given fstype and
       appropriate flags for filesystem family"""
    fs_family = specific_to_family.get(fstype)
    mkfs_cmd = mkfs_commands.get(fstype)
    if fs_family is None or mkfs_cmd is None:
        raise ValueError("unsupported fs type '%s'" % fstype)
    cmd = [mkfs_cmd]
    if fs_family == "fat":
        fat_size = fstype.strip(string.ascii_letters)
        if fat_size in ["12", "16", "32"]:
            flags.append(("fatsize", fat_size))
    for flag in flags:
        flag_sym_families = family_flag_mappings.get(flag[0])
        if flag_sym_families is None:
            raise ValueError("unsupported flag '%s'" % flag[0])
        flag_sym = flag_sym_families.get(fs_family)
        if flag_sym is None:
            # This flag is npt supported by current fs_family, previous
            # behavior was to ignore it silently, so not going to raise
            continue
        cmd.extend([flag_sym, flag[1]])
    cmd.append(path)
    util.subp(cmd)


def mkfs_from_config(path, info):
    """Make filesystem on block device with given path according to storage
       config given"""
    fstype = info.get('fstype')
    if fstype is None:
        raise ValueError("fstype must be specified")
    flags = list((i, info.get(i)) for i in info if i in family_flag_mappings)
    mkfs(path, fstype, flags)
