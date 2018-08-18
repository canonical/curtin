# This file is part of curtin. See LICENSE file for copyright and license info.

from collections import OrderedDict, namedtuple
from curtin import (block, config, util)
from curtin.block import (bcache, mdadm, mkfs, clear_holders, lvm, iscsi, zfs)
from curtin.log import LOG, logged_time
from curtin.reporter import events

from . import populate_one_subcmd
from curtin.udev import compose_udev_equality, udevadm_settle, udevadm_trigger

import glob
import os
import platform
import string
import sys
import tempfile
import time

FstabData = namedtuple(
    "FstabData", ('spec', 'path', 'fstype', 'options', 'freq', 'passno',
                  'device'))
FstabData.__new__.__defaults__ = (None, None, None, "", "0", "0", None)


SIMPLE = 'simple'
SIMPLE_BOOT = 'simple-boot'
CUSTOM = 'custom'
BCACHE_REGISTRATION_RETRY = [0.2] * 60

CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'default': None, }),
     ('--fstype', {'help': 'root partition filesystem type',
                   'choices': ['ext4', 'ext3'], 'default': 'ext4'}),
     (('-t', '--target'),
      {'help': 'chroot to target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     ('--boot-fstype', {'help': 'boot partition filesystem type',
                        'choices': ['ext4', 'ext3'], 'default': None}),
     ('--umount', {'help': 'unmount any mounted filesystems before exit',
                   'action': 'store_true', 'default': False}),
     ('mode', {'help': 'meta-mode to use',
               'choices': [CUSTOM, SIMPLE, SIMPLE_BOOT]}),
     )
)


@logged_time("BLOCK_META")
def block_meta(args):
    # main entry point for the block-meta command.
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)
    dd_images = util.get_dd_images(cfg.get('sources', {}))
    if ((args.mode == CUSTOM or cfg.get("storage") is not None) and
            len(dd_images) == 0):
        meta_custom(args)
    elif args.mode in (SIMPLE, SIMPLE_BOOT) or len(dd_images) > 0:
        meta_simple(args)
    else:
        raise NotImplementedError("mode=%s is not implemented" % args.mode)


def logtime(msg, func, *args, **kwargs):
    with util.LogTimer(LOG.debug, msg):
        return func(*args, **kwargs)


def write_image_to_disk(source, dev):
    """
    Write disk image to block device
    """
    LOG.info('writing image to disk %s, %s', source, dev)
    extractor = {
        'dd-tgz': '|tar -xOzf -',
        'dd-txz': '|tar -xOJf -',
        'dd-tbz': '|tar -xOjf -',
        'dd-tar': '|smtar -xOf -',
        'dd-bz2': '|bzcat',
        'dd-gz': '|zcat',
        'dd-xz': '|xzcat',
        'dd-raw': ''
    }
    (devname, devnode) = block.get_dev_name_entry(dev)
    util.subp(args=['sh', '-c',
                    ('wget "$1" --progress=dot:mega -O - ' +
                     extractor[source['type']] + '| dd bs=4M of="$2"'),
                    '--', source['uri'], devnode])
    util.subp(['partprobe', devnode])
    udevadm_settle()
    paths = ["curtin", "system-data/var/lib/snapd"]
    return block.get_root_device([devname], paths=paths)


def get_bootpt_cfg(cfg, enabled=False, fstype=None, root_fstype=None):
    # 'cfg' looks like:
    #   enabled: boolean
    #   fstype: filesystem type (default to 'fstype')
    #   label:  filesystem label (default to 'boot')
    # parm enable can enable, but not disable
    # parm fstype overrides cfg['fstype']
    def_boot = (platform.machine() in ('aarch64') and
                not util.is_uefi_bootable())
    ret = {'enabled': def_boot, 'fstype': None, 'label': 'boot'}
    ret.update(cfg)
    if enabled:
        ret['enabled'] = True

    if ret['enabled'] and not ret['fstype']:
        if root_fstype:
            ret['fstype'] = root_fstype
        if fstype:
            ret['fstype'] = fstype
    return ret


def get_partition_format_type(cfg, machine=None, uefi_bootable=None):
    if machine is None:
        machine = platform.machine()
    if uefi_bootable is None:
        uefi_bootable = util.is_uefi_bootable()

    cfgval = cfg.get('format', None)
    if cfgval:
        return cfgval

    if uefi_bootable:
        return 'uefi'

    if machine in ['aarch64']:
        return 'gpt'
    elif machine.startswith('ppc64'):
        return 'prep'

    return "mbr"


def devsync(devpath):
    LOG.debug('devsync for %s', devpath)
    util.subp(['partprobe', devpath], rcs=[0, 1])
    udevadm_settle()
    for x in range(0, 10):
        if os.path.exists(devpath):
            LOG.debug('devsync happy - path %s now exists', devpath)
            return
        else:
            LOG.debug('Waiting on device path: %s', devpath)
            time.sleep(1)
    raise OSError('Failed to find device at path: %s', devpath)


def determine_partition_number(partition_id, storage_config):
    vol = storage_config.get(partition_id)
    partnumber = vol.get('number')
    if vol.get('flag') == "logical":
        if not partnumber:
            LOG.warn('partition \'number\' key not set in config:\n%s',
                     util.json_dumps(vol))
            partnumber = 5
            for key, item in storage_config.items():
                if item.get('type') == "partition" and \
                        item.get('device') == vol.get('device') and\
                        item.get('flag') == "logical":
                    if item.get('id') == vol.get('id'):
                        break
                    else:
                        partnumber += 1
    else:
        if not partnumber:
            LOG.warn('partition \'number\' key not set in config:\n%s',
                     util.json_dumps(vol))
            partnumber = 1
            for key, item in storage_config.items():
                if item.get('type') == "partition" and \
                        item.get('device') == vol.get('device'):
                    if item.get('id') == vol.get('id'):
                        break
                    else:
                        partnumber += 1
    return partnumber


def sanitize_dname(dname):
    """
    dnames should be sanitized before writing rule files, in case maas has
    emitted a dname with a special character

    only letters, numbers and '-' and '_' are permitted, as this will be
    used for a device path. spaces are also not permitted
    """
    valid = string.digits + string.ascii_letters + '-_'
    return ''.join(c if c in valid else '-' for c in dname)


