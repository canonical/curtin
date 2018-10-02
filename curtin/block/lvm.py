# This file is part of curtin. See LICENSE file for copyright and license info.

"""
This module provides some helper functions for manipulating lvm devices
"""

from curtin import distro
from curtin import util
from curtin.log import LOG
import os

# separator to use for lvm/dm tools
_SEP = '='


def _filter_lvm_info(lvtool, match_field, query_field, match_key):
    """
    filter output of pv/vg/lvdisplay tools
    """
    (out, _) = util.subp([lvtool, '-C', '--separator', _SEP, '--noheadings',
                          '-o', ','.join([match_field, query_field])],
                         capture=True)
    return [qf for (mf, qf) in
            [l.strip().split(_SEP) for l in out.strip().splitlines()]
            if mf == match_key]


def get_pvols_in_volgroup(vg_name):
    """
    get physical volumes used by volgroup
    """
    return _filter_lvm_info('pvdisplay', 'vg_name', 'pv_name', vg_name)


def get_lvols_in_volgroup(vg_name):
    """
    get logical volumes in volgroup
    """
    return _filter_lvm_info('lvdisplay', 'vg_name', 'lv_name', vg_name)


def split_lvm_name(full):
    """
    split full lvm name into tuple of (volgroup, lv_name)
    """
    # 'dmsetup splitname' is the authoratative source for lvm name parsing
    (out, _) = util.subp(['dmsetup', 'splitname', full, '-c', '--noheadings',
                          '--separator', _SEP, '-o', 'vg_name,lv_name'],
                         capture=True)
    return out.strip().split(_SEP)


def lvmetad_running():
    """
    check if lvmetad is running
    """
    return os.path.exists(os.environ.get('LVM_LVMETAD_PIDFILE',
                                         '/run/lvmetad.pid'))


def activate_volgroups():
    """
    Activate available volgroups and logical volumes within.

    # found
    % vgchange -ay
      1 logical volume(s) in volume group "vg1sdd" now active

    # none found (no output)
    % vgchange -ay
    """

    # vgchange handles syncing with udev by default
    # see man 8 vgchange and flag --noudevsync
    out, _ = util.subp(['vgchange', '--activate=y'], capture=True)
    if out:
        LOG.info(out)


def lvm_scan(activate=True):
    """
    run full scan for volgroups, logical volumes and physical volumes
    """
    # prior to xenial, lvmetad is not packaged, so even if a tool supports
    # flag --cache it has no effect. In Xenial and newer the --cache flag is
    # used (if lvmetad is running) to ensure that the data cached by
    # lvmetad is updated.

    # before appending the cache flag though, check if lvmetad is running. this
    # ensures that we do the right thing even if lvmetad is supported but is
    # not running
    release = distro.lsb_release().get('codename')
    if release in [None, 'UNAVAILABLE']:
        LOG.warning('unable to find release number, assuming xenial or later')
        release = 'xenial'

    for cmd in [['pvscan'], ['vgscan', '--mknodes']]:
        if release != 'precise' and lvmetad_running():
            cmd.append('--cache')
        util.subp(cmd, capture=True)

# vi: ts=4 expandtab syntax=python
