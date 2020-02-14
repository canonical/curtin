# This file is part of curtin. See LICENSE file for copyright and license info.

"""
This module provides a mechanism for shutting down virtual storage layers on
top of a block device, making it possible to reuse the block device without
having to reboot the system
"""

import glob
import os
import time

from curtin import (block, udev, util)
from curtin.swap import is_swap_device
from curtin.block import bcache
from curtin.block import lvm
from curtin.block import mdadm
from curtin.block import multipath
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


def shutdown_bcache(device):
    """
    Shut down bcache for specified bcache device

    1. wipe the bcache device contents
    2. extract the cacheset uuid (if cached)
    3. extract the backing device
    4. stop cacheset (if present)
    5. stop the bcacheN device
    6. wait for removal of sysfs path to bcacheN, bcacheN/bcache and
       backing/bcache to go away
    """
    if not device.startswith('/sys/class/block'):
        raise ValueError('Invalid Device (%s): '
                         'Device path must start with /sys/class/block/',
                         device)

    # bcache device removal should be fast but in an extreme
    # case, might require the cache device to flush large
    # amounts of data to a backing device.  The strategy here
    # is to wait for approximately 30 seconds but to check
    # frequently since curtin cannot proceed until devices
    # cleared.
    bcache_shutdown_message = ('shutdown_bcache running on {} has determined '
                               'that the device has already been shut down '
                               'during handling of another bcache dev. '
                               'skipping'.format(device))

    if not os.path.exists(device):
        LOG.info(bcache_shutdown_message)
        return

    LOG.info('Wiping superblock on bcache device: %s', device)
    _wipe_superblock(block.sysfs_to_devpath(device), exclusive=False)

    # collect required information before stopping bcache device
    # UUID from /sys/fs/cache/UUID
    cset_uuid = bcache.get_attached_cacheset(device)
    # /sys/class/block/vdX which is a backing dev of device (bcacheN)
    backing_sysfs = bcache.get_backing_device(block.path_to_kname(device))
    # /sys/class/block/bcacheN/bache
    bcache_sysfs = bcache.sysfs_path(device, strict=False)

    # stop cacheset if one is presennt
    if cset_uuid:
        LOG.info('%s was attached to cacheset %s, stopping cacheset',
                 device, cset_uuid)
        bcache.stop_cacheset(cset_uuid)

        # let kernel settle before the next remove
        udev.udevadm_settle()
        LOG.info('bcache cacheset stopped: %s', cset_uuid)

    # test and log whether the device paths are still present
    to_check = [bcache_sysfs, backing_sysfs]
    found_devs = [os.path.exists(p) for p in to_check]
    LOG.debug('os.path.exists on blockdevs:\n%s',
              list(zip(to_check, found_devs)))
    if not any(found_devs):
        LOG.info('bcache backing device already removed: %s (%s)',
                 bcache_sysfs, device)
        LOG.debug('bcache backing device checked: %s', backing_sysfs)
    else:
        LOG.info('stopping bcache backing device at: %s', bcache_sysfs)
        bcache.stop_device(bcache_sysfs)
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

    LOG.info('Discovering raid devices and spares for %s', device)
    md_devs = (
        mdadm.md_get_devices_list(blockdev) +
        mdadm.md_get_spares_list(blockdev))
    mdadm.set_sync_action(blockdev, action="idle")
    mdadm.set_sync_action(blockdev, action="frozen")

    LOG.info('Wiping superblock on raid device: %s', device)
    try:
        _wipe_superblock(blockdev, exclusive=False)
    except ValueError as e:
        # if the array is not functional, writes to the device may fail
        # and _wipe_superblock will raise ValueError for short writes
        # which happens on inactive raid volumes.  In that case we
        # shouldn't give up yet as we still want to disassemble
        # array and wipe members.  Other errors such as IOError or OSError
        # are unwelcome and will stop deployment.
        LOG.debug('Non-fatal error writing to array device %s, '
                  'proceeding with shutdown: %s', blockdev, e)

    LOG.info('Removing raid array members: %s', md_devs)
    for mddev in md_devs:
        try:
            mdadm.fail_device(blockdev, mddev)
            mdadm.remove_device(blockdev, mddev)
        except util.ProcessExecutionError as e:
            LOG.debug('Non-fatal error clearing raid array: %s', e.stderr)
            pass

    LOG.debug('using mdadm.mdadm_stop on dev: %s', blockdev)
    mdadm.mdadm_stop(blockdev)

    LOG.debug('Wiping mdadm member devices: %s' % md_devs)
    for mddev in md_devs:
        mdadm.zero_device(mddev, force=True)

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
        if not block.is_online(blockdev):
            LOG.debug("Device is not online (size=0), so skipping:"
                      " '%s'", blockdev)
            return

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
            LOG.debug('Attempting to release bcache layer from device: %s:%s',
                      device, stop_path)
            if stop_path.endswith('set'):
                rp = os.path.realpath(stop_path)
                bcache.stop_cacheset(rp)
            else:
                bcache._stop_device(stop_path)

    # the blockdev (e.g. /dev/sda2) may be a multipath partition which can
    # only be wiped via its device mapper device (e.g. /dev/dm-4)
    # check for this and determine the correct device mapper value to use.
    mp_dev = None
    mp_support = multipath.multipath_supported()
    if mp_support:
        parent, partnum = block.get_blockdev_for_partition(blockdev)
        parent_mpath_id = multipath.find_mpath_id_by_path(parent)
        if parent_mpath_id is not None:
            # construct multipath dmsetup id
            # <mpathid>-part%d -> /dev/dm-1
            mp_id, mp_dev = multipath.find_mpath_id_by_parent(parent_mpath_id,
                                                              partnum=partnum)
            # if we don't find a mapping then the mp partition has already been
            # wiped/removed
            if mp_dev:
                LOG.debug('Found multipath device over %s, wiping holder %s',
                          blockdev, mp_dev)

            # check if we can remove the parent mpath_id mapping; this is
            # is possible after removing all dependent mpath devices (like
            # mpath partitions.  Once the mpath parts are wiped and unmapped
            # we can remove the parent mpath mapping which releases the lock
            # on the underlying disk partitions.
            dm_map = multipath.dmname_to_blkdev_mapping()
            LOG.debug('dm map: %s', dm_map)
            parent_mp_dev = dm_map.get(parent_mpath_id)
            if parent_mp_dev is not None:
                parent_mp_holders = get_holders(parent_mp_dev)
                if len(parent_mp_holders) == 0:
                    LOG.debug('Parent multipath device (%s, %s) has no '
                              'holders, removing.', parent_mpath_id,
                              parent_mp_dev)
                    multipath.remove_map(parent_mpath_id)

    _wipe_superblock(mp_dev if mp_dev else blockdev)

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

    if mp_support:
        # multipath partitions are separate block devices (disks)
        if mp_dev or multipath.is_mpath_partition(blockdev):
            multipath.remove_partition(mp_dev if mp_dev else blockdev)
        # multipath devices must be hidden to utilize a single member (path)
        elif multipath.is_mpath_device(blockdev):
            mp_id = multipath.find_mpath_id(blockdev)
            multipath.remove_partition(blockdev)
            if mp_id:
                multipath.remove_map(mp_id)
            else:
                raise RuntimeError(
                    'Failed to find multipath id for %s' % blockdev)