def make_dname(volume, storage_config):
    state = util.load_command_environment()
    rules_dir = os.path.join(state['scratch'], "rules.d")
    vol = storage_config.get(volume)
    path = get_path_to_storage_volume(volume, storage_config)
    ptuuid = None
    dname = vol.get('name')
    if vol.get('type') in ["partition", "disk"]:
        (out, _err) = util.subp(["blkid", "-o", "export", path], capture=True,
                                rcs=[0, 2], retries=[1, 1, 1])
        for line in out.splitlines():
            if "PTUUID" in line or "PARTUUID" in line:
                ptuuid = line.split('=')[-1]
                break
    # we may not always be able to find a uniq identifier on devices with names
    if not ptuuid and vol.get('type') in ["disk", "partition"]:
        LOG.warning("Can't find a uuid for volume: {}. Skipping dname.".format(
            volume))
        return

    rule = [
        compose_udev_equality("SUBSYSTEM", "block"),
        compose_udev_equality("ACTION", "add|change"),
        ]
    if vol.get('type') == "disk":
        rule.append(compose_udev_equality('ENV{DEVTYPE}', "disk"))
        rule.append(compose_udev_equality('ENV{ID_PART_TABLE_UUID}', ptuuid))
    elif vol.get('type') == "partition":
        rule.append(compose_udev_equality('ENV{DEVTYPE}', "partition"))
        dname = storage_config.get(vol.get('device')).get('name') + \
            "-part%s" % determine_partition_number(volume, storage_config)
        rule.append(compose_udev_equality('ENV{ID_PART_ENTRY_UUID}', ptuuid))
    elif vol.get('type') == "raid":
        md_data = mdadm.mdadm_query_detail(path)
        md_uuid = md_data.get('MD_UUID')
        rule.append(compose_udev_equality("ENV{MD_UUID}", md_uuid))
    elif vol.get('type') == "bcache":
        # bind dname to bcache backing device's dev.uuid as the bcache minor
        # device numbers are not stable across reboots.
        backing_dev = get_path_to_storage_volume(vol.get('backing_device'),
                                                 storage_config)
        bcache_super = bcache.superblock_asdict(device=backing_dev)
        if bcache_super and bcache_super['sb.version'].startswith('1'):
                bdev_uuid = bcache_super['dev.uuid']
        rule.append(compose_udev_equality("ENV{CACHED_UUID}", bdev_uuid))
        bcache.write_label(sanitize_dname(dname), backing_dev)
    elif vol.get('type') == "lvm_partition":
        volgroup_name = storage_config.get(vol.get('volgroup')).get('name')
        dname = "%s-%s" % (volgroup_name, dname)
        rule.append(compose_udev_equality("ENV{DM_NAME}", dname))
    else:
        raise ValueError('cannot make dname for device with type: {}'
                         .format(vol.get('type')))

    # note: this sanitization is done here instead of for all name attributes
    #       at the beginning of storage configuration, as some devices, such as
    #       lvm devices may use the name attribute and may permit special chars
    sanitized = sanitize_dname(dname)
    if sanitized != dname:
        LOG.warning(
            "dname modified to remove invalid chars. old: '{}' new: '{}'"
            .format(dname, sanitized))
    rule.append("SYMLINK+=\"disk/by-dname/%s\"\n" % sanitized)
    LOG.debug("Writing dname udev rule '{}'".format(str(rule)))
    util.ensure_dir(rules_dir)
    rule_file = os.path.join(rules_dir, '{}.rules'.format(sanitized))
    util.write_file(rule_file, ', '.join(rule))


def get_poolname(info, storage_config):
    """ Resolve pool name from zfs info """

    LOG.debug('get_poolname for volume {}'.format(info))
    if info.get('type') == 'zfs':
        pool_id = info.get('pool')
        poolname = get_poolname(storage_config.get(pool_id), storage_config)
    elif info.get('type') == 'zpool':
        poolname = info.get('pool')
    else:
        msg = 'volume is not type zfs or zpool: %s' % info
        LOG.error(msg)
        raise ValueError(msg)

    return poolname


def get_path_to_storage_volume(volume, storage_config):
    # Get path to block device for volume. Volume param should refer to id of
    # volume in storage config

    LOG.debug('get_path_to_storage_volume for volume {}'.format(volume))
    devsync_vol = None
    vol = storage_config.get(volume)
    if not vol:
        raise ValueError("volume with id '%s' not found" % volume)

    # Find path to block device
    if vol.get('type') == "partition":
        partnumber = determine_partition_number(vol.get('id'), storage_config)
        disk_block_path = get_path_to_storage_volume(vol.get('device'),
                                                     storage_config)
        disk_kname = block.path_to_kname(disk_block_path)
        partition_kname = block.partition_kname(disk_kname, partnumber)
        volume_path = block.kname_to_path(partition_kname)
        devsync_vol = os.path.join(disk_block_path)

    elif vol.get('type') == "disk":
        # Get path to block device for disk. Device_id param should refer
        # to id of device in storage config
        if vol.get('serial'):
            volume_path = block.lookup_disk(vol.get('serial'))
        elif vol.get('path'):
            if vol.get('path').startswith('iscsi:'):
                i = iscsi.ensure_disk_connected(vol.get('path'))
                volume_path = os.path.realpath(i.devdisk_path)
            else:
                # resolve any symlinks to the dev_kname so
                # sys/class/block access is valid.  ie, there are no
                # udev generated values in sysfs
                volume_path = os.path.realpath(vol.get('path'))
        elif vol.get('wwn'):
            by_wwn = '/dev/disk/by-id/wwn-%s' % vol.get('wwn')
            volume_path = os.path.realpath(by_wwn)
        else:
            raise ValueError("serial, wwn or path to block dev must be \
                specified to identify disk")

    elif vol.get('type') == "lvm_partition":
        # For lvm partitions, a directory in /dev/ should be present with the
        # name of the volgroup the partition belongs to. We can simply append
        # the id of the lvm partition to the path of that directory
        volgroup = storage_config.get(vol.get('volgroup'))
        if not volgroup:
            raise ValueError("lvm volume group '%s' could not be found"
                             % vol.get('volgroup'))
        volume_path = os.path.join("/dev/", volgroup.get('name'),
                                   vol.get('name'))

    elif vol.get('type') == "dm_crypt":
        # For dm_crypted partitions, unencrypted block device is at
        # /dev/mapper/<dm_name>
        dm_name = vol.get('dm_name')
        if not dm_name:
            dm_name = vol.get('id')
        volume_path = os.path.join("/dev", "mapper", dm_name)

    elif vol.get('type') == "raid":
        # For raid partitions, block device is at /dev/mdX
        name = vol.get('name')
        volume_path = os.path.join("/dev", name)

    elif vol.get('type') == "bcache":
        # For bcache setups, the only reliable way to determine the name of the
        # block device is to look in all /sys/block/bcacheX/ dirs and see what
        # block devs are in the slaves dir there. Then, those blockdevs can be
        # checked against the kname of the devs in the config for the desired
        # bcache device. This is not very elegant though
        backing_device_path = get_path_to_storage_volume(
            vol.get('backing_device'), storage_config)
        backing_device_kname = block.path_to_kname(backing_device_path)
        sys_path = list(filter(lambda x: backing_device_kname in x,
                               glob.glob("/sys/block/bcache*/slaves/*")))[0]
        while "bcache" not in os.path.split(sys_path)[-1]:
            sys_path = os.path.split(sys_path)[0]
        bcache_kname = block.path_to_kname(sys_path)
        volume_path = block.kname_to_path(bcache_kname)
        LOG.debug('got bcache volume path {}'.format(volume_path))

    else:
        raise NotImplementedError("cannot determine the path to storage \
            volume '%s' with type '%s'" % (volume, vol.get('type')))

    # sync devices
    if not devsync_vol:
        devsync_vol = volume_path
    devsync(devsync_vol)

    LOG.debug('return volume path {}'.format(volume_path))
    return volume_path


