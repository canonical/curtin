# This file is part of curtin. See LICENSE file for copyright and license info.

"""
Wrap calls to the zfsutils-linux package (zpool, zfs) for creating zpools
and volumes."""

import os

from curtin.config import merge_config
from curtin import util
from . import blkid

ZPOOL_DEFAULT_PROPERTIES = {
    'ashift': 12,
    'version': 28,
}

ZFS_DEFAULT_PROPERTIES = {
    'atime': 'off',
    'canmount': 'off',
    'normalization': 'formD',
}

ZFS_UNSUPPORTED_ARCHES = ['i386']
ZFS_UNSUPPORTED_RELEASES = ['precise', 'trusty']


def _join_flags(optflag, params):
    """
    Insert optflag for each param in params and return combined list.

    :param optflag: String of the optional flag, like '-o'
    :param params: dictionary of parameter names and values
    :returns: List of strings
    :raises: ValueError: if params are of incorrect type

    Example:
        optflag='-o', params={'foo': 1, 'bar': 2} =>
            ['-o', 'foo=1', '-o', 'bar=2']
    """

    if not isinstance(optflag, str) or not optflag:
        raise ValueError("Invalid optflag: %s", optflag)

    if not isinstance(params, dict):
        raise ValueError("Invalid params: %s", params)

    # zfs flags and params require string booleans ('on', 'off')
    # yaml implicity converts those and others to booleans, we
    # revert that here
    def _b2s(value):
        if not isinstance(value, bool):
            return value
        if value:
            return 'on'
        return 'off'

    return [] if not params else (
        [param for opt in zip([optflag] * len(params),
                              ["%s=%s" % (k, _b2s(v))
                               for (k, v) in params.items()])
         for param in opt])


def _join_pool_volume(poolname, volume):
    """
    Combine poolname and volume.
    """
    if not poolname or not volume:
        raise ValueError('Invalid pool (%s) or volume (%s)', poolname, volume)

    return os.path.normpath("%s/%s" % (poolname, volume))


def zfs_supported():
    """ Determine if the runtime system supports zfs.
    returns: True if system supports zfs
    raises: RuntimeError: if system does not support zfs
    """
    arch = util.get_platform_arch()
    if arch in ZFS_UNSUPPORTED_ARCHES:
        raise RuntimeError("zfs is not supported on architecture: %s" % arch)

    release = util.lsb_release()['codename']
    if release in ZFS_UNSUPPORTED_RELEASES:
        raise RuntimeError("zfs is not supported on release: %s" % release)

    try:
        util.subp(['modinfo', 'zfs'], capture=True)
    except util.ProcessExecutionError as err:
        if err.stderr.startswith("modinfo: ERROR: Module zfs not found."):
            raise RuntimeError("zfs kernel module is not available: %s" % err)

    return True


def zpool_create(poolname, vdevs, mountpoint=None, altroot=None,
                 pool_properties=None, zfs_properties=None):
    """
    Create a zpool called <poolname> comprised of devices specified in <vdevs>.

    :param poolname: String used to name the pool.
    :param vdevs: An iterable of strings of block devices paths which *should*
                  start with '/dev/disk/by-id/' to follow best practices.
    :param pool_properties: A dictionary of key, value pairs to be passed
                            to `zpool create` with the `-o` flag as properties
                            of the zpool.  If value is None, then
                            ZPOOL_DEFAULT_PROPERTIES will be used.
    :param zfs_properties: A dictionary of key, value pairs to be passed
                           to `zpool create` with the `-O` flag as properties
                           of the filesystems created under the pool.  If the
                           value is None, then ZFS_DEFAULT_PROPERTIES will be
                           used.
    :returns: None on success.
    :raises: ValueError: raises exceptions on missing/badd input
    :raises: ProcessExecutionError: raised on unhandled exceptions from
                                    invoking `zpool create`.
    """
    if not isinstance(poolname, util.string_types) or not poolname:
        raise ValueError("Invalid poolname: %s", poolname)

    if isinstance(vdevs, util.string_types) or isinstance(vdevs, dict):
        raise TypeError("Invalid vdevs: expected list-like iterable")
    else:
        try:
            vdevs = list(vdevs)
        except TypeError:
            raise TypeError("vdevs must be iterable, not: %s" % str(vdevs))

    pool_cfg = ZPOOL_DEFAULT_PROPERTIES.copy()
    if pool_properties:
        merge_config(pool_cfg, pool_properties)
    zfs_cfg = ZFS_DEFAULT_PROPERTIES.copy()
    if zfs_properties:
        merge_config(zfs_cfg, zfs_properties)

    options = _join_flags('-o', pool_cfg)
    options.extend(_join_flags('-O', zfs_cfg))

    if mountpoint:
        options.extend(_join_flags('-O', {'mountpoint': mountpoint}))

    if altroot:
        options.extend(['-R', altroot])

    cmd = ["zpool", "create"] + options + [poolname] + vdevs
    util.subp(cmd, capture=True)