def _wipe_superblock(blockdev, exclusive=True, strict=True):
    """ No checks, just call wipe_volume """

    retries = [1, 3, 5, 7]
    LOG.info('wiping superblock on %s', blockdev)
    for attempt, wait in enumerate(retries):
        LOG.debug('wiping %s attempt %s/%s',
                  blockdev, attempt + 1, len(retries))
        try:
            block.wipe_volume(blockdev, mode='superblock',
                              exclusive=exclusive, strict=strict)
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
    blockdev = block.sys_block_path(device)
    path = os.path.join(blockdev, 'partition')
    if os.path.exists(path):
        return True

    if multipath.is_mpath_partition(blockdev):
        return True

    return False


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

    # sort the trees to ensure we generate a consistent plan
    holders_trees = sorted(holders_trees, key=lambda x: x['device'])

    def htree_level(tree):
        if len(tree['holders']) == 0:
            return 0
        return 1 + sum(htree_level(holder) for holder in tree['holders'])

    def flatten_holders_tree(tree, level=0):
        """
        add entries from holders tree to registry with level key corresponding
        to how many layers from raw disks the current device is at
        """
        device = tree['device']
        device_level = htree_level(tree)

        # always go with highest level if current device has been
        # encountered already. since the device and everything above it is
        # re-added to the registry it ensures that any increase of level
        # required here will propagate down the tree
        # this handles a scenario like mdadm + bcache, where the backing
        # device for bcache is a 3rd level item like mdadm, but the cache
        # device is 1st level (disk) or second level (partition), ensuring
        # that the bcache item is always considered higher level than
        # anything else regardless of whether it was added to the tree via
        # the cache device or backing device first
        if device in reg:
            level = max(reg[device]['level'], level) + 1

        else:
            # first time device to registry, assume the larger value of the
            # current level or the length of its dependencies.
            level = max(device_level, level)

        reg[device] = {'level': level, 'device': device,
                       'dev_type': tree['dev_type']}

        # handle holders above this level
        for holder in tree['holders']:
            flatten_holders_tree(holder, level=level + 1)

    # flatten the holders tree into the registry
    for holders_tree in holders_trees:
        flatten_holders_tree(holders_tree)

    def devtype_order(dtype):
        """Return the order in which we want to clear device types, higher
         value should be cleared first.

        :param: dtype: string. A device types name from the holders registry,
                see _define_handlers_registry()
        :returns: integer
        """
        dev_type_order = [
            'disk', 'partition', 'bcache', 'lvm', 'raid', 'crypt']
        return 1 + dev_type_order.index(dtype)

    # return list of entry dicts with greatest htree depth. The 'level' value
    # indicates the number of additional devices that are "below" this device.
    # Devices must be cleared in descending 'level' value.  For devices which
    # have the same 'level' value, we sort within the 'level' by devtype order.
    return [reg[k]
            for k in sorted(reg, reverse=True,
                            key=lambda x: (reg[x]['level'],
                                           devtype_order(reg[x]['dev_type'])))]


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
    base_paths = [block.sys_block_path(path, strict=False)
                  for path in base_paths]
    for holders_tree in [gen_holders_tree(p)
                         for p in base_paths if os.path.exists(p)]:
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
    # collect detail on any assembling arrays
    for md in [md for md in glob.glob('/dev/md*')
               if not os.path.isdir(md) and not identify_partition(md)]:
        mdstat = None
        if os.path.exists('/proc/mdstat'):
            mdstat = util.load_file('/proc/mdstat')
            LOG.debug("/proc/mdstat:\n%s", mdstat)
            found = [line for line in mdstat.splitlines()
                     if os.path.basename(md) in line]
            # in some cases we have a /dev/md0 device node
            # but the kernel has already renamed the device /dev/md127
            if len(found) == 0:
                LOG.debug('Ignoring md device %s, not present in mdstat', md)
                continue

        # give it a second poke to encourage running
        try:
            LOG.debug('Activating mdadm array %s', md)
            (out, err) = mdadm.mdadm_run(md)
            LOG.debug('MDADM run on %s stdout:\n%s\nstderr:\n%s', md, out, err)
        except util.ProcessExecutionError:
            LOG.debug('Non-fatal error when starting mdadm device %s', md)

        # extract details if we can
        try:
            (out, err) = mdadm.mdadm_query_detail(md, export=False,
                                                  rawoutput=True)
            LOG.debug('MDADM detail on %s stdout:\n%s\nstderr:\n%s',
                      md, out, err)
        except util.ProcessExecutionError:
            LOG.debug('Non-fatal error when querying mdadm detail on %s', md)

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
