# This file is part of curtin. See LICENSE file for copyright and license info.

import errno
import os

from curtin import util
from curtin.log import LOG
from . import sys_block_path

# Wait up to 20 minutes (150 + 300 + 750 = 1200 seconds)
BCACHE_RETRIES = [sleep for nap in [1, 2, 5] for sleep in [nap] * 150]


def superblock_asdict(device=None, data=None):
    """ Convert output from bcache-super-show into a dictionary"""

    if not device and not data:
        raise ValueError('Supply a device name, or data to parse')

    if not data:
        try:
            data, _err = util.subp(['bcache-super-show', device], capture=True)
        except util.ProcessExecutionError as e:
            LOG.debug('Failed to parse bcache superblock on %s:%s',
                      device, e)
            return None
    bcache_super = {}
    for line in data.splitlines():
        if not line:
            continue
        values = [val for val in line.split('\t') if val]
        bcache_super.update({values[0]: values[1]})

    return bcache_super


def parse_sb_version(device=None, sbdict=None):
    """ Parse bcache 'sb_version' field to integer if possible.

    """
    if not device and not sbdict:
        raise ValueError('Supply a device name or bcache superblock dict')

    if not sbdict:
        sbdict = superblock_asdict(device=device)
        if not sbdict:
            LOG.info('Cannot parse sb.version without bcache superblock')
            return None
    if not isinstance(sbdict, dict):
        raise ValueError('Invalid sbdict type, must be dict')

    sb_version = sbdict.get('sb.version')
    try:
        # 'sb.version': '1 [backing device]'
        # 'sb.version': '3 [caching device]'
        version = int(sb_version.split()[0])
    except (AttributeError, ValueError):
        LOG.warning("Failed to parse bcache 'sb.version' field"
                    " as integer: %s", sb_version)
        raise

    return version


def _check_bcache_type(device, sysfs_attr, sb_version, superblock=False):
    """ helper for checking bcache type via sysfs or bcache superblock. """
    if not superblock:
        if not device.endswith('bcache'):
            sys_block = os.path.join(sys_block_path(device), 'bcache')
        else:
            sys_block = device
        bcache_sys_attr = os.path.join(sys_block, sysfs_attr)
        LOG.debug('path exists %s', bcache_sys_attr)
        return os.path.exists(bcache_sys_attr)
    else:
        return parse_sb_version(device=device) == sb_version


def is_backing(device, superblock=False):
    """ Test if device is a bcache backing device

    A runtime check for an active bcache backing device is to
    examine /sys/class/block/<kname>/bcache/label

    However if a device is not active then read the superblock
    of the device and check that sb.version == 1"""
    return _check_bcache_type(device, 'label', 1, superblock=superblock)


def is_caching(device, superblock=False):
    """ Test if device is a bcache caching device

    A runtime check for an active bcache backing device is to
    examine /sys/class/block/<kname>/bcache/cache_replacement_policy

    However if a device is not active then read the superblock
    of the device and check that sb.version == 3"""

    LOG.debug('Checking if %s is bcache caching device', device)
    return _check_bcache_type(device, 'cache_replacement_policy', 3,
                              superblock=superblock)


def sysfs_path(device, strict=True):
    """ Return /sys/class/block/<device>/bcache path for device. """
    path = os.path.join(sys_block_path(device, strict=strict), 'bcache')
    if strict and not os.path.exists(path):
        err = OSError(
            "device '{}' did not have existing syspath '{}'".format(
                device, path))
        err.errno = errno.ENOENT
        raise err

    return path


def write_label(label, device):
    """ write label to bcache device """
    bcache_sys_attr = os.path.join(sysfs_path(device), 'label')
    util.write_file(bcache_sys_attr, content=label, mode=None)


def get_attached_cacheset(device):
    """  return the sysfs path to an attached cacheset. """
    bcache_cache = os.path.join(sysfs_path(device), 'cache')
    if os.path.exists(bcache_cache):
        return os.path.basename(os.path.realpath(bcache_cache))

    return None