def zfs_create(poolname, volume, zfs_properties=None):
    """
    Create a filesystem dataset within the specified zpool.

    :param poolname: String used to specify the pool in which to create the
                     filesystem.
    :param volume: String used as the name of the filesystem.
    :param zfs_properties: A dict of properties to be passed
                           to `zfs create` with the `-o` flag as properties
                           of the filesystems created under the pool. If
                           value is None then no properties will be set on
                           the filesystem.
    :returns: None
    :raises: ValueError: raises exceptions on missing/bad input.
    :raises: ProcessExecutionError: raised on unhandled exceptions from
                                    invoking `zfs create`.
    """
    if not isinstance(poolname, util.string_types) or not poolname:
        raise ValueError("Invalid poolname: %s", poolname)

    if not isinstance(volume, util.string_types) or not volume:
        raise ValueError("Invalid volume: %s", volume)

    zfs_cfg = {}
    if zfs_properties:
        merge_config(zfs_cfg, zfs_properties)

    options = _join_flags('-o', zfs_cfg)

    cmd = ["zfs", "create"] + options + [_join_pool_volume(poolname, volume)]
    util.subp(cmd, capture=True)

    # mount volume if it canmount=noauto
    if zfs_cfg.get('canmount') == 'noauto':
        zfs_mount(poolname, volume)


def zfs_mount(poolname, volume):
    """
    Mount zfs pool/volume

    :param poolname: String used to specify the pool in which to create the
                     filesystem.
    :param volume: String used as the name of the filesystem.
    :returns: None
    :raises: ValueError: raises exceptions on missing/bad input.
    :raises: ProcessExecutionError: raised on unhandled exceptions from
                                    invoking `zfs mount`.
    """

    if not isinstance(poolname, util.string_types) or not poolname:
        raise ValueError("Invalid poolname: %s", poolname)

    if not isinstance(volume, util.string_types) or not volume:
        raise ValueError("Invalid volume: %s", volume)

    cmd = ['zfs', 'mount', _join_pool_volume(poolname, volume)]
    util.subp(cmd, capture=True)


def zpool_list():
    """
    Return a list of zfs pool names which have been imported

    :returns: List of strings
    """

    # -H drops the header, -o specifies an attribute to fetch
    out, _err = util.subp(['zpool', 'list', '-H', '-o', 'name'], capture=True)

    return out.splitlines()


def zpool_export(poolname):
    """
    Export specified zpool

    :param poolname: String used to specify the pool to export.
    :returns: None
    """

    if not isinstance(poolname, util.string_types) or not poolname:
        raise ValueError("Invalid poolname: %s", poolname)

    util.subp(['zpool', 'export', poolname])


def device_to_poolname(devname):
    """
    Use blkid information to map a devname to a zpool poolname
    stored in in 'LABEL' if devname is a zfs_member and LABEL
    is set.

    :param devname: A block device name
    :returns: String

    Example blkid output on a zfs vdev:
        {'/dev/vdb1': {'LABEL': 'rpool',
                       'PARTUUID': '52dff41a-49be-44b3-a36a-1b499e570e69',
                       'TYPE': 'zfs_member',
                       'UUID': '12590398935543668673',
                       'UUID_SUB': '7809435738165038086'}}

    device_to_poolname('/dev/vdb1') would return 'rpool'
    """
    if not isinstance(devname, util.string_types) or not devname:
        raise ValueError("device_to_poolname: invalid devname: '%s'" % devname)

    blkid_info = blkid(devs=[devname])
    if not blkid_info or devname not in blkid_info:
        return

    vdev = blkid_info.get(devname)
    vdev_type = vdev.get('TYPE')
    label = vdev.get('LABEL')
    if vdev_type == 'zfs_member' and label:
        return label

# vi: ts=4 expandtab syntax=python
