# This file is part of curtin. See LICENSE file for copyright and license info.

"""
This module provides a mechanism for shutting down virtual storage layers on
top of a block device, making it possible to reuse the block device without
having to reboot the system
"""

import errno
import os
import time

from curtin import (block, udev, util)
from curtin.swap import is_swap_device
from curtin.block import lvm
from curtin.block import mdadm
from curtin.block import zfs
from curtin.log import LOG

# poll frequenty, but wait up to 60 seconds total
MDADM_RELEASE_RETRIES = [0.4] * 150


def _define_handlers_registry():
    """
    returns instantiated dev_types
    """
    return {
        'partition': {'shutdown': wipe_superblock,
                      'ident': identify_partition},
        'lvm': {'shutdown': shutdown_lvm, 'ident': identify_lvm},
        'crypt': {'shutdown': shutdown_crypt, 'ident': identify_crypt},
        'raid': {'shutdown': shutdown_mdadm, 'ident': identify_mdadm},
        'bcache': {'shutdown': shutdown_bcache, 'ident': identify_bcache},
        'disk': {'ident': lambda x: False, 'shutdown': wipe_superblock},
    }


def get_dmsetup_uuid(device):
    """
    get the dm uuid for a specified dmsetup device
    """
    blockdev = block.sysfs_to_devpath(device)
    (out, _) = util.subp(['dmsetup', 'info', blockdev, '-C', '-o', 'uuid',
                          '--noheadings'], capture=True)
    return out.strip()


def get_bcache_using_dev(device, strict=True):
    """
    Get the /sys/fs/bcache/ path of the bcache cache device bound to
    specified device
    """
    # FIXME: when block.bcache is written this should be moved there
    sysfs_path = block.sys_block_path(device)
    path = os.path.realpath(os.path.join(sysfs_path, 'bcache', 'cache'))
    if strict and not os.path.exists(path):
        err = OSError(
            "device '{}' did not have existing syspath '{}'".format(
                device, path))
        err.errno = errno.ENOENT
        raise err

    return path


def get_bcache_sys_path(device, strict=True):
    """
    Get the /sys/class/block/<device>/bcache path
    """
    sysfs_path = block.sys_block_path(device, strict=strict)
    path = os.path.join(sysfs_path, 'bcache')
    if strict and not os.path.exists(path):
        err = OSError(
            "device '{}' did not have existing syspath '{}'".format(
                device, path))
        err.errno = errno.ENOENT
        raise err

    return path


def maybe_stop_bcache_device(device):
    """Attempt to stop the provided device_path or raise unexpected errors."""
    bcache_stop = os.path.join(device, 'stop')
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


def shutdown_bcache(device):
    """
    Shut down bcache for specified bcache device

    1. Stop the cacheset that `device` is connected to
    2. Stop the 'device'
    """
    if not device.startswith('/sys/class/block'):
        raise ValueError('Invalid Device (%s): '
                         'Device path must start with /sys/class/block/',
                         device)

    LOG.info('Wiping superblock on bcache device: %s', device)
    _wipe_superblock(block.sysfs_to_devpath(device), exclusive=False)

    # bcache device removal should be fast but in an extreme
    # case, might require the cache device to flush large
    # amounts of data to a backing device.  The strategy here
    # is to wait for approximately 30 seconds but to check
    # frequently since curtin cannot proceed until devices
    # cleared.
    removal_retries = [0.2] * 150  # 30 seconds total
    bcache_shutdown_message = ('shutdown_bcache running on {} has determined '
                               'that the device has already been shut down '
                               'during handling of another bcache dev. '
                               'skipping'.format(device))

    if not os.path.exists(device):
        LOG.info(bcache_shutdown_message)
        return

    # get slaves [vdb1, vdc], allow for slaves to not have bcache dir
    try:
        slave_paths = [get_bcache_sys_path(k, strict=False) for k in
                       os.listdir(os.path.join(device, 'slaves'))]
    except util.FileMissingError as e:
        LOG.debug('Transient race, bcache slave path not found: %s', e)
        slave_paths = []

    # stop cacheset if it exists
    bcache_cache_sysfs = get_bcache_using_dev(device, strict=False)
    if not os.path.exists(bcache_cache_sysfs):
        LOG.info('bcache cacheset already removed: %s',
                 os.path.basename(bcache_cache_sysfs))
    else:
        LOG.info('stopping bcache cacheset at: %s', bcache_cache_sysfs)
        maybe_stop_bcache_device(bcache_cache_sysfs)
        try:
            util.wait_for_removal(bcache_cache_sysfs, retries=removal_retries)
        except OSError:
            LOG.info('Failed to stop bcache cacheset %s', bcache_cache_sysfs)
            raise

        # let kernel settle before the next remove
        udev.udevadm_settle()

    # after stopping cache set, we may need to stop the device
    # both the dev and sysfs entry should be gone.

    # we know the bcacheN device is really gone when we've removed:
    #  /sys/class/block/{bcacheN}
    #  /sys/class/block/slaveN1/bcache
    #  /sys/class/block/slaveN2/bcache
    bcache_block_sysfs = get_bcache_sys_path(device, strict=False)
    to_check = [device] + slave_paths
    found_devs = [os.path.exists(p) for p in to_check]
    LOG.debug('os.path.exists on blockdevs:\n%s',
              list(zip(to_check, found_devs)))
    if not any(found_devs):
        LOG.info('bcache backing device already removed: %s (%s)',
                 bcache_block_sysfs, device)
        LOG.debug('bcache slave paths checked: %s', slave_paths)
        return
    else:
        LOG.info('stopping bcache backing device at: %s', bcache_block_sysfs)
        maybe_stop_bcache_device(bcache_block_sysfs)
        try:
            # wait for them all to go away
            for dev in [device, bcache_block_sysfs] + slave_paths:
                util.wait_for_removal(dev, retries=removal_retries)
        except OSError:
            LOG.info('Failed to stop bcache backing device %s',
                     bcache_block_sysfs)
            raise

    return