def disk_handler(info, storage_config):
    _dos_names = ['dos', 'msdos']
    ptable = info.get('ptable')
    disk = get_path_to_storage_volume(info.get('id'), storage_config)

    if config.value_as_boolean(info.get('preserve')):
        # Handle preserve flag, verifying if ptable specified in config
        if config.value_as_boolean(ptable):
            current_ptable = block.get_part_table_type(disk)
            if not ((ptable in _dos_names and current_ptable in _dos_names) or
                    (ptable == 'gpt' and current_ptable == 'gpt')):
                raise ValueError(
                    "disk '%s' does not have correct partition table or "
                    "cannot be read, but preserve is set to true. "
                    "cannot continue installation." % info.get('id'))
        LOG.info("disk '%s' marked to be preserved, so keeping partition "
                 "table" % disk)
    else:
        # wipe the disk and create the partition table if instructed to do so
        if config.value_as_boolean(info.get('wipe')):
            block.wipe_volume(disk, mode=info.get('wipe'))
        if config.value_as_boolean(ptable):
            LOG.info("labeling device: '%s' with '%s' partition table", disk,
                     ptable)
            if ptable == "gpt":
                # Wipe both MBR and GPT that may be present on the disk.
                # N.B.: wipe_volume wipes 1M at front and end of the disk.
                # This could destroy disk data in filesystems that lived
                # there.
                block.wipe_volume(disk, mode='superblock')
            elif ptable in _dos_names:
                util.subp(["parted", disk, "--script", "mklabel", "msdos"])
            else:
                raise ValueError('invalid partition table type: %s', ptable)
        holders = clear_holders.get_holders(disk)
        if len(holders) > 0:
            LOG.info('Detected block holders on disk %s: %s', disk, holders)
            clear_holders.clear_holders(disk)
            clear_holders.assert_clear(disk)

    # Make the name if needed
    if info.get('name'):
        make_dname(info.get('id'), storage_config)


def getnumberoflogicaldisks(device, storage_config):
    logicaldisks = 0
    for key, item in storage_config.items():
        if item.get('device') == device and item.get('flag') == "logical":
            logicaldisks = logicaldisks + 1
    return logicaldisks


def find_previous_partition(disk_id, part_id, storage_config):
    last_partnum = None
    for item_id, command in storage_config.items():
        if item_id == part_id:
            break

        # skip anything not on this disk, not a 'partition' or 'extended'
        if command['type'] != 'partition' or command['device'] != disk_id:
            continue
        if command.get('flag') == "extended":
            continue

        last_partnum = determine_partition_number(item_id, storage_config)

    return last_partnum


