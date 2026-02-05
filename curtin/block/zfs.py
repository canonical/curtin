# This file is part of curtin. See LICENSE file for copyright and license info.

"""
Wrap calls to the zfsutils-linux package (zpool, zfs) for creating zpools
and volumes."""

import os
import tempfile
import secrets
import shutil
from contextlib import ExitStack
from pathlib import Path

from curtin.config import merge_config
from curtin.udev import udevadm_settle
from curtin import distro
from curtin import util
from . import blkid, get_supported_filesystems

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

# The keystore consists of the LUKS header, which is a size we can configure,
# and the usable volume size of the keystore.  While the file we store here is
# rather small we leave a little room. In LP: #2107381 we learned that the
# cryptsetup detected offset can vary, so choosing a LUKS header size avoids
# surprises later where luksFormat fails due to insufficient volume size.
# The mechanism behind that: cryptsetup LUKS2_hdr_get_storage_params() decides
# on several values, including offset to the actual usable device space.
# offset may be supplied with the cryptset --offset argument, or it will be
# chosen in a way based on the BLKIOOPT / BLKALIGNOFF ioctls in cryptsetup
# device_topology_alignment(), which is a bit overkill for the keystore, so
# just choose a size and keep it small.
LUKS_HEADER_SIZE = 16 << 20
USABLE_VOLUME_SIZE = 4 << 20
KEYSTORE_VOLUME_SIZE = LUKS_HEADER_SIZE + USABLE_VOLUME_SIZE


