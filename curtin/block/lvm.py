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

# This module provides some helper functions for manipulating lvm devices

from curtin import util


def _filter_lvm_info(lvtool, match_field, query_field, match_key):
    """filter output of pv/vg/lvdisplay tools"""
    sep = '='
    (out, _) = util.subp([lvtool, '-C', '--separator', sep, '--noheadings',
                          '-o', ','.join([match_field, query_field])],
                         capture=True)
    return [qf for (mf, qf) in [l.strip().split(sep) for l in out.splitlines()]
            if mf == match_key]


def get_pvols_in_volgroup(vg_name):
    """get physical volumes used by volgroup"""
    return _filter_lvm_info('pvdisplay', 'vg_name', 'pv_name', vg_name)


def get_lvols_in_volgroup(vg_name):
    """get logical volumes in volgroup"""
    return _filter_lvm_info('lvdisplay', 'vg_name', 'lv_name', vg_name)


def get_lvm_dm_mappings():
    """
    get mappings between lvm volumes/volgroups and device mapper backing devs
    """
    return {}


def split_vg_lv_name(full):
    """
    Break full logical volume device name into volume group and logical volume
    """
    # just using .split('-') will not work because when a logical volume or
    # volume group has a name containing a '-', '--' is used to denote this in
    # the /sys/block/{name}/dm/name (LP:1591573)

    # handle newline if present
    full = full.strip()

    # get index of first - not followed by or preceeded by another -
    indx = None
    try:
        indx = next(i + 1 for (i, c) in enumerate(full[1:-1])
                    if c == '-' and '-' not in (full[i], full[i + 2]))
    except StopIteration:
        pass

    if not indx:
        raise ValueError("vg-lv full name does not contain a '-': {}'".format(
            full))

    return (full[:indx].replace('--', '-'),
            full[indx + 1:].replace('--', '-'))