def partition_handler(info, storage_config):
    device = info.get('device')
    size = info.get('size')
    flag = info.get('flag')
    disk_ptable = storage_config.get(device).get('ptable')
    partition_type = None
    if not device:
        raise ValueError("device must be set for partition to be created")
    if not size:
        raise ValueError("size must be specified for partition to be created")

    disk = get_path_to_storage_volume(device, storage_config)
    partnumber = determine_partition_number(info.get('id'), storage_config)
    disk_kname = block.path_to_kname(disk)
    disk_sysfs_path = block.sys_block_path(disk)
    # consider the disks logical sector size when calculating sectors
    try:
        lbs_path = os.path.join(disk_sysfs_path, 'queue', 'logical_block_size')
        with open(lbs_path, 'r') as f:
            logical_block_size_bytes = int(f.readline())
    except Exception:
        logical_block_size_bytes = 512
    LOG.debug(
        "{} logical_block_size_bytes: {}".format(disk_kname,
                                                 logical_block_size_bytes))

    if partnumber > 1:
        if partnumber == 5 and disk_ptable == "msdos":
            for key, item in storage_config.items():
                if item.get('type') == "partition" and \
                        item.get('device') == device and \
                        item.get('flag') == "extended":
                    extended_part_no = determine_partition_number(
                        key, storage_config)
                    break
            pnum = extended_part_no
        else:
            pnum = find_previous_partition(device, info['id'], storage_config)

        LOG.debug("previous partition number for '%s' found to be '%s'",
                  info.get('id'), pnum)
        partition_kname = block.partition_kname(disk_kname, pnum)
        previous_partition = os.path.join(disk_sysfs_path, partition_kname)
        LOG.debug("previous partition: {}".format(previous_partition))
        # XXX: sys/block/X/{size,start} is *ALWAYS* in 512b value
        previous_size = int(
            util.load_file(os.path.join(previous_partition, "size")))
        previous_size_sectors = int(previous_size * 512 /
                                    logical_block_size_bytes)
        previous_start = int(
            util.load_file(os.path.join(previous_partition, "start")))
        previous_start_sectors = int(previous_start * 512 /
                                     logical_block_size_bytes)
        LOG.debug("previous partition.size_sectors: {}".format(
                  previous_size_sectors))
        LOG.debug("previous partition.start_sectors: {}".format(
                  previous_start_sectors))

    # Align to 1M at the beginning of the disk and at logical partitions
    alignment_offset = int((1 << 20) / logical_block_size_bytes)
    if partnumber == 1:
        # start of disk
        offset_sectors = alignment_offset
    else:
        # further partitions
        if disk_ptable == "gpt" or flag != "logical":
            # msdos primary and any gpt part start after former partition end
            offset_sectors = previous_start_sectors + previous_size_sectors
        else:
            # msdos extended/logical partitions
            if flag == "logical":
                if partnumber == 5:
                    # First logical partition
                    # start at extended partition start + alignment_offset
                    offset_sectors = (previous_start_sectors +
                                      alignment_offset)
                else:
                    # Further logical partitions
                    # start at former logical partition end + alignment_offset
                    offset_sectors = (previous_start_sectors +
                                      previous_size_sectors +
                                      alignment_offset)

    length_bytes = util.human2bytes(size)
    # start sector is part of the sectors that define the partitions size
    # so length has to be "size in sectors - 1"
    length_sectors = int(length_bytes / logical_block_size_bytes) - 1
    # logical partitions can't share their start sector with the extended
    # partition and logical partitions can't go head-to-head, so we have to
    # realign and for that increase size as required
    if info.get('flag') == "extended":
        logdisks = getnumberoflogicaldisks(device, storage_config)
        length_sectors = length_sectors + (logdisks * alignment_offset)

    # Handle preserve flag
    if config.value_as_boolean(info.get('preserve')):
        return
    elif config.value_as_boolean(storage_config.get(device).get('preserve')):
        raise NotImplementedError("Partition '%s' is not marked to be \
            preserved, but device '%s' is. At this time, preserving devices \
            but not also the partitions on the devices is not supported, \
            because of the possibility of damaging partitions intended to be \
            preserved." % (info.get('id'), device))

    # Set flag
    # 'sgdisk --list-types'
    sgdisk_flags = {"boot": 'ef00',
                    "lvm": '8e00',
                    "raid": 'fd00',
                    "bios_grub": 'ef02',
                    "prep": '4100',
                    "swap": '8200',
                    "home": '8302',
                    "linux": '8300'}

    LOG.info("adding partition '%s' to disk '%s' (ptable: '%s')",
             info.get('id'), device, disk_ptable)
    LOG.debug("partnum: %s offset_sectors: %s length_sectors: %s",
              partnumber, offset_sectors, length_sectors)

    # Wipe the partition if told to do so, do not wipe dos extended partitions
    # as this may damage the extended partition table
    if config.value_as_boolean(info.get('wipe')):
        LOG.info("Preparing partition location on disk %s", disk)
        if info.get('flag') == "extended":
            LOG.warn("extended partitions do not need wiping, so skipping: "
                     "'%s'" % info.get('id'))
        else:
            # wipe the start of the new partition first by zeroing 1M at the
            # length of the previous partition
            wipe_offset = int(offset_sectors * logical_block_size_bytes)
            LOG.debug('Wiping 1M on %s at offset %s', disk, wipe_offset)
            # We don't require exclusive access as we're wiping data at an
            # offset and the current holder maybe part of the current storage
            # configuration.
            block.zero_file_at_offsets(disk, [wipe_offset], exclusive=False)

    if disk_ptable == "msdos":
        if flag in ["extended", "logical", "primary"]:
            partition_type = flag
        else:
            partition_type = "primary"
        cmd = ["parted", disk, "--script", "mkpart", partition_type,
               "%ss" % offset_sectors, "%ss" % str(offset_sectors +
                                                   length_sectors)]
        util.subp(cmd, capture=True)
    elif disk_ptable == "gpt":
        if flag and flag in sgdisk_flags:
            typecode = sgdisk_flags[flag]
        else:
            typecode = sgdisk_flags['linux']
        cmd = ["sgdisk", "--new", "%s:%s:%s" % (partnumber, offset_sectors,
               length_sectors + offset_sectors),
               "--typecode=%s:%s" % (partnumber, typecode), disk]
        util.subp(cmd, capture=True)
    else:
        raise ValueError("parent partition has invalid partition table")

    # Make the name if needed
    if storage_config.get(device).get('name') and partition_type != 'extended':
        make_dname(info.get('id'), storage_config)


def format_handler(info, storage_config):
    volume = info.get('volume')
    if not volume:
        raise ValueError("volume must be specified for partition '%s'" %
                         info.get('id'))

    # Get path to volume
    volume_path = get_path_to_storage_volume(volume, storage_config)

    # Handle preserve flag
    if config.value_as_boolean(info.get('preserve')):
        # Volume marked to be preserved, not formatting
        return

    # Make filesystem using block library
    LOG.debug("mkfs {} info: {}".format(volume_path, info))
    mkfs.mkfs_from_config(volume_path, info)

    device_type = storage_config.get(volume).get('type')
    LOG.debug('Formated device type: %s', device_type)
    if device_type == 'bcache':
        # other devs have a udev watch on them. Not bcache (LP: #1680597).
        LOG.debug('Detected bcache device format, calling udevadm trigger to '
                  'generate by-uuid symlinks on "%s"', volume_path)
        udevadm_trigger([volume_path])


def mount_data(info, storage_config):
    """Return information necessary for a mount or fstab entry.

    :param info: a 'mount' type from storage config.
    :param storage_config: related storage_config ordered dict by id.

    :return FstabData type."""
    if info.get('type') != "mount":
        raise ValueError("entry is not type 'mount' (%s)" % info)

    spec = info.get('spec')
    fstype = info.get('fstype')
    path = info.get('path')
    freq = str(info.get('freq', 0))
    passno = str(info.get('passno', 0))

    # turn empty options into "defaults", which works in fstab and mount -o.
    if not info.get('options'):
        options = ["defaults"]
    else:
        options = info.get('options').split(",")

    volume_path = None

    if 'device' not in info:
        missing = [m for m in ('spec', 'fstype') if not info.get(m)]
        if not (fstype and spec):
            raise ValueError(
                "mount entry without 'device' missing: %s. (%s)" %
                (missing, info))

    else:
        if info['device'] not in storage_config:
            raise ValueError(
                "mount entry refers to non-existant device %s: (%s)" %
                (info['device'], info))
        if not (fstype and spec):
            format_info = storage_config.get(info['device'])
            if not fstype:
                fstype = format_info['fstype']
            if not spec:
                if format_info.get('volume') not in storage_config:
                    raise ValueError(
                        "format type refers to non-existant id %s: (%s)" %
                        (format_info.get('volume'), format_info))
                volume_path = get_path_to_storage_volume(
                    format_info['volume'],  storage_config)
                if "_netdev" not in options:
                    if iscsi.volpath_is_iscsi(volume_path):
                        options.append("_netdev")

    if fstype in ("fat", "fat12", "fat16", "fat32", "fat64"):
        fstype = "vfat"

    return FstabData(
        spec, path, fstype, ",".join(options), freq, passno, volume_path)


def fstab_line_for_data(fdata):
    """Return a string representing fdata in /etc/fstab format.

    :param fdata: a FstabData type
    :return a newline terminated string for /etc/fstab."""
    path = fdata.path
    if not path:
        if fdata.fstype == "swap":
            path = "none"
        else:
            raise ValueError("empty path in %s." % str(fdata))

    if fdata.spec is None:
        if not fdata.device:
            raise ValueError("FstabData missing both spec and device.")
        uuid = block.get_volume_uuid(fdata.device)
        spec = ("UUID=%s" % uuid) if uuid else fdata.device
    else:
        spec = fdata.spec

    if fdata.options in (None, "", "defaults"):
        if fdata.fstype == "swap":
            options = "sw"
        else:
            options = "defaults"
    else:
        options = fdata.options

    return ' '.join((spec, path, fdata.fstype, options,
                     fdata.freq, fdata.passno)) + "\n"