def shutdown_lvm(device):
    """
    Shutdown specified lvm device.
    """
    device = block.sys_block_path(device)
    # lvm devices have a dm directory that containes a file 'name' containing
    # '{volume group}-{logical volume}'. The volume can be freed using lvremove
    name_file = os.path.join(device, 'dm', 'name')
    lvm_name = util.load_file(name_file).strip()
    (vg_name, lv_name) = lvm.split_lvm_name(lvm_name)
    vg_lv_name = "%s/%s" % (vg_name, lv_name)
    devname = "/dev/" + vg_lv_name

    # wipe contents of the logical volume first
    LOG.info('Wiping lvm logical volume: %s', devname)
    block.quick_zero(devname, partitions=False)

    # remove the logical volume
    LOG.debug('using "lvremove" on %s', vg_lv_name)
    util.subp(['lvremove', '--force', '--force', vg_lv_name])

    # if that was the last lvol in the volgroup, get rid of volgroup
    if len(lvm.get_lvols_in_volgroup(vg_name)) == 0:
        pvols = lvm.get_pvols_in_volgroup(vg_name)
        util.subp(['vgremove', '--force', '--force', vg_name], rcs=[0, 5])

        # wipe the underlying physical volumes
        for pv in pvols:
            LOG.info('Wiping lvm physical volume: %s', pv)
            block.quick_zero(pv, partitions=False)

    # refresh lvmetad
    lvm.lvm_scan()


def shutdown_crypt(device):
    """
    Shutdown specified cryptsetup device
    """
    blockdev = block.sysfs_to_devpath(device)
    util.subp(['cryptsetup', 'remove', blockdev], capture=True)


def shutdown_mdadm(device):
    """
    Shutdown specified mdadm device.
    """

    blockdev = block.sysfs_to_devpath(device)

    LOG.info('Wiping superblock on raid device: %s', device)
    _wipe_superblock(blockdev, exclusive=False)

    md_devs = (
        mdadm.md_get_devices_list(blockdev) +
        mdadm.md_get_spares_list(blockdev))
    mdadm.set_sync_action(blockdev, action="idle")
    mdadm.set_sync_action(blockdev, action="frozen")
    for mddev in md_devs:
        try:
            mdadm.fail_device(blockdev, mddev)
            mdadm.remove_device(blockdev, mddev)
        except util.ProcessExecutionError as e:
            LOG.debug('Non-fatal error clearing raid array: %s', e.stderr)
            pass

    LOG.debug('using mdadm.mdadm_stop on dev: %s', blockdev)
    mdadm.mdadm_stop(blockdev)

    for mddev in md_devs:
        mdadm.zero_device(mddev)

    # mdadm stop operation is asynchronous so we must wait for the kernel to
    # release resources. For more details see  LP: #1682456
    try:
        for wait in MDADM_RELEASE_RETRIES:
            if mdadm.md_present(block.path_to_kname(blockdev)):
                time.sleep(wait)
            else:
                LOG.debug('%s has been removed', blockdev)
                break

        if mdadm.md_present(block.path_to_kname(blockdev)):
            raise OSError('Timeout exceeded for removal of %s', blockdev)

    except OSError:
        LOG.critical('Failed to stop mdadm device %s', device)
        if os.path.exists('/proc/mdstat'):
            LOG.critical("/proc/mdstat:\n%s", util.load_file('/proc/mdstat'))
        raise


