# This file is part of curtin. See LICENSE file for copyright and license info.

import errno
import os
import time

from curtin import util
from curtin.log import LOG
from curtin.udev import udevadm_settle
from . import dev_path, sys_block_path

# Wait up to 20 minutes (150 + 300 + 750 = 1200 seconds)
BCACHE_RETRIES = [sleep for nap in [1, 2, 5] for sleep in [nap] * 150]
BCACHE_REGISTRATION_RETRY = [0.2] * 60


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


def attach_backing_to_cacheset(backing_device, cache_device, cset_uuid):
    LOG.info("Attaching backing device to cacheset: "
             "{} -> {} cset.uuid: {}".format(backing_device, cache_device,
                                             cset_uuid))
    backing_device_sysfs = sys_block_path(backing_device)
    attach = os.path.join(backing_device_sysfs, "bcache", "attach")
    util.write_file(attach, cset_uuid, mode=None)


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


def register_bcache(bcache_device):
    LOG.debug('register_bcache: %s > /sys/fs/bcache/register', bcache_device)
    util.write_file('/sys/fs/bcache/register', bcache_device, mode=None)


def set_cache_mode(bcache_dev, cache_mode):
    LOG.info("Setting cache_mode on {} to {}".format(bcache_dev, cache_mode))
    cache_mode_file = '/sys/block/{}/bcache/cache_mode'.format(bcache_dev)
    util.write_file(cache_mode_file, cache_mode, mode=None)


def validate_bcache_ready(bcache_device, bcache_sys_path):
    """ check if bcache is ready, dump info

    For cache devices, we expect to find a cacheN symlink
    which will point to the underlying cache device; Find
    this symlink, read it and compare bcache_device
    specified in the parameters.

    For backing devices, we expec to find a dev symlink
    pointing to the bcacheN device to which the backing
    device is enslaved.  From the dev symlink, we can
    read the bcacheN holders list, which should contain
    the backing device kname.

    In either case, if we fail to find the correct
    symlinks in sysfs, this method will raise
    an OSError indicating the missing attribute.
    """
    # cacheset
    # /sys/fs/bcache/<uuid>

    # cache device
    # /sys/class/block/<cdev>/bcache/set -> # .../fs/bcache/uuid

    # backing
    # /sys/class/block/<bdev>/bcache/cache -> # .../block/bcacheN
    # /sys/class/block/<bdev>/bcache/dev -> # .../block/bcacheN

    if bcache_sys_path.startswith('/sys/fs/bcache'):
        LOG.debug("validating bcache caching device '%s' from sys_path"
                  " '%s'", bcache_device, bcache_sys_path)
        # we expect a cacheN symlink to point to bcache_device/bcache
        sys_path_links = [os.path.join(bcache_sys_path, l)
                          for l in os.listdir(bcache_sys_path)]
        cache_links = [l for l in sys_path_links
                       if os.path.islink(l) and (
                          os.path.basename(l).startswith('cache'))]

        if len(cache_links) == 0:
            msg = ('Failed to find any cache links in %s:%s' % (
                   bcache_sys_path, sys_path_links))
            raise OSError(msg)

        for link in cache_links:
            target = os.readlink(link)
            LOG.debug('Resolving symlink %s -> %s', link, target)
            # cacheN  -> ../../../devices/.../<bcache_device>/bcache
            # basename(dirname(readlink(link)))
            target_cache_device = os.path.basename(
                os.path.dirname(target))
            if os.path.basename(bcache_device) == target_cache_device:
                LOG.debug('Found match: bcache_device=%s target_device=%s',
                          bcache_device, target_cache_device)
                return
            else:
                msg = ('Cache symlink %s ' % target_cache_device +
                       'points to incorrect device: %s' % bcache_device)
                raise OSError(msg)
    elif bcache_sys_path.startswith('/sys/class/block'):
        LOG.debug("validating bcache backing device '%s' from sys_path"
                  " '%s'", bcache_device, bcache_sys_path)
        # we expect a 'dev' symlink to point to the bcacheN device
        bcache_dev = os.path.join(bcache_sys_path, 'dev')
        if os.path.islink(bcache_dev):
            bcache_dev_link = (
                os.path.basename(os.readlink(bcache_dev)))
            LOG.debug('bcache device %s using bcache kname: %s',
                      bcache_sys_path, bcache_dev_link)

            bcache_slaves_path = os.path.join(bcache_dev, 'slaves')
            slaves = os.listdir(bcache_slaves_path)
            LOG.debug('bcache device %s has slaves: %s',
                      bcache_sys_path, slaves)
            if os.path.basename(bcache_device) in slaves:
                LOG.debug('bcache device %s found in slaves',
                          os.path.basename(bcache_device))
                return
            else:
                msg = ('Failed to find bcache device %s' % bcache_device +
                       'in slaves list %s' % slaves)
                raise OSError(msg)
        else:
            msg = 'didnt find "dev" attribute on: %s', bcache_dev
            return OSError(msg)

    else:
        LOG.debug("Failed to validate bcache device '%s' from sys_path"
                  " '%s'", bcache_device, bcache_sys_path)
        msg = ('sysfs path %s does not appear to be a bcache device' %
               bcache_sys_path)
        return ValueError(msg)