def mount_fstab_data(fdata, target=None):
    """mount the FstabData fdata with root at target.

    :param fdata: a FstabData type
    :return None."""
    mp = util.target_path(target, fdata.path)
    if fdata.device:
        device = fdata.device
    else:
        if fdata.spec.startswith("/") and not fdata.spec.startswith("/dev/"):
            device = util.target_path(target, fdata.spec)
        else:
            device = fdata.spec

    options = fdata.options if fdata.options else "defaults"

    mcmd = ['mount']
    if fdata.fstype not in ("bind", None, "none"):
        mcmd.extend(['-t', fdata.fstype])
    mcmd.extend(['-o', options, device, mp])

    if fdata.fstype == "bind" or "bind" in options.split(","):
        # for bind mounts, create the 'src' dir (mount -o bind src target)
        util.ensure_dir(device)
    util.ensure_dir(mp)

    try:
        util.subp(mcmd, capture=True)
    except util.ProcessExecutionError as e:
        LOG.exception(e)
        msg = 'Mount failed: %s @ %s with options %s' % (device, mp, options)
        LOG.error(msg)
        raise RuntimeError(msg)


def mount_apply(fdata, target=None, fstab=None):
    if fdata.fstype != "swap":
        mount_fstab_data(fdata, target=target)

    # Add volume to fstab
    if fstab:
        util.write_file(fstab, fstab_line_for_data(fdata), omode="a")
    else:
        LOG.info("fstab not in environment, so not writing")


def mount_handler(info, storage_config):
    """ Handle storage config type: mount

    info = {
        'id': 'rootfs_mount',
        'type': 'mount',
        'path': '/',
        'options': 'defaults,errors=remount-ro',
        'device': 'rootfs',
    }

    Mount specified device under target at 'path' and generate
    fstab entry.
    """
    state = util.load_command_environment()
    mount_apply(mount_data(info, storage_config),
                target=state.get('target'), fstab=state.get('fstab'))


def lvm_volgroup_handler(info, storage_config):
    devices = info.get('devices')
    device_paths = []
    name = info.get('name')
    if not devices:
        raise ValueError("devices for volgroup '%s' must be specified" %
                         info.get('id'))
    if not name:
        raise ValueError("name for volgroups needs to be specified")

    for device_id in devices:
        device = storage_config.get(device_id)
        if not device:
            raise ValueError("device '%s' could not be found in storage config"
                             % device_id)
        device_paths.append(get_path_to_storage_volume(device_id,
                            storage_config))

    # Handle preserve flag
    if config.value_as_boolean(info.get('preserve')):
        # LVM will probably be offline, so start it
        util.subp(["vgchange", "-a", "y"])
        # Verify that volgroup exists and contains all specified devices
        if set(lvm.get_pvols_in_volgroup(name)) != set(device_paths):
            raise ValueError("volgroup '%s' marked to be preserved, but does "
                             "not exist or does not contain the right "
                             "physical volumes" % info.get('id'))
    else:
        # Create vgrcreate command and run
        # capture output to avoid printing it to log
        # Use zero to clear target devices of any metadata
        util.subp(['vgcreate', '--force', '--zero=y', '--yes',
                   name] + device_paths, capture=True)

    # refresh lvmetad
    lvm.lvm_scan()


def lvm_partition_handler(info, storage_config):
    volgroup = storage_config.get(info.get('volgroup')).get('name')
    name = info.get('name')
    if not volgroup:
        raise ValueError("lvm volgroup for lvm partition must be specified")
    if not name:
        raise ValueError("lvm partition name must be specified")
    if info.get('ptable'):
        raise ValueError("Partition tables on top of lvm logical volumes is "
                         "not supported")

    # Handle preserve flag
    if config.value_as_boolean(info.get('preserve')):
        if name not in lvm.get_lvols_in_volgroup(volgroup):
            raise ValueError("lvm partition '%s' marked to be preserved, but "
                             "does not exist or does not mach storage "
                             "configuration" % info.get('id'))
    elif storage_config.get(info.get('volgroup')).get('preserve'):
        raise NotImplementedError(
            "Lvm Partition '%s' is not marked to be preserved, but volgroup "
            "'%s' is. At this time, preserving volgroups but not also the lvm "
            "partitions on the volgroup is not supported, because of the "
            "possibility of damaging lvm  partitions intended to be "
            "preserved." % (info.get('id'), volgroup))
    else:
        # Use 'wipesignatures' (if available) and 'zero' to clear target lv
        # of any fs metadata
        cmd = ["lvcreate", volgroup, "--name", name, "--zero=y"]
        release = util.lsb_release()['codename']
        if release not in ['precise', 'trusty']:
            cmd.extend(["--wipesignatures=y"])

        if info.get('size'):
            cmd.extend(["--size", info.get('size')])
        else:
            cmd.extend(["--extents", "100%FREE"])

        util.subp(cmd)

    # refresh lvmetad
    lvm.lvm_scan()

    make_dname(info.get('id'), storage_config)


def dm_crypt_handler(info, storage_config):
    state = util.load_command_environment()
    volume = info.get('volume')
    key = info.get('key')
    keysize = info.get('keysize')
    cipher = info.get('cipher')
    dm_name = info.get('dm_name')
    if not volume:
        raise ValueError("volume for cryptsetup to operate on must be \
            specified")
    if not key:
        raise ValueError("encryption key must be specified")
    if not dm_name:
        dm_name = info.get('id')

    volume_path = get_path_to_storage_volume(volume, storage_config)

    # TODO: this is insecure, find better way to do this
    tmp_keyfile = tempfile.mkstemp()[1]
    fp = open(tmp_keyfile, "w")
    fp.write(key)
    fp.close()

    cmd = ["cryptsetup"]
    if cipher:
        cmd.extend(["--cipher", cipher])
    if keysize:
        cmd.extend(["--key-size", keysize])
    cmd.extend(["luksFormat", volume_path, tmp_keyfile])

    util.subp(cmd)

    cmd = ["cryptsetup", "open", "--type", "luks", volume_path, dm_name,
           "--key-file", tmp_keyfile]

    util.subp(cmd)

    os.remove(tmp_keyfile)

    # A crypttab will be created in the same directory as the fstab in the
    # configuration. This will then be copied onto the system later
    if state['fstab']:
        crypt_tab_location = os.path.join(os.path.split(state['fstab'])[0],
                                          "crypttab")
        uuid = block.get_volume_uuid(volume_path)
        with open(crypt_tab_location, "a") as fp:
            fp.write("%s UUID=%s none luks\n" % (dm_name, uuid))
    else:
        LOG.info("fstab configuration is not present in environment, so \
            cannot locate an appropriate directory to write crypttab in \
            so not writing crypttab")


