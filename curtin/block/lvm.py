# This file is part of curtin. See LICENSE file for copyright and license info.

"""
This module provides some helper functions for manipulating lvm devices
"""

from curtin import distro
from curtin import util
from curtin.log import LOG
import json
import os

# separator to use for dm tool
_SEP = '='


def _query_lvmreport(tool, fields=(), filters=None,
                     *, report_subtype, reportidx):
    cmd = [tool, '--reportformat=json', "--units=B"]

    if not filters:
        filters = {}

    # lvmreport supports filters using the --select option, but the syntax
    # requires careful escaping which is challenging to do. Let's do the
    # filtering ourselves. This means we need to include the key of the filter
    # in the list of fields though.
    orig_fields = set(fields)
    fields = set(fields).union(filters.keys())

    if fields:
        cmd.extend(["--options", ",".join(sorted(fields))])

    (out, _) = util.subp(cmd, capture=True)
    ret = []
    for entry in json.loads(out)["report"][reportidx][report_subtype]:
        for key, val in filters.items():
            if entry[key] != val:
                break
        else:
            # Here we only keep the fields that were requested, not the ones
            # that were added because of filtering.
            ret.append({k: v for k, v in entry.items() if k in orig_fields})
    return ret


def _query_pvs(fields=(), filters=None):
    return _query_lvmreport("pvs", fields=fields, filters=filters,
                            report_subtype="pv", reportidx=0)


def _query_lvs(fields=(), filters=None):
    return _query_lvmreport("lvs", fields=fields, filters=filters,
                            report_subtype="lv", reportidx=0)


def get_pvols_in_volgroup(vg_name):
    """
    get physical volumes used by volgroup
    """
    results = _query_pvs(fields=["pv_name"], filters={"vg_name": vg_name})
    return [pv["pv_name"] for pv in results]


def get_lvols_in_volgroup(vg_name):
    """
    get logical volumes in volgroup
    """
    results = _query_lvs(fields=['lv_name'], filters={'vg_name': vg_name})
    return [lv["lv_name"] for lv in results]


def get_lv_size_bytes(lv_name):
    """ get the size in bytes of a logical volume specified by lv_name."""
    result = _query_lvs(fields=["lv_size"], filters={"lv_name": lv_name})
    if result:
        return util.human2bytes(result[0]["lv_size"])


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


def activate_volgroups(multipath=False):
    """
    Activate available volgroups and logical volumes within.

    # found
    % vgchange -ay
      1 logical volume(s) in volume group "vg1sdd" now active

    # none found (no output)
    % vgchange -ay
    """
    cmd = ['vgchange', '--activate=y']
    if multipath:
        # only operate on mp devices or encrypted volumes
        mp_filter = generate_multipath_dev_mapper_filter()
        cmd.extend(['--config', 'devices{ %s }' % mp_filter])

    # vgchange handles syncing with udev by default
    # see man 8 vgchange and flag --noudevsync
    out, _ = util.subp(cmd, capture=True)
    if out:
        LOG.info(out)


def _generate_multipath_filter(accept=None):
    if not accept:
        raise ValueError('Missing list of accept patterns')
    prefix = ", ".join(['"a|%s|"' % p for p in accept])
    return 'filter = [ {prefix}, "r|.*|" ]'.format(prefix=prefix)


def generate_multipath_dev_mapper_filter():
    return _generate_multipath_filter(
        accept=['/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*'])


def generate_multipath_dm_uuid_filter():
    return _generate_multipath_filter(accept=[
        '/dev/disk/by-id/dm-uuid-.*mpath-.*',
        '/dev/disk/by-id/.*dm_crypt-.*'])


def lvm_scan(activate=True, multipath=False):
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

    if multipath:
        # only operate on mp devices or encrypted volumes
        mponly = 'devices{ filter = [ "a|%s|", "a|%s|", "r|.*|" ] }' % (
            '/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*')

    for cmd in [['pvscan'], ['vgscan']]:
        if release != 'precise' and lvmetad_running():
            cmd.append('--cache')
        if multipath:
            cmd.extend(['--config', mponly])
        util.subp(cmd, capture=True)

# vi: ts=4 expandtab syntax=python