class ZPoolEncryption:
    def __init__(self, vdevs, poolname, style, keyfile):
        self.poolname = poolname
        self.style = style
        self.keyfile = keyfile
        self.system_key = None
        self.vdevs = vdevs

    def get_system_key(self):
        if self.system_key is None:
            fd, self.system_key = tempfile.mkstemp()
            with open(fd, "wb") as writer:
                writer.write(secrets.token_bytes(32))
        return self.system_key

    def validate(self):
        if self.style is None:
            return

        if not self.poolname:
            raise ValueError("valid pool name required")

        if self.style != "luks_keystore":
            raise ValueError(f"unrecognized encryption style {self.style}")

        if not self.keyfile:
            raise ValueError(f"keyfile required when using {self.style}")

        if not Path(self.keyfile).is_file():
            raise ValueError(f"invalid keyfile path {self.keyfile}")

    def in_use(self):
        return self.style is not None

    def dataset_properties(self):
        if not self.in_use():
            return {}

        ks_system_key = self.get_system_key()
        return {
            "encryption": "on",
            "keylocation": f"file://{ks_system_key}",
            "keyformat": "raw",
            # as we'll be formatting this as another fs, ext4,
            # mounting before the ext4 is no help
            "canmount": "off",
        }

    def setup(self, storage_config, context):
        if not self.in_use():
            return

        # Create the dataset for the keystore.  This is a bit special as it
        # won't be ZFS despite being on the zpool.
        zfs_create(
            self.poolname, "keystore", {"encryption": "off"},
            str(KEYSTORE_VOLUME_SIZE),
        )
        keystore_volume = f"/dev/zvol/{self.poolname}/keystore"
        udevadm_settle(exists=keystore_volume)

        with ExitStack() as es:
            for vdev in self.vdevs:
                es.enter_context(util.FlockEx(vdev))

            # cryptsetup format and open this keystore. pick a fixed offset
            # size, in sectors, to work with the fixed volume size.
            cmd = [
                "cryptsetup",
                "luksFormat",
                "--offset",
                str(LUKS_HEADER_SIZE // 512),
                keystore_volume,
                self.keyfile
            ]

            # strace has shown that udevd does indeed probe this keystore
            with util.FlockEx(keystore_volume):
                util.subp(cmd, capture=True)

            udevadm_settle()

            dm_name = f"keystore-{self.poolname}"
            cmd = [
                "cryptsetup", "open", "--type", "luks", keystore_volume,
                dm_name, "--key-file", self.keyfile,
            ]
            util.subp(cmd, capture=True)

            dmpath = f"/dev/mapper/{dm_name}"
            udevadm_settle(exists=dmpath)

        with ExitStack() as es:
            # format as ext4, mount it, move the previously-generated systemkey
            es.enter_context(util.FlockEx(dmpath))
            cmd = ["mke2fs", "-t", "ext4", dmpath, "-L", dm_name]
            util.subp(cmd, capture=True)

            keystore_root = f"/run/keystore/{self.poolname}"

            es.enter_context(util.mount(dmpath, keystore_root))
            ks_system_key = f"{keystore_root}/system.key"
            shutil.move(self.system_key, ks_system_key)
            Path(ks_system_key).chmod(0o400)

            # update the pool with the real keylocation
            keylocation = f"keylocation=file://{ks_system_key}"
            cmd = ["zfs", "set", keylocation, self.poolname]
            util.subp(cmd, capture=True)

        # LP: #2140415
        # We used to `cryptsetup close dmpath` here.
        # This is a problem for recent dracut, which needs to see a crypto_LUKS
        # device during the install in order for the needed tools to end up in
        # the initrd.


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

    r = []
    for k, v in params.items():
        if v is not None:
            r.append(optflag)
            r.append("%s=%s" % (k, _b2s(v)))
    return r


def _join_pool_volume(poolname, volume):
    """
    Combine poolname and volume.
    """
    if not poolname or not volume:
        raise ValueError('Invalid pool (%s) or volume (%s)', poolname, volume)

    return os.path.normpath("%s/%s" % (poolname, volume))


def zfs_supported():
    """Return a boolean indicating if zfs is supported."""
    try:
        zfs_assert_supported()
        return True
    except RuntimeError:
        return False


def zfs_assert_supported():
    """ Determine if the runtime system supports zfs.
    returns: True if system supports zfs
    raises: RuntimeError: if system does not support zfs
    """
    arch = util.get_platform_arch()
    if arch in ZFS_UNSUPPORTED_ARCHES:
        raise RuntimeError("zfs is not supported on architecture: %s" % arch)

    release = distro.lsb_release()['codename']
    if release in ZFS_UNSUPPORTED_RELEASES:
        raise RuntimeError("zfs is not supported on release: %s" % release)

    if 'zfs' not in get_supported_filesystems():
        try:
            util.load_kernel_module('zfs')
        except util.ProcessExecutionError as err:
            raise RuntimeError("Failed to load 'zfs' kernel module: %s" % err)

    missing_progs = [p for p in ('zpool', 'zfs') if not util.which(p)]
    if missing_progs:
        raise RuntimeError("Missing zfs utils: %s" % ','.join(missing_progs))


def zpool_create(poolname, vdevs, storage_config=None, context=None,
                 mountpoint=None, altroot=None,
                 default_features=True,
                 pool_properties=None, zfs_properties=None,
                 encryption_style=None, keyfile=None):
    """
    Create a zpool called <poolname> comprised of devices specified in <vdevs>.

    :param poolname: String used to name the pool.
    :param vdevs: An iterable of strings of block devices paths which *should*
                  start with '/dev/disk/by-id/' to follow best practices.
    :param default_features: If true, keep the default features enabled.
    :param pool_properties: A dictionary of key, value pairs to be passed
                            to `zpool create` with the `-o` flag as properties
                            of the zpool.  If value is None, then
                            ZPOOL_DEFAULT_PROPERTIES will be used.
                            `key: null` may be use to unset a
                            ZPOOL_DEFAULT_PROPERTIES value.
    :param zfs_properties: A dictionary of key, value pairs to be passed
                           to `zpool create` with the `-O` flag as properties
                           of the filesystems created under the pool.  If the
                           value is None, then ZFS_DEFAULT_PROPERTIES will be
                           used. `key: null` may be use to unset a
                            ZFS_DEFAULT_PROPERTIES value.
    :param encryption_style: 'luks_keystore' or None.  If luks_keystore,
                             a Ubiquity-style keystore is created, and the
                             `keyfile` argument is mandatory.
    :param keyfile: Use with `encryption_style` to create an encrypted ZFS
                    install.  The `keyfile` contains the password of the
                    encryption key.  The target system will prompt for this
                    password in order to mount the disk.
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

    encryption = ZPoolEncryption(vdevs, poolname, encryption_style, keyfile)
    encryption.validate()
    if encryption.in_use():
        merge_config(zfs_cfg, encryption.dataset_properties())

    options = _join_flags('-o', pool_cfg)
    options.extend(_join_flags('-O', zfs_cfg))

    if mountpoint:
        options.extend(_join_flags('-O', {'mountpoint': mountpoint}))

    if altroot:
        options.extend(['-R', altroot])

    if not default_features:
        options.extend(['-d'])

    cmd = ["zpool", "create"] + options + [poolname] + vdevs
    util.subp(cmd, capture=True)

    # Trigger generation of zpool.cache file
    cmd = ["zpool", "set", "cachefile=/etc/zfs/zpool.cache", poolname]
    util.subp(cmd, capture=True)

    if encryption.in_use():
        encryption.setup(storage_config, context)


def zfs_create(poolname, volume, zfs_properties=None, size=None):
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
    :param size: integer size in bytes of the dataset.  Not normally required.
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
    if size is not None:
        options.extend(["-V", str(size)])

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


def get_zpool_from_config(cfg, *, only_encrypted=False):
    """Parse a curtin storage config and return a list
       of zpools that were created.
    """
    if not cfg:
        return []

    if 'storage' not in cfg:
        return []

    zpools = []
    sconfig = cfg['storage']['config']
    for item in sconfig:
        if item['type'] == 'zpool':
            if only_encrypted and item.get('encryption_style') is None:
                continue
            zpools.append(item['pool'])
        elif item['type'] == 'format':
            if item['fstype'] == 'zfsroot':
                if only_encrypted:
                    # Currently, encryption is not supported in conjunction
                    # with "zfsroot".
                    continue
                # curtin.commands.blockmeta sets pool='rpool' for zfsroot
                zpools.append('rpool')

    return zpools


# vi: ts=4 expandtab syntax=python