def raid_handler(info, storage_config):
    state = util.load_command_environment()
    devices = info.get('devices')
    raidlevel = info.get('raidlevel')
    spare_devices = info.get('spare_devices')
    md_devname = block.dev_path(info.get('name'))
    if not devices:
        raise ValueError("devices for raid must be specified")
    if raidlevel not in ['linear', 'raid0', 0, 'stripe', 'raid1', 1, 'mirror',
                         'raid4', 4, 'raid5', 5, 'raid6', 6, 'raid10', 10]:
        raise ValueError("invalid raidlevel '%s'" % raidlevel)
    if raidlevel in ['linear', 'raid0', 0, 'stripe']:
        if spare_devices:
            raise ValueError("spareunsupported in raidlevel '%s'" % raidlevel)

    LOG.debug('raid: cfg: {}'.format(util.json_dumps(info)))
    device_paths = list(get_path_to_storage_volume(dev, storage_config) for
                        dev in devices)
    LOG.debug('raid: device path mapping: {}'.format(
              zip(devices, device_paths)))

    spare_device_paths = []
    if spare_devices:
        spare_device_paths = list(get_path_to_storage_volume(dev,
                                  storage_config) for dev in spare_devices)
        LOG.debug('raid: spare device path mapping: {}'.format(
                  zip(spare_devices, spare_device_paths)))

    # Handle preserve flag
    if config.value_as_boolean(info.get('preserve')):
        # check if the array is already up, if not try to assemble
        if not mdadm.md_check(md_devname, raidlevel,
                              device_paths, spare_device_paths):
            LOG.info("assembling preserved raid for "
                     "{}".format(md_devname))

            mdadm.mdadm_assemble(md_devname, device_paths, spare_device_paths)

            # try again after attempting to assemble
            if not mdadm.md_check(md_devname, raidlevel,
                                  devices, spare_device_paths):
                raise ValueError("Unable to confirm preserved raid array: "
                                 " {}".format(md_devname))
        # raid is all OK
        return

    mdadm.mdadm_create(md_devname, raidlevel,
                       device_paths, spare_device_paths,
                       info.get('mdname', ''))

    # Make dname rule for this dev
    make_dname(info.get('id'), storage_config)

    # A mdadm.conf will be created in the same directory as the fstab in the
    # configuration. This will then be copied onto the installed system later.
    # The file must also be written onto the running system to enable it to run
    # mdadm --assemble and continue installation
    if state['fstab']:
        mdadm_location = os.path.join(os.path.split(state['fstab'])[0],
                                      "mdadm.conf")
        mdadm_scan_data = mdadm.mdadm_detail_scan()
        with open(mdadm_location, "w") as fp:
            fp.write(mdadm_scan_data)
    else:
        LOG.info("fstab configuration is not present in the environment, so \
            cannot locate an appropriate directory to write mdadm.conf in, \
            so not writing mdadm.conf")

    # If ptable is specified, call disk_handler on this mdadm device to create
    # the table
    if info.get('ptable'):
        disk_handler(info, storage_config)


def bcache_handler(info, storage_config):
    backing_device = get_path_to_storage_volume(info.get('backing_device'),
                                                storage_config)
    cache_device = get_path_to_storage_volume(info.get('cache_device'),
                                              storage_config)
    cache_mode = info.get('cache_mode', None)

    if not backing_device or not cache_device:
        raise ValueError("backing device and cache device for bcache"
                         " must be specified")

    bcache_sysfs = "/sys/fs/bcache"
    udevadm_settle(exists=bcache_sysfs)

    def register_bcache(bcache_device):
        LOG.debug('register_bcache: %s > /sys/fs/bcache/register',
                  bcache_device)
        with open("/sys/fs/bcache/register", "w") as fp:
            fp.write(bcache_device)

    def _validate_bcache(bcache_device, bcache_sys_path):
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
                    _validate_bcache(bcache_device, expected)
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

    if cache_device:
        # /sys/class/block/XXX/YYY/
        cache_device_sysfs = block.sys_block_path(cache_device)

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

    if backing_device:
        backing_device_sysfs = block.sys_block_path(backing_device)
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
        holders = clear_holders.get_holders(backing_device)
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
                LOG.info("Attaching backing device to cacheset: "
                         "{} -> {} cset.uuid: {}".format(backing_device,
                                                         cache_device,
                                                         cset_uuid))
                attach = os.path.join(backing_device_sysfs,
                                      "bcache",
                                      "attach")
                with open(attach, "w") as fp:
                    fp.write(cset_uuid)
            else:
                msg = "Invalid cset_uuid: {}".format(cset_uuid)
                LOG.error(msg)
                raise ValueError(msg)

        if cache_mode:
            LOG.info("Setting cache_mode on {} to {}".format(bcache_dev,
                                                             cache_mode))
            cache_mode_file = \
                '/sys/block/{}/bcache/cache_mode'.format(bcache_dev)
            with open(cache_mode_file, "w") as fp:
                fp.write(cache_mode)
    else:
        # no backing device
        if cache_mode:
            raise ValueError("cache mode specified which can only be set per \
                              backing devices, but none was specified")

    if info.get('name'):
        # Make dname rule for this dev
        make_dname(info.get('id'), storage_config)

    if info.get('ptable'):
        raise ValueError("Partition tables on top of lvm logical volumes is \
                         not supported")
    LOG.debug('Finished bcache creation for backing {} or caching {}'
              .format(backing_device, cache_device))


def zpool_handler(info, storage_config):
    """
    Create a zpool based in storage_configuration
    """
    zfs.zfs_assert_supported()

    state = util.load_command_environment()

    # extract /dev/disk/by-id paths for each volume used
    vdevs = [get_path_to_storage_volume(v, storage_config)
             for v in info.get('vdevs', [])]
    poolname = info.get('pool')
    mountpoint = info.get('mountpoint')
    altroot = state['target']

    if not vdevs or not poolname:
        raise ValueError("pool and vdevs for zpool must be specified")

    # map storage volume to by-id path for persistent path
    vdevs_byid = []
    for vdev in vdevs:
        byid = block.disk_to_byid_path(vdev)
        if not byid:
            msg = ('Cannot find by-id path to zpool device "%s". '
                   'The zpool may fail to import of path names change.' % vdev)
            LOG.warning(msg)
            byid = vdev

        vdevs_byid.append(byid)

    LOG.info('Creating zpool %s with vdevs %s', poolname, vdevs_byid)
    zfs.zpool_create(poolname, vdevs_byid,
                     mountpoint=mountpoint, altroot=altroot)