def wipe_superblock(device):
    """
    Wrapper for block.wipe_volume compatible with shutdown function interface
    """
    blockdev = block.sysfs_to_devpath(device)
    # when operating on a disk that used to have a dos part table with an
    # extended partition, attempting to wipe the extended partition will fail
    try:
        if block.is_extended_partition(blockdev):
            LOG.info("extended partitions do not need wiping, so skipping:"
                     " '%s'", blockdev)
            return
    except OSError as e:
        if util.is_file_not_found_exc(e):
            LOG.debug('Device to wipe disappeared: %s', e)
            LOG.debug('/proc/partitions says: %s',
                      util.load_file('/proc/partitions'))

            (parent, partnum) = block.get_blockdev_for_partition(blockdev)
            out, _e = util.subp(['sfdisk', '-d', parent],
                                capture=True, combine_capture=True)
            LOG.debug('Disk partition info:\n%s', out)
            return
        else:
            raise e

    # gather any partitions
    partitions = block.get_sysfs_partitions(device)

    # release zfs member by exporting the pool
    if zfs.zfs_supported() and block.is_zfs_member(blockdev):
        poolname = zfs.device_to_poolname(blockdev)
        # only export pools that have been imported
        if poolname in zfs.zpool_list():
            try:
                zfs.zpool_export(poolname)
            except util.ProcessExecutionError as e:
                LOG.warning('Failed to export zpool "%s": %s', poolname, e)

    if is_swap_device(blockdev):
        shutdown_swap(blockdev)

    # some volumes will be claimed by the bcache layer but do not surface
    # an actual /dev/bcacheN device which owns the parts (backing, cache)
    # The result is that some volumes cannot be wiped while bcache claims
    # the device.  Resolve this by stopping bcache layer on those volumes
    # if present.
    for bcache_path in ['bcache', 'bcache/set']:
        stop_path = os.path.join(device, bcache_path)
        if os.path.exists(stop_path):
            LOG.debug('Attempting to release bcache layer from device: %s',
                      device)
            maybe_stop_bcache_device(stop_path)
            continue

    _wipe_superblock(blockdev)

    # if we had partitions, make sure they've been removed
    if partitions:
        LOG.debug('%s had partitions, issuing partition reread', device)
        retries = [.5, .5, 1, 2, 5, 7]
        for attempt, wait in enumerate(retries):
            try:
                # only rereadpt on wiped device
                block.rescan_block_devices(devices=[blockdev])
                # may raise IOError, OSError due to wiped partition table
                curparts = block.get_sysfs_partitions(device)
                if len(curparts) == 0:
                    return
            except (IOError, OSError):
                if attempt + 1 >= len(retries):
                    raise

            LOG.debug("%s partitions still present, rereading pt"
                      " (%s/%s).  sleeping %ss before retry",
                      device, attempt + 1, len(retries), wait)
            time.sleep(wait)


def _wipe_superblock(blockdev, exclusive=True):
    """ No checks, just call wipe_volume """

    retries = [1, 3, 5, 7]
    LOG.info('wiping superblock on %s', blockdev)
    for attempt, wait in enumerate(retries):
        LOG.debug('wiping %s attempt %s/%s',
                  blockdev, attempt + 1, len(retries))
        try:
            block.wipe_volume(blockdev, mode='superblock', exclusive=exclusive)
            LOG.debug('successfully wiped device %s on attempt %s/%s',
                      blockdev, attempt + 1, len(retries))
            return
        except OSError:
            if attempt + 1 >= len(retries):
                raise
            else:
                LOG.debug("wiping device '%s' failed on attempt"
                          " %s/%s.  sleeping %ss before retry",
                          blockdev, attempt + 1, len(retries), wait)
                time.sleep(wait)


def identify_lvm(device):
    """
    determine if specified device is a lvm device
    """
    return (block.path_to_kname(device).startswith('dm') and
            get_dmsetup_uuid(device).startswith('LVM'))


def identify_crypt(device):
    """
    determine if specified device is dm-crypt device
    """
    return (block.path_to_kname(device).startswith('dm') and
            get_dmsetup_uuid(device).startswith('CRYPT'))


def identify_mdadm(device):
    """
    determine if specified device is a mdadm device
    """
    # RAID0 and 1 devices can be partitioned and the partitions are *not*
    # raid devices with a sysfs 'md' subdirectory
    partition = identify_partition(device)
    return block.path_to_kname(device).startswith('md') and not partition


