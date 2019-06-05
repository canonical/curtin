import os

from curtin.log import LOG
from curtin import util
from curtin import udev

SHOW_PATHS_FMT = ("device='%d' serial='%z' multipath='%m' host_wwpn='%N' "
                  "target_wwnn='%n' host_wwpn='%R' target_wwpn='%r' "
                  "host_adapter='%a'")
SHOW_MAPS_FMT = "name=%n multipath='%w' sysfs='%d' paths='%N'"


def _extract_mpath_data(cmd, show_verb):
    data, _err = util.subp(cmd, capture=True)
    result = []
    for line in data.splitlines():
        mp_dict = util.load_shell_content(line, add_empty=True)
        LOG.debug('Extracted multipath %s fields: %s', show_verb, mp_dict)
        if mp_dict:
            result.append(mp_dict)

    return result


def show_paths():
    cmd = ['multipathd', 'show', 'paths', 'raw', 'format', SHOW_PATHS_FMT]
    return _extract_mpath_data(cmd, 'paths')


def show_maps():
    cmd = ['multipathd', 'show', 'maps', 'raw', 'format', SHOW_MAPS_FMT]
    return _extract_mpath_data(cmd, 'maps')


def is_mpath_device(devpath):
    info = udev.udevadm_info(devpath)
    if info.get('DM_UUID', '').startswith('mpath-'):
        return True

    return False


def is_mpath_member(devpath):
    try:
        util.subp(['multipath', '-c', devpath], capture=True)
        return True
    except util.ProcessExecutionError:
        return False


def is_mpath_partition(devpath):
    if devpath.startswith('/dev/dm-'):
        if 'DM_PART' in udev.udevadm_info(devpath):
            LOG.debug("%s is multipath device partition", devpath)
            return True

    return False


def mpath_partition_to_mpath_id(devpath):
    info = udev.udevadm_info(devpath)
    if 'DM_MPATH' in info:
        return info['DM_MPATH']

    return None


def remove_partition(devpath, retries=10):
    LOG.debug('multipath: removing multipath partition: %s', devpath)
    for _ in range(0, retries):
        util.subp(['dmsetup', 'remove', devpath], rcs=[0, 1])
        udev.udevadm_settle()
        if not os.path.exists(devpath):
            return

    util.wait_for_removal(devpath)


def remove_map(map_id, retries=10):
    LOG.debug('multipath: removing multipath map: %s', map_id)
    devpath = '/dev/mapper/%s' % map_id
    for _ in range(0, retries):
        util.subp(['multipath', '-f', map_id], rcs=[0, 1])
        udev.udevadm_settle()
        if not os.path.exists(devpath):
            return

    util.wait_for_removal(devpath)


def find_mpath_members(multipath_id, paths=None):
    if not paths:
        paths = show_paths()

    members = ['/dev/' + path['device']
               for path in paths if path['multipath'] == multipath_id]
    return members


def find_mpath_id(devpath, maps=None):
    if not maps:
        maps = show_maps()

    for mpmap in maps:
        if '/dev/' + mpmap['sysfs'] == devpath:
            name = mpmap.get('name')
            if name:
                return name
            return mpmap['multipath']

    return None