def zfs_handler(info, storage_config):
    """
    Create a zfs filesystem
    """
    zfs.zfs_assert_supported()

    state = util.load_command_environment()
    poolname = get_poolname(info, storage_config)
    volume = info.get('volume')
    properties = info.get('properties', {})

    LOG.info('Creating zfs dataset %s/%s with properties %s',
             poolname, volume, properties)
    zfs.zfs_create(poolname, volume, zfs_properties=properties)

    mountpoint = properties.get('mountpoint')
    if mountpoint:
        if state['fstab']:
            fstab_entry = (
                "# Use `zfs list` for current zfs mount info\n" +
                "# %s %s defaults 0 0\n" % (poolname, mountpoint))
            util.write_file(state['fstab'], fstab_entry, omode='a')


def extract_storage_ordered_dict(config):
    storage_config = config.get('storage', {})
    if not storage_config:
        raise ValueError("no 'storage' entry in config")
    scfg = storage_config.get('config')
    if not scfg:
        raise ValueError("invalid storage config data")

    # Since storage config will often have to be searched for a value by its
    # id, and this can become very inefficient as storage_config grows, a dict
    # will be generated with the id of each component of the storage_config as
    # its index and the component of storage_config as its value
    return OrderedDict((d["id"], d) for (i, d) in enumerate(scfg))


def zfsroot_update_storage_config(storage_config):
    """Return an OrderedDict that has 'zfsroot' format expanded into
       zpool and zfs commands to enable ZFS on rootfs.
    """

    zfsroots = [d for i, d in storage_config.items()
                if d.get('fstype') == "zfsroot"]

    if len(zfsroots) == 0:
        return storage_config

    if len(zfsroots) > 1:
        raise ValueError(
            "zfsroot found in two entries in storage config: %s" % zfsroots)

    root = zfsroots[0]
    vol = root.get('volume')
    if not vol:
        raise ValueError("zfsroot entry did not have 'volume'.")

    if vol not in storage_config:
        raise ValueError(
            "zfs volume '%s' not referenced in storage config" % vol)

    mounts = [d for i, d in storage_config.items()
              if d.get('type') == 'mount' and d.get('path') == "/"]
    if len(mounts) != 1:
        raise ValueError("Multiple 'mount' entries point to '/'")

    mount = mounts[0]
    if mount.get('device') != root['id']:
        raise ValueError(
            "zfsroot Mountpoint entry for / has device=%s, expected '%s'" %
            (mount.get("device"), root['id']))

    # validate that the boot disk is GPT partitioned
    bootdevs = [d for i, d in storage_config.items() if d.get('grub_device')]
    bootdev = bootdevs[0]
    if bootdev.get('ptable') != 'gpt':
        raise ValueError(
            'zfsroot requires bootdisk with GPT partition table'
            ' found "%s" on disk id="%s"' %
            (bootdev.get('ptable'), bootdev.get('id')))

    LOG.info('Enabling experimental zfsroot!')

    ret = OrderedDict()
    for eid, info in storage_config.items():
        if info.get('id') == mount['id']:
            continue

        if info.get('fstype') != "zfsroot":
            ret[eid] = info
            continue

        vdevs = [storage_config[info['volume']]['id']]
        baseid = info['id']
        pool = {
            'type': 'zpool',
            'id': baseid + "_zfsroot_pool",
            'pool': 'rpool',
            'vdevs': vdevs,
            'mountpoint': '/'
        }
        container = {
            'type': 'zfs',
            'id': baseid + "_zfsroot_container",
            'pool': pool['id'],
            'volume': '/ROOT',
            'properties': {
                'canmount': 'off',
                'mountpoint': 'none',
            }
        }
        rootfs = {
            'type': 'zfs',
            'id': baseid + "_zfsroot_fs",
            'pool': pool['id'],
            'volume': '/ROOT/zfsroot',
            'properties': {
                'canmount': 'noauto',
                'mountpoint': '/',
            }
        }

        for d in (pool, container, rootfs):
            if d['id'] in ret:
                raise RuntimeError(
                    "Collided on id '%s' in storage config" % d['id'])
            ret[d['id']] = d

    return ret


def meta_custom(args):
    """Does custom partitioning based on the layout provided in the config
    file. Section with the name storage contains information on which
    partitions on which disks to create. It also contains information about
    overlays (raid, lvm, bcache) which need to be setup.
    """

    command_handlers = {
        'disk': disk_handler,
        'partition': partition_handler,
        'format': format_handler,
        'mount': mount_handler,
        'lvm_volgroup': lvm_volgroup_handler,
        'lvm_partition': lvm_partition_handler,
        'dm_crypt': dm_crypt_handler,
        'raid': raid_handler,
        'bcache': bcache_handler,
        'zfs': zfs_handler,
        'zpool': zpool_handler,
    }

    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    storage_config_dict = extract_storage_ordered_dict(cfg)

    storage_config_dict = zfsroot_update_storage_config(storage_config_dict)

    # set up reportstack
    stack_prefix = state.get('report_stack_prefix', '')

    # shut down any already existing storage layers above any disks used in
    # config that have 'wipe' set
    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level='INFO',
            description="removing previous storage devices"):
        clear_holders.start_clear_holders_deps()
        disk_paths = [get_path_to_storage_volume(k, storage_config_dict)
                      for (k, v) in storage_config_dict.items()
                      if v.get('type') == 'disk' and
                      config.value_as_boolean(v.get('wipe')) and
                      not config.value_as_boolean(v.get('preserve'))]
        clear_holders.clear_holders(disk_paths)
        # if anything was not properly shut down, stop installation
        clear_holders.assert_clear(disk_paths)

    for item_id, command in storage_config_dict.items():
        handler = command_handlers.get(command['type'])
        if not handler:
            raise ValueError("unknown command type '%s'" % command['type'])
        with events.ReportEventStack(
                name=stack_prefix, reporting_enabled=True, level="INFO",
                description="configuring %s: %s" % (command['type'],
                                                    command['id'])):
            try:
                handler(command, storage_config_dict)
            except Exception as error:
                LOG.error("An error occured handling '%s': %s - %s" %
                          (item_id, type(error).__name__, error))
                raise

    if args.umount:
        util.do_umount(state['target'], recursive=True)
    return 0


