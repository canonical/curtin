#   Copyright (C) 2016 Canonical Ltd.
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
from curtin import block

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
                  "btrfs": "--label",
                  "fat": "-n",
                  "swap": "--label",
                  "xfs": "-L",
                  "jfs": "-L",
                  "reiserfs": "--label",
                  "ntfs": "--label"},
        "uuid": {"ext": "-U",
                 "btrfs": "--uuid",
                 "swap": "--uuid",
                 "reiserfs": "--uuid"},
        "force": {"ext": "-F",
                  "btrfs": "--force",
                  "swap": "--force",
                  "xfs": "-f",
                  "ntfs": "--force",
                  "reiserfs": "-f"},
        "fatsize": {"fat": "-F"},
        "quiet": {"ext": "-q",
                  "reiserfs": "-q",
                  "ntfs": "-q",
                  "xfs": "--quiet"}
        }


def replace_flag_value(flags, flagname, flagval):
    """Loop through flags and replace value of any instance of flag with
       given name with given value. If no instance of flag exists then append
       one"""
    for flag in flags:
        if isinstance(flag, (tuple, list)) and flag[0] == flagname:
            flag[1] = flagval
            break
    else:
        flags.append([flagname, flagval])


def mkfs(path, fstype, extra_flags=[], strict=False, label=None, uuid=None):
    """Make filesystem on block device with given path using given fstype and
       appropriate flags for filesystem family.

       Filesystem uuid and label can be passed in as kwargs. By default no
       label or uuid will be used. If a filesystem label is too long curtin
       will raise a ValueError if the strict flag is true or will truncate
       it to the maximum possible length.

       Additional flags are passed in as a list to extra_flags, with each
       entry in the list either being a string representing a flag without
       a parameter or a tuple representing a flag and it's parameter. UUID and
       label can be passed in to extra_flags as well, but if a uuid or label is
       specified both in extra_flags and as a kwarg the kwarg takes priority.
       If a flag is not supported by a filesystem family mkfs will raise a
       ValueError if the strict flag is true or silently ignore it otherwise.
       """

    if path is None or not block.is_valid_device(path):
        raise ValueError("invalid block dev path '%s'" % path)

    fs_family = specific_to_family.get(fstype, fstype)
    mkfs_cmd = mkfs_commands.get(fstype)
    if not all((fs_family, mkfs_cmd)):
        raise ValueError("unsupported fs type '%s'" % fstype)

    if util.which(mkfs_cmd) is None:
        raise ValueError("need '%s' but it could not be found" % mkfs_cmd)

    cmd = [mkfs_cmd]

    if label is not None:
        replace_flag_value(extra_flags, "label", label)

    if uuid is not None:
        replace_flag_value(extra_flags, "uuid", uuid)

    if fs_family == "fat":
        fat_size = fstype.strip(string.ascii_letters)
        if fat_size in ["12", "16", "32"]:
            replace_flag_value(extra_flags, "fatsize", fat_size)

    for flag in extra_flags:
        if isinstance(flag, (tuple, list)):
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
            # This flag is not supported by current filesystem family.
            if strict:
                raise ValueError("flag '%s' not supported by fs family '%s'" %
                                 flag_name, fs_family)
            else:
                continue

        if flag_name == "label":
            limit = label_length_limits.get(fs_family)
            if len(flag_val) > limit:
                if strict:
                    raise ValueError("length of fs label for '%s' exceeds max \
                                     allowed for fstype '%s'. max is '%s'"
                                     % (path, fstype, limit))
                else:
                    flag_val = flag_val[:limit]

        cmd.append(flag_sym)
        if flag_val is not None:
            cmd.append(flag_val)

    cmd.append(path)
    util.subp(cmd, capture=True)


def mkfs_from_config(path, info, strict=False):
    """Make filesystem on block device with given path according to storage
       config given"""
    fstype = info.get('fstype')
    if fstype is None:
        raise ValueError("fstype must be specified")
    flags = list((i, info.get(i)) for i in info if i in family_flag_mappings)
    # NOTE: Since old metadata on partitions that have not been wiped can cause
    #       some mkfs commands to refuse to work, it's best to add a force flag
    #       here. Also note that mkfs.btrfs does not have a force flag on
    #       precise, so we will skip adding the force flag for it
    if util.lsb_release()['codename'] != "precise" or fstype != "btrfs":
        flags.append("force")
    mkfs(path, fstype, extra_flags=flags, strict=strict)