def get_cacheset_members(cset_uuid):
    """ return a list of sysfs paths to backing devices
        attached to the specified cache set.

    Example:
      % get_cacheset_members('08307315-48e7-4e46-8742-2ec37d615829')
      ['/sys/devices/pci0000:00/0000:00:08.0/virtio5/block/vdc/bcache',
       '/sys/devices/pci0000:00/0000:00:07.0/virtio4/block/vdb/bcache',
       '/sys/devices/pci0000:00/0000:00:06.0/virtio3/block/vda/vda1/bcache']
    """
    cset_path = '/sys/fs/bcache/%s' % cset_uuid
    members = []
    if os.path.exists(cset_path):
        # extract bdev* links
        bdevs = [link for link in os.listdir(cset_path)
                 if link.startswith('bdev')]
        # resolve symlink to target
        members = [os.path.realpath("%s/%s" % (cset_path, bdev))
                   for bdev in bdevs]

    return members


def get_cacheset_cachedev(cset_uuid):
    """ Return a sysfs path to a cacheset cache device's bcache dir."""

    # XXX: bcache cachesets only have a single cache0 entry
    cachedev = '/sys/fs/bcache/%s/cache0' % cset_uuid
    if os.path.exists(cachedev):
        return os.path.realpath(cachedev)

    return None


def get_backing_device(bcache_kname):
    """ For a given bcacheN kname, return the backing device
        bcache sysfs dir.

        bcache0 -> /sys/.../devices/.../device/bcache
    """
    bcache_deps = '/sys/class/block/%s/slaves' % bcache_kname

    try:
        # if the bcache device is deleted, this may fail
        deps = os.listdir(bcache_deps)
    except util.FileMissingError as e:
        LOG.debug('Transient race, bcache slave path not found: %s', e)
        return None

    # a running bcache device has two entries in slaves, the cacheset
    # device, and the backing device. There may only be the backing
    # device (if a bcache device is found but not currently attached
    # to a cacheset.
    if len(deps) == 0:
        raise RuntimeError(
            '%s unexpected empty dir: %s' % (bcache_kname, bcache_deps))

    for dev in (sysfs_path(dep) for dep in deps):
        if is_backing(dev):
            return dev

    return None


def stop_cacheset(cset_uuid):
    """stop specified bcache cacheset."""
    # we may be called with a full path or just the uuid
    if cset_uuid.startswith('/sys/fs/bcache/'):
        cset_device = cset_uuid
    else:
        cset_device = "/sys/fs/bcache/%s" % cset_uuid
    LOG.info('Stopping bcache set device: %s', cset_device)
    _stop_device(cset_device)


def stop_device(device):
    """Stop the specified bcache device."""
    if not device.startswith('/sys'):
        raise ValueError('Invalid device %s, must be sysfs path' % device)

    if not any(f(device) for f in (is_backing, is_caching)):
        raise ValueError('Cannot stop non-bcache device: %s' % device)

    LOG.debug('Stopping bcache layer on %s', device)
    _stop_device(device)


def _stop_device(device):
    """  write to sysfs 'stop' and wait for path to be removed

    The caller needs to ensure that supplied path to the device
    is a 'bcache' sysfs path on a device.  This may be one of the
    following scenarios:

    Cacheset:
      /sys/fs/bcache/<uuid>/

    Bcache device:
     /sys/class/block/bcache0/bcache

    Backing device
     /sys/class/block/vdb/bcache

    Cached device
     /sys/class/block/nvme0n1p1/bcache/set

    To support all of these, we append 'stop' to the path
    and write '1' and then wait for the 'stop' path to
    be removed.
    """
    bcache_stop = os.path.join(device, 'stop')
    if not os.path.exists(bcache_stop):
        LOG.debug('bcache._stop_device: already removed %s', bcache_stop)
        return

    LOG.debug('bcache._stop_device: device=%s stop_path=%s',
              device, bcache_stop)
    try:
        util.write_file(bcache_stop, '1', mode=None)
    except (IOError, OSError) as e:
        # Note: if we get any exceptions in the above exception classes
        # it is a result of attempting to write "1" into the sysfs path
        # The range of errors changes depending on when we race with
        # the kernel asynchronously removing the sysfs path. Therefore
        # we log the exception errno we got, but do not re-raise as
        # the calling process is watching whether the same sysfs path
        # is being removed;  if it fails to go away then we'll have
        # a log of the exceptions to debug.
        LOG.debug('Error writing to bcache stop file %s, device removed: %s',
                  bcache_stop, e)
    finally:
        util.wait_for_removal(bcache_stop, retries=BCACHE_RETRIES)


# vi: ts=4 expandtab syntax=python