def identify_bcache(device):
    """
    determine if specified device is a bcache device
    """
    # bcache devices can be partitioned and the partitions are *not*
    # bcache devices with a sysfs 'slaves' subdirectory
    partition = identify_partition(device)
    return block.path_to_kname(device).startswith('bcache') and not partition


def identify_partition(device):
    """
    determine if specified device is a partition
    """
    path = os.path.join(block.sys_block_path(device), 'partition')
    return os.path.exists(path)


def shutdown_swap(path):
    """release swap device from kernel swap pool if present"""
    procswaps = util.load_file('/proc/swaps')
    for swapline in procswaps.splitlines():
        if swapline.startswith(path):
            msg = ('Removing %s from active use as swap device, '
                   'needed for storage config' % path)
            LOG.warning(msg)
            util.subp(['swapoff', path])
            return


def get_holders(device):
    """
    Look up any block device holders, return list of knames
    """
    # block.sys_block_path works when given a /sys or /dev path
    sysfs_path = block.sys_block_path(device)
    # get holders
    holders = os.listdir(os.path.join(sysfs_path, 'holders'))
    LOG.debug("devname '%s' had holders: %s", device, holders)
    return holders


def gen_holders_tree(device):
    """
    generate a tree representing the current storage hirearchy above 'device'
    """
    device = block.sys_block_path(device)
    dev_name = block.path_to_kname(device)
    # the holders for a device should consist of the devices in the holders/
    # dir in sysfs and any partitions on the device. this ensures that a
    # storage tree starting from a disk will include all devices holding the
    # disk's partitions
    holder_paths = ([block.sys_block_path(h) for h in get_holders(device)] +
                    block.get_sysfs_partitions(device))
    # the DEV_TYPE registry contains a function under the key 'ident' for each
    # device type entry that returns true if the device passed to it is of the
    # correct type. there should never be a situation in which multiple
    # identify functions return true. therefore, it will always work to take
    # the device type with the first identify function that returns true as the
    # device type for the current device. in the event that no identify
    # functions return true, the device will be treated as a disk
    # (DEFAULT_DEV_TYPE). the identify function for disk never returns true.
    # the next() builtin in python will not raise a StopIteration exception if
    # there is a default value defined
    dev_type = next((k for k, v in DEV_TYPES.items() if v['ident'](device)),
                    DEFAULT_DEV_TYPE)
    return {
        'device': device, 'dev_type': dev_type, 'name': dev_name,
        'holders': [gen_holders_tree(h) for h in holder_paths],
    }


def plan_shutdown_holder_trees(holders_trees):
    """
    plan best order to shut down holders in, taking into account high level
    storage layers that may have many devices below them

    returns a sorted list of descriptions of storage config entries including
    their path in /sys/block and their dev type

    can accept either a single storage tree or a list of storage trees assumed
    to start at an equal place in storage hirearchy (i.e. a list of trees
    starting from disk)
    """
    # holds a temporary registry of holders to allow cross references
    # key = device sysfs path, value = {} of priority level, shutdown function
    reg = {}

    # normalize to list of trees
    if not isinstance(holders_trees, (list, tuple)):
        holders_trees = [holders_trees]

    def flatten_holders_tree(tree, level=0):
        """
        add entries from holders tree to registry with level key corresponding
        to how many layers from raw disks the current device is at
        """
        device = tree['device']

        # always go with highest level if current device has been
        # encountered already. since the device and everything above it is
        # re-added to the registry it ensures that any increase of level
        # required here will propagate down the tree
        # this handles a scenario like mdadm + bcache, where the backing
        # device for bcache is a 3nd level item like mdadm, but the cache
        # device is 1st level (disk) or second level (partition), ensuring
        # that the bcache item is always considered higher level than
        # anything else regardless of whether it was added to the tree via
        # the cache device or backing device first
        if device in reg:
            level = max(reg[device]['level'], level)

        reg[device] = {'level': level, 'device': device,
                       'dev_type': tree['dev_type']}

        # handle holders above this level
        for holder in tree['holders']:
            flatten_holders_tree(holder, level=level + 1)

    # flatten the holders tree into the registry
    for holders_tree in holders_trees:
        flatten_holders_tree(holders_tree)

    # return list of entry dicts with highest level first
    return [reg[k] for k in sorted(reg, key=lambda x: reg[x]['level'] * -1)]