def meta_simple(args):
    """Creates a root partition. If args.mode == SIMPLE_BOOT, it will also
    create a separate /boot partition.
    """
    state = util.load_command_environment()

    cfg = config.load_command_config(args, state)
    devpath = None
    if cfg.get("storage") is not None:
        for i in cfg["storage"]["config"]:
            serial = i.get("serial")
            if serial is None:
                continue
            grub = i.get("grub_device")
            diskPath = block.lookup_disk(serial)
            if grub is True:
                devpath = diskPath
            if config.value_as_boolean(i.get('wipe')):
                block.wipe_volume(diskPath, mode=i.get('wipe'))

    if args.target is not None:
        state['target'] = args.target

    if state['target'] is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    devices = args.devices
    if devices is None:
        devices = cfg.get('block-meta', {}).get('devices', [])

    bootpt = get_bootpt_cfg(
        cfg.get('block-meta', {}).get('boot-partition', {}),
        enabled=args.mode == SIMPLE_BOOT, fstype=args.boot_fstype,
        root_fstype=args.fstype)

    ptfmt = get_partition_format_type(cfg.get('block-meta', {}))

    # Remove duplicates but maintain ordering.
    devices = list(OrderedDict.fromkeys(devices))

    # Multipath devices might be automatically assembled if multipath-tools
    # package is available in the installation environment. We need to stop
    # all multipath devices to exclusively use one of paths as a target disk.
    block.stop_all_unused_multipath_devices()

    if len(devices) == 0 and devpath is None:
        devices = block.get_installable_blockdevs()
        LOG.warn("'%s' mode, no devices given. unused list: %s",
                 args.mode, devices)
        # Check if the list of installable block devices is still empty after
        # checking for block devices and filtering out the removable ones.  In
        # this case we may have a system which has its harddrives reported by
        # lsblk incorrectly. In this case we search for installable
        # blockdevices that are removable as a last resort before raising an
        # exception.
        if len(devices) == 0:
            devices = block.get_installable_blockdevs(include_removable=True)
            if len(devices) == 0:
                # Fail gracefully if no devices are found, still.
                raise Exception("No valid target devices found that curtin "
                                "can install on.")
            else:
                LOG.warn("No non-removable, installable devices found. List "
                         "populated with removable devices allowed: %s",
                         devices)
    elif len(devices) == 0 and devpath:
        devices = [devpath]

    if len(devices) > 1:
        if args.devices is not None:
            LOG.warn("'%s' mode but multiple devices given. "
                     "using first found", args.mode)
        available = [f for f in devices
                     if block.is_valid_device(f)]
        target = sorted(available)[0]
        LOG.warn("mode is '%s'. multiple devices given. using '%s' "
                 "(first available)", args.mode, target)
    else:
        target = devices[0]

    if not block.is_valid_device(target):
        raise Exception("target device '%s' is not a valid device" % target)

    (devname, devnode) = block.get_dev_name_entry(target)

    LOG.info("installing in '%s' mode to '%s'", args.mode, devname)

    sources = cfg.get('sources', {})
    dd_images = util.get_dd_images(sources)

    if len(dd_images):
        # we have at least one dd-able image
        # we will only take the first one
        rootdev = write_image_to_disk(dd_images[0], devname)
        util.subp(['mount', rootdev, state['target']])
        return 0

    # helper partition will forcibly set up partition there
    ptcmd = ['partition', '--format=' + ptfmt]
    if bootpt['enabled']:
        ptcmd.append('--boot')
    ptcmd.append(devnode)

    if bootpt['enabled'] and ptfmt in ("uefi", "prep"):
        raise ValueError("format=%s with boot partition not supported" % ptfmt)

    bootdev_ptnum = None
    rootdev_ptnum = None
    bootdev = None
    if bootpt['enabled']:
        bootdev_ptnum = 1
        rootdev_ptnum = 2
    else:
        if ptfmt == "prep":
            rootdev_ptnum = 2
        else:
            rootdev_ptnum = 1

    logtime("creating partition with: %s" % ' '.join(ptcmd),
            util.subp, ptcmd)

    ptpre = ""
    if not os.path.exists("%s%s" % (devnode, rootdev_ptnum)):
        # perhaps the device is /dev/<blockname>p<ptnum>
        if os.path.exists("%sp%s" % (devnode, rootdev_ptnum)):
            ptpre = "p"
        else:
            LOG.warn("root device %s%s did not exist, expecting failure",
                     devnode, rootdev_ptnum)

    if bootdev_ptnum:
        bootdev = "%s%s%s" % (devnode, ptpre, bootdev_ptnum)

    if ptfmt == "uefi":
        # assumed / required from the partitioner pt_uefi
        uefi_ptnum = "15"
        uefi_label = "uefi-boot"
        uefi_dev = "%s%s%s" % (devnode, ptpre, uefi_ptnum)

    rootdev = "%s%s%s" % (devnode, ptpre, rootdev_ptnum)

    LOG.debug("rootdev=%s bootdev=%s fmt=%s bootpt=%s",
              rootdev, bootdev, ptfmt, bootpt)

    # mkfs for root partition first and mount
    cmd = ['mkfs.%s' % args.fstype, '-q', '-L', 'cloudimg-rootfs', rootdev]
    logtime(' '.join(cmd), util.subp, cmd)
    util.subp(['mount', rootdev, state['target']])

    if bootpt['enabled']:
        # create 'boot' directory in state['target']
        boot_dir = os.path.join(state['target'], 'boot')
        util.subp(['mkdir', boot_dir])
        # mkfs for boot partition and mount
        cmd = ['mkfs.%s' % bootpt['fstype'],
               '-q', '-L', bootpt['label'], bootdev]
        logtime(' '.join(cmd), util.subp, cmd)
        util.subp(['mount', bootdev, boot_dir])

    if ptfmt == "uefi":
        uefi_dir = os.path.join(state['target'], 'boot', 'efi')
        util.ensure_dir(uefi_dir)
        util.subp(['mount', uefi_dev, uefi_dir])

    if state['fstab']:
        with open(state['fstab'], "w") as fp:
            if bootpt['enabled']:
                fp.write("LABEL=%s /boot %s defaults 0 0\n" %
                         (bootpt['label'], bootpt['fstype']))

            if ptfmt == "uefi":
                # label created in helpers/partition for uefi
                fp.write("LABEL=%s /boot/efi vfat defaults 0 0\n" %
                         uefi_label)

            fp.write("LABEL=%s / %s defaults 0 0\n" %
                     ('cloudimg-rootfs', args.fstype))
    else:
        LOG.info("fstab not in environment, so not writing")

    if args.umount:
        util.do_umount(state['target'], recursive=True)

    return 0


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_meta)

# vi: ts=4 expandtab syntax=python
