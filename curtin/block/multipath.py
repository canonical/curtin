import os

from curtin.log import LOG
from curtin import util
from curtin import udev

SHOW_PATHS_FMT = ("device='%d' serial='%z' multipath='%m' host_wwpn='%N' "
                  "target_wwnn='%n' host_wwpn='%R' target_wwpn='%r' "
                  "host_adapter='%a'")
SHOW_MAPS_FMT = "name=%n multipath='%w' sysfs='%d' paths='%N'"


def _extract_mpath_data(cmd, show_verb):
    """ Parse output from specifed command output via load_shell_content."""
    data, _err = util.subp(cmd, capture=True)
    result = []
    for line in data.splitlines():
        mp_dict = util.load_shell_content(line, add_empty=True)
        LOG.debug('Extracted multipath %s fields: %s', show_verb, mp_dict)
        if mp_dict:
            result.append(mp_dict)

    return result


def show_paths():
    """ Query multipathd for paths output and return a dict of the values."""
    cmd = ['multipathd', 'show', 'paths', 'raw', 'format', SHOW_PATHS_FMT]
    return _extract_mpath_data(cmd, 'paths')


def show_maps():
    """ Query multipathd for maps output and return a dict of the values."""
    cmd = ['multipathd', 'show', 'maps', 'raw', 'format', SHOW_MAPS_FMT]
    return _extract_mpath_data(cmd, 'maps')


def dmname_to_blkdev_mapping():
    """ Use dmsetup ls output to build a dict of DM_NAME, /dev/dm-x values."""
    data, _err = util.subp(['dmsetup', 'ls', '-o', 'blkdevname'], capture=True)
    mapping = {}
    if data and data.strip() != "No devices found":
        LOG.debug('multipath: dmsetup ls output:\n%s', data)
        for line in data.splitlines():
            if line:
                dm_name, blkdev = line.split('\t')
                # (dm-1) -> /dev/dm-1
                mapping[dm_name] = '/dev/' + blkdev.strip('()')

    return mapping


def is_mpath_device(devpath):
    """ Check if devpath is a multipath device, returns boolean. """
    info = udev.udevadm_info(devpath)
    if info.get('DM_UUID', '').startswith('mpath-'):
        return True

    return False


def is_mpath_member(devpath):
    """ Check if a device is a multipath member (a path), returns boolean. """
    try:
        util.subp(['multipath', '-c', devpath], capture=True)
        return True
    except util.ProcessExecutionError:
        return False


def is_mpath_partition(devpath):
    """ Check if a device is a multipath partition, returns boolean. """
    if devpath.startswith('/dev/dm-'):
        if 'DM_PART' in udev.udevadm_info(devpath):
            LOG.debug("%s is multipath device partition", devpath)
            return True

    return False


def mpath_partition_to_mpath_id(devpath):
    """ Return the mpath id of a multipath partition. """
    info = udev.udevadm_info(devpath)
    if 'DM_MPATH' in info:
        return info['DM_MPATH']

    return None


def remove_partition(devpath, retries=10):
    """ Remove a multipath partition mapping. """
    LOG.debug('multipath: removing multipath partition: %s', devpath)
    for _ in range(0, retries):
        util.subp(['dmsetup', 'remove', '--force', '--retry', devpath])
        udev.udevadm_settle()
        if not os.path.exists(devpath):
            return

    util.wait_for_removal(devpath)


def remove_map(map_id, retries=10):
    """ Remove a multipath device mapping. """
    LOG.debug('multipath: removing multipath map: %s', map_id)
    devpath = '/dev/mapper/%s' % map_id
    for _ in range(0, retries):
        util.subp(['multipath', '-v3', '-R3', '-f', map_id], rcs=[0, 1])
        udev.udevadm_settle()
        if not os.path.exists(devpath):
            return

    util.wait_for_removal(devpath)


def find_mpath_members(multipath_id, paths=None):
    """ Return a list of device path for each member of aspecified mpath_id."""
    if not paths:
        paths = show_paths()

    members = ['/dev/' + path['device']
               for path in paths if path['multipath'] == multipath_id]
    return members


def find_mpath_id(devpath, maps=None):
    """ Return the mpath_id associated with a specified device path. """
    if not maps:
        maps = show_maps()

    for mpmap in maps:
        if '/dev/' + mpmap['sysfs'] == devpath:
            name = mpmap.get('name')
            if name:
                return name
            return mpmap['multipath']

    return None


def find_mpath_id_by_path(devpath, paths=None):
    """ Return the mpath_id associated with a specified device path. """
    if not paths:
        paths = show_paths()

    for path in paths:
        if devpath == '/dev/' + path['device']:
            return path['multipath']

    return None


def find_mpath_id_by_parent(multipath_id, partnum=None):
    """ Return the mpath_id associated with a specified device path. """
    devmap = dmname_to_blkdev_mapping()
    LOG.debug('multipath: dm_name blk map: %s', devmap)
    dm_name = multipath_id
    if partnum:
        dm_name += "-part%d" % int(partnum)

    return (dm_name, devmap.get(dm_name))


def multipath_supported():
    """Return a boolean indicating if multipath is supported."""
    try:
        multipath_assert_supported()
        return True
    except RuntimeError:
        return False


def multipath_assert_supported():
    """ Determine if the runtime system supports multipath.
    returns: True if system supports multipath
    raises: RuntimeError: if system does not support multipath
    """
    missing_progs = [p for p in ('multipath', 'multipathd')
                     if not util.which(p)]
    if missing_progs:
        raise RuntimeError(
            "Missing multipath utils: %s" % ','.join(missing_progs))

# vi: ts=4 expandtab syntax=python