def ensure_bcache_is_registered(bcache_device, expected, retry=None):
    """ Test that bcache_device is found at an expected path and
        re-register the device if it's not ready.

        Retry the validation and registration as needed.
    """
    if not retry:
        retry = BCACHE_REGISTRATION_RETRY

    for attempt, wait in enumerate(retry):
        # find the actual bcache device name via sysfs using the
        # backing device's holders directory.
        LOG.debug('check just created bcache %s if it is registered,'
                  ' try=%s', bcache_device, attempt + 1)
        try:
            udevadm_settle()
            if os.path.exists(expected):
                LOG.debug('Found bcache dev %s at expected path %s',
                          bcache_device, expected)
                validate_bcache_ready(bcache_device, expected)
            else:
                msg = 'bcache device path not found: %s' % expected
                LOG.debug(msg)
                raise ValueError(msg)

            # if bcache path exists and holders are > 0 we can return
            LOG.debug('bcache dev %s at path %s successfully registered'
                      ' on attempt %s/%s',  bcache_device, expected,
                      attempt + 1, len(retry))
            return

        except (OSError, IndexError, ValueError):
            # Some versions of bcache-tools will register the bcache device
            # as soon as we run make-bcache using udev rules, so wait for
            # udev to settle, then try to locate the dev, on older versions
            # we need to register it manually though
            LOG.debug('bcache device was not registered, registering %s '
                      'at /sys/fs/bcache/register', bcache_device)
            try:
                register_bcache(bcache_device)
            except IOError:
                # device creation is notoriously racy and this can trigger
                # "Invalid argument" IOErrors if it got created in "the
                # meantime" - just restart the function a few times to
                # check it all again
                pass

        LOG.debug("bcache dev %s not ready, waiting %ss",
                  bcache_device, wait)
        time.sleep(wait)

    # we've exhausted our retries
    LOG.warning('Repetitive error registering the bcache dev %s',
                bcache_device)
    raise RuntimeError("bcache device %s can't be registered" %
                       bcache_device)


def create_cache_device(cache_device):
    # /sys/class/block/XXX/YYY/
    cache_device_sysfs = sys_block_path(cache_device)

    if os.path.exists(os.path.join(cache_device_sysfs, "bcache")):
        LOG.debug('caching device already exists at {}/bcache. Read '
                  'cset.uuid'.format(cache_device_sysfs))
        (out, err) = util.subp(["bcache-super-show", cache_device],
                               capture=True)
        LOG.debug('bcache-super-show=[{}]'.format(out))
        [cset_uuid] = [line.split()[-1] for line in out.split("\n")
                       if line.startswith('cset.uuid')]
    else:
        LOG.debug('caching device does not yet exist at {}/bcache. Make '
                  'cache and get uuid'.format(cache_device_sysfs))
        # make the cache device, extracting cacheset uuid
        (out, err) = util.subp(["make-bcache", "-C", cache_device],
                               capture=True)
        LOG.debug('out=[{}]'.format(out))
        [cset_uuid] = [line.split()[-1] for line in out.split("\n")
                       if line.startswith('Set UUID:')]

    target_sysfs_path = '/sys/fs/bcache/%s' % cset_uuid
    ensure_bcache_is_registered(cache_device, target_sysfs_path)
    return cset_uuid


def create_backing_device(backing_device, cache_device, cache_mode, cset_uuid):
    backing_device_sysfs = sys_block_path(backing_device)
    target_sysfs_path = os.path.join(backing_device_sysfs, "bcache")

    # there should not be any pre-existing bcache device
    bdir = os.path.join(backing_device_sysfs, "bcache")
    if os.path.exists(bdir):
        raise RuntimeError(
            'Unexpected old bcache device: %s', backing_device)

    LOG.debug('Creating a backing device on %s', backing_device)
    util.subp(["make-bcache", "-B", backing_device])
    ensure_bcache_is_registered(backing_device, target_sysfs_path)

    # via the holders we can identify which bcache device we just created
    # for a given backing device
    from .clear_holders import get_holders
    holders = get_holders(backing_device)
    if len(holders) != 1:
        err = ('Invalid number {} of holding devices:'
               ' "{}"'.format(len(holders), holders))
        LOG.error(err)
        raise ValueError(err)
    [bcache_dev] = holders
    LOG.debug('The just created bcache device is {}'.format(holders))

    if cache_device:
        # if we specify both then we need to attach backing to cache
        if cset_uuid:
            attach_backing_to_cacheset(backing_device, cache_device, cset_uuid)
        else:
            msg = "Invalid cset_uuid: {}".format(cset_uuid)
            LOG.error(msg)
            raise ValueError(msg)

    if cache_mode:
        set_cache_mode(bcache_dev, cache_mode)
    return dev_path(bcache_dev)


# vi: ts=4 expandtab syntax=python
