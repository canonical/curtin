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
        "swap": "mkswap",
        "xfs": "mkfs.xfs",
        "jfs": "jfs_mkfs",
        "reiserfs": "mkfs.reiserfs",
        "ntfs": "mkntfs"
        }

specific_to_family = {
        "ext4": "ext",
        "ext3": "ext",
        "ext2": "ext",
        "fat12": "fat",
        "fat16": "fat",
        "fat32": "fat",
        }

label_length_limits = {
        "fat": 11,
        "ext": 16,
        "ntfs": 32,
        "jfs": 16,  # see jfs_tune manpage
        "xfs": 12,
        "swap": 15,  # not in manpages, found experimentally
        "btrfs": 256,
        "reiserfs": 16
        }

family_flag_mappings = {
        "label": {"ext": "-L",
                  "btrfs": "-L",
                  "fat": "-n",
                  "swap": "-L",
                  "xfs": "-L",
                  "jfs": "-L",
                  "reiserfs": "-l",
                  "ntfs": "-L"},
        "uuid": {"ext": "-U",
                 "btrfs": "-U",
                 "swap": "-U",
                 "reiserfs": "-d"},
        "force": {"ext": "-F",
                  "btrfs": "-f",
                  "swap": "-f",
                  "xfs": "-f",
                  "ntfs": "-F",
                  "reiserfs": "-f"},
        "fatsize": {"fat": "-F"},
        "quiet": {"ext": "-q",
                  "reiserfs": "-q",
                  "ntfs": "-q",
                  "xfs": "-q"}
        }


def mkfs(path, fstype, flags):
    """Make filesystem on block device with given path using given fstype and
       appropriate flags for filesystem family"""
    fs_family = specific_to_family.get(fstype, fstype)
    mkfs_cmd = mkfs_commands.get(fstype)
    if fs_family is None or mkfs_cmd is None:
        raise ValueError("unsupported fs type '%s'" % fstype)

    cmd = [mkfs_cmd]

    if fs_family == "fat":
        fat_size = fstype.strip(string.ascii_letters)
        if fat_size in ["12", "16", "32"]:
            flags.append(("fatsize", fat_size))

    for flag in flags:
        if type(flag) in [tuple, list]:
            # This is a flag with params
            flag_name = flag[0]
            flag_val = flag[1]
        else:
            # This is a standalone flag
            flag_name = flag
            flag_val = None

        flag_sym_families = family_flag_mappings.get(flag_name)
        if flag_sym_families is None:
            raise ValueError("unsupported flag '%s'" % flag[0])

        flag_sym = flag_sym_families.get(fs_family)
        if flag_sym is None:
            # This flag is npt supported by current fs_family, previous
            # behavior was to ignore it silently, so not going to raise
            continue

        if flag_name == "label":
            limit = label_length_limits.get(fs_family)
            if len(flag_val) > limit:
                raise ValueError("length of fs label for '%s' exceeds max \
                                 allowed for fstype '%s'. max is '%s'"
                                 % (path, fstype, limit))

        cmd.append(flag_sym)
        if flag_val is not None:
            cmd.append(flag_val)

    cmd.append(path)
    util.subp(cmd)


def mkfs_from_config(path, info):
    """Make filesystem on block device with given path according to storage
       config given"""
    fstype = info.get('fstype')
    if fstype is None:
        raise ValueError("fstype must be specified")
    flags = list((i, info.get(i)) for i in info if i in family_flag_mappings)
    # NOTE: Since old metadata on partitions that have not been wiped can cause
    #       some mkfs commands to refuse to work, its best to add a force flag
    #       here. At some point it may be a good idea to remove this if we can
    #       ensure that everything will be clean by the time we format. Also
    #       note that mkfs.btrfs does not have a force flag on precise, so we
    #       will skip adding the force flag for it
    if util.lsb_release()['codename'] != "precise" or fstype != "btrfs":
        flags.append("force")
    # Go ahead and add the quiet flag if the filesystem supports it
    flags.append("quiet")
    mkfs(path, fstype, flags)