def format_holders_tree(holders_tree):
    """
    draw a nice dirgram of the holders tree
    """
    # spacer styles based on output of 'tree --charset=ascii'
    spacers = (('`-- ', ' ' * 4), ('|-- ', '|' + ' ' * 3))

    def format_tree(tree):
        """
        format entry and any subentries
        """
        result = [tree['name']]
        holders = tree['holders']
        for (holder_no, holder) in enumerate(holders):
            spacer_style = spacers[min(len(holders) - (holder_no + 1), 1)]
            subtree_lines = format_tree(holder)
            for (line_no, line) in enumerate(subtree_lines):
                result.append(spacer_style[min(line_no, 1)] + line)
        return result

    return '\n'.join(format_tree(holders_tree))


def get_holder_types(tree):
    """
    get flattened list of types of holders in holders tree and the devices
    they correspond to
    """
    types = {(tree['dev_type'], tree['device'])}
    for holder in tree['holders']:
        types.update(get_holder_types(holder))
    return types


def assert_clear(base_paths):
    """
    Check if all paths in base_paths are clear to use
    """
    valid = ('disk', 'partition')
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]
    base_paths = [block.sys_block_path(path) for path in base_paths]
    for holders_tree in [gen_holders_tree(p) for p in base_paths]:
        if any(holder_type not in valid and path not in base_paths
               for (holder_type, path) in get_holder_types(holders_tree)):
            raise OSError('Storage not clear, remaining:\n{}'
                          .format(format_holders_tree(holders_tree)))


def clear_holders(base_paths, try_preserve=False):
    """
    Clear all storage layers depending on the devices specified in 'base_paths'
    A single device or list of devices can be specified.
    Device paths can be specified either as paths in /dev or /sys/block
    Will throw OSError if any holders could not be shut down
    """
    # handle single path
    if not isinstance(base_paths, (list, tuple)):
        base_paths = [base_paths]

    # get current holders and plan how to shut them down
    holder_trees = [gen_holders_tree(path) for path in base_paths]
    LOG.info('Current device storage tree:\n%s',
             '\n'.join(format_holders_tree(tree) for tree in holder_trees))
    ordered_devs = plan_shutdown_holder_trees(holder_trees)
    LOG.info('Shutdown Plan:\n%s', "\n".join(map(str, ordered_devs)))

    # run shutdown functions
    for dev_info in ordered_devs:
        dev_type = DEV_TYPES.get(dev_info['dev_type'])
        shutdown_function = dev_type.get('shutdown')
        if not shutdown_function:
            continue

        if try_preserve and shutdown_function in DATA_DESTROYING_HANDLERS:
            LOG.info('shutdown function for holder type: %s is destructive. '
                     'attempting to preserve data, so skipping' %
                     dev_info['dev_type'])
            continue

        if os.path.exists(dev_info['device']):
            LOG.info("shutdown running on holder type: '%s' syspath: '%s'",
                     dev_info['dev_type'], dev_info['device'])
            shutdown_function(dev_info['device'])


def start_clear_holders_deps():
    """
    prepare system for clear holders to be able to scan old devices
    """
    # a mdadm scan has to be started in case there is a md device that needs to
    # be detected. if the scan fails, it is either because there are no mdadm
    # devices on the system, or because there is a mdadm device in a damaged
    # state that could not be started. due to the nature of mdadm tools, it is
    # difficult to know which is the case. if any errors did occur, then ignore
    # them, since no action needs to be taken if there were no mdadm devices on
    # the system, and in the case where there is some mdadm metadata on a disk,
    # but there was not enough to start the array, the call to wipe_volume on
    # all disks and partitions should be sufficient to remove the mdadm
    # metadata
    mdadm.mdadm_assemble(scan=True, ignore_errors=True)
    # scan and activate for logical volumes
    lvm.lvm_scan()
    lvm.activate_volgroups()
    # the bcache module needs to be present to properly detect bcache devs
    # on some systems (precise without hwe kernel) it may not be possible to
    # lad the bcache module bcause it is not present in the kernel. if this
    # happens then there is no need to halt installation, as the bcache devices
    # will never appear and will never prevent the disk from being reformatted
    util.load_kernel_module('bcache')

    if not zfs.zfs_supported():
        LOG.warning('zfs filesystem is not supported in this environment')


# anything that is not identified can assumed to be a 'disk' or similar
DEFAULT_DEV_TYPE = 'disk'
# handlers that should not be run if an attempt is being made to preserve data
DATA_DESTROYING_HANDLERS = [wipe_superblock]
# types of devices that could be encountered by clear holders and functions to
# identify them and shut them down
DEV_TYPES = _define_handlers_registry()

# vi: ts=4 expandtab syntax=python
