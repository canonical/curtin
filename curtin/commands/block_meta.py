# This file is part of curtin. See LICENSE file for copyright and license info.

from collections import OrderedDict, namedtuple
from curtin import (block, config, paths, util)
from curtin.block import schemas
from curtin.block import (bcache, clear_holders, dasd, iscsi, lvm, mdadm, mkfs,
                          multipath, zfs)
from curtin import distro
from curtin.log import LOG, logged_time
from curtin.reporter import events
from curtin.storage_config import (extract_storage_ordered_dict,
                                   ptable_uuid_to_flag_entry)


from . import populate_one_subcmd
from curtin.udev import (compose_udev_equality, udevadm_settle,
                         udevadm_trigger, udevadm_info)

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
PTABLE_UNSUPPORTED = schemas._ptable_unsupported
PTABLES_SUPPORTED = schemas._ptables
PTABLES_VALID = schemas._ptables_valid

SGDISK_FLAGS = {
    "boot": 'ef00',
    "lvm": '8e00',
    "raid": 'fd00',
    "bios_grub": 'ef02',
    "prep": '4100',
    "swap": '8200',
    "home": '8302',
    "linux": '8300'
}

MSDOS_FLAGS = {
    'boot': 'boot',
    'extended': 'extended',
    'logical': 'logical',
}

DNAME_BYID_KEYS = ['DM_UUID', 'ID_WWN_WITH_EXTENSION', 'ID_WWN', 'ID_SERIAL',
                   'ID_SERIAL_SHORT']
CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'default': None, }),
     ('--fstype', {'help': 'root partition filesystem type',
                   'choices': ['ext4', 'ext3'], 'default': 'ext4'}),
     ('--force-mode', {'help': 'force mode, disable mode detection',
                       'action': 'store_true', 'default': False}),
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
    state = util.load_command_environment(strict=True)
    cfg = config.load_command_config(args, state)
    dd_images = util.get_dd_images(cfg.get('sources', {}))

    # run clear holders on potential devices
    devices = args.devices
    if devices is None:
        devices = []
        if 'storage' in cfg:
            devices = get_device_paths_from_storage_config(
                extract_storage_ordered_dict(cfg))
            LOG.debug('block-meta: extracted devices to clear: %s', devices)
        if len(devices) == 0:
            devices = cfg.get('block-meta', {}).get('devices', [])
        LOG.debug('Declared block devices: %s', devices)
        args.devices = devices

    LOG.debug('clearing devices=%s', devices)
    meta_clear(devices, state.get('report_stack_prefix', ''))

    # dd-images requires use of meta_simple
    if len(dd_images) > 0 and args.force_mode is False:
        LOG.info('blockmeta: detected dd-images, using mode=simple')
        return meta_simple(args)

    if cfg.get("storage") and args.force_mode is False:
        LOG.info('blockmeta: detected storage config, using mode=custom')
        return meta_custom(args)

    LOG.info('blockmeta: mode=%s force=%s', args.mode, args.force_mode)
    if args.mode == CUSTOM:
        return meta_custom(args)
    elif args.mode in (SIMPLE, SIMPLE_BOOT):
        return meta_simple(args)
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
    # Images from MAAS have well-known/required paths present
    # on the rootfs partition.  Use these values to select the
    # root (target) partition to complete installation.
    #
    # /curtin -> Most Ubuntu Images
    # /system-data/var/lib/snapd -> UbuntuCore 16 or 18
    # /snaps -> UbuntuCore20
    paths = ["curtin", "system-data/var/lib/snapd", "snaps"]
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


def make_dname_byid(path, error_msg=None, info=None):
    """ Returns a list of udev equalities for a given disk path

    :param path: string of a kernel device path to a block device
    :param error_msg: more information about path for log/errors
    :param info: dict of udevadm info key, value pairs of device specified by
                 path.
    :returns: list of udev equalities (lists)
    :raises: ValueError if path is not a disk.
    :raises: RuntimeError if there is no serial or wwn.
    """
    error_msg = str(path) + ("" if not error_msg else " [%s]" % error_msg)
    if info is None:
        info = udevadm_info(path=path)
    devtype = info.get('DEVTYPE')
    if devtype != "disk":
        raise ValueError(
            "Disk tag udev rules are only for disks, %s has devtype=%s" %
            (error_msg, devtype))

    present = [k for k in DNAME_BYID_KEYS if info.get(k)]
    if not present:
        LOG.warning(
            "Cannot create disk tag udev rule for %s, "
            "missing 'serial' or 'wwn' value", error_msg)
        return []

    return [[compose_udev_equality('ENV{%s}' % k, info[k]) for k in present]]


def make_dname(volume, storage_config):
    state = util.load_command_environment(strict=True)
    rules_dir = os.path.join(state['scratch'], "rules.d")
    vol = storage_config.get(volume)
    path = get_path_to_storage_volume(volume, storage_config)
    ptuuid = None
    byid = None
    dname = vol.get('name')
    if vol.get('type') in ["partition", "disk"]:
        (out, _err) = util.subp(["blkid", "-o", "export", path], capture=True,
                                rcs=[0, 2], retries=[1, 1, 1])
        for line in out.splitlines():
            if "PTUUID" in line or "PARTUUID" in line:
                ptuuid = line.split('=')[-1]
                break
        if vol.get('type') == 'disk':
            byid = make_dname_byid(path, error_msg="id=%s" % vol.get('id'))
    # we may not always be able to find a uniq identifier on devices with names
    if (not ptuuid and not byid) and vol.get('type') in ["disk", "partition"]:
        LOG.warning("Can't find a uuid for volume: %s. Skipping dname.",
                    volume)
        return

    matches = []
    base_rule = [
        compose_udev_equality("SUBSYSTEM", "block"),
        compose_udev_equality("ACTION", "add|change"),
        ]
    if vol.get('type') == "disk":
        if ptuuid:
            matches += [[compose_udev_equality('ENV{DEVTYPE}', "disk"),
                        compose_udev_equality('ENV{ID_PART_TABLE_UUID}',
                                              ptuuid)]]
        for rule in byid:
            matches += [
                [compose_udev_equality('ENV{DEVTYPE}', "disk")] + rule]
    elif vol.get('type') == "partition":
        # if partition has its own name, bind that to the existing PTUUID
        if dname:
            matches += [[compose_udev_equality('ENV{DEVTYPE}', "partition"),
                        compose_udev_equality('ENV{ID_PART_ENTRY_UUID}',
                                              ptuuid)]]
        else:
            # disks generate dname-part%n rules automatically
            LOG.debug('No partition-specific dname')
            return
    elif vol.get('type') == "raid":
        md_data = mdadm.mdadm_query_detail(path)
        md_uuid = md_data.get('MD_UUID')
        matches += [[compose_udev_equality("ENV{MD_UUID}", md_uuid)]]
    elif vol.get('type') == "bcache":
        # bind dname to bcache backing device's dev.uuid as the bcache minor
        # device numbers are not stable across reboots.
        backing_dev = get_path_to_storage_volume(vol.get('backing_device'),
                                                 storage_config)
        bcache_super = bcache.superblock_asdict(device=backing_dev)
        if bcache_super and bcache_super['sb.version'].startswith('1'):
            bdev_uuid = bcache_super['dev.uuid']
        matches += [[compose_udev_equality("ENV{CACHED_UUID}", bdev_uuid)]]
        bcache.write_label(sanitize_dname(dname), backing_dev)
    elif vol.get('type') == "lvm_partition":
        info = udevadm_info(path=path)
        dname = info['DM_NAME']
        matches += [[compose_udev_equality("ENV{DM_NAME}", dname)]]
    else:
        raise ValueError('cannot make dname for device with type: {}'
                         .format(vol.get('type')))

    # note: this sanitization is done here instead of for all name attributes
    #       at the beginning of storage configuration, as some devices, such as
    #       lvm devices may use the name attribute and may permit special chars
    sanitized = sanitize_dname(dname)
    if sanitized != dname:
        LOG.warning("dname modified to remove invalid chars. old:"
                    "'%s' new: '%s'", dname, sanitized)
    content = ['# Written by curtin']
    for match in matches:
        rule = (base_rule + match +
                ["SYMLINK+=\"disk/by-dname/%s\"\n" % sanitized])
        LOG.debug("Creating dname udev rule '%s'", str(rule))
        content.append(', '.join(rule))

    if vol.get('type') == 'disk':
        for brule in byid:
            part_rule = None
            for env_rule in brule:
                # multipath partitions prefix partN- to DM_UUID for fun!
                # and partitions are "disks" yay \o/ /sarcasm
                if 'ENV{DM_UUID}=="mpath' not in env_rule:
                    continue
                dm_uuid = env_rule.split("==")[1].replace('"', '')
                part_dm_uuid = 'part*-' + dm_uuid
                part_rule = (
                    [compose_udev_equality('ENV{DEVTYPE}', 'disk')] +
                    [compose_udev_equality('ENV{DM_UUID}', part_dm_uuid)])

            # non-multipath partition rule
            if not part_rule:
                part_rule = (
                    [compose_udev_equality('ENV{DEVTYPE}', 'partition')] +
                    brule)
            rule = (base_rule + part_rule +
                    ['SYMLINK+="disk/by-dname/%s-part%%n"\n' % sanitized])
            LOG.debug("Creating dname udev rule '%s'", str(rule))
            content.append(', '.join(rule))

    util.ensure_dir(rules_dir)
    rule_file = os.path.join(rules_dir, '{}.rules'.format(sanitized))
    util.write_file(rule_file, '\n'.join(content))


def get_poolname(info, storage_config):
    """ Resolve pool name from zfs info """

    LOG.debug('get_poolname for volume %s', info)
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

    devsync_vol = None
    vol = storage_config.get(volume)
    LOG.debug('get_path_to_storage_volume for volume %s(%s)', volume, vol)
    if not vol:
        raise ValueError("volume with id '%s' not found" % volume)

    # Find path to block device
    if vol.get('type') == "partition":
        partnumber = determine_partition_number(vol.get('id'), storage_config)
        disk_block_path = get_path_to_storage_volume(vol.get('device'),
                                                     storage_config)
        if disk_block_path.startswith('/dev/mapper/mpath'):
            volume_path = disk_block_path + '-part%s' % partnumber
        else:
            disk_kname = block.path_to_kname(disk_block_path)
            partition_kname = block.partition_kname(disk_kname, partnumber)
            volume_path = block.kname_to_path(partition_kname)
        devsync_vol = os.path.join(disk_block_path)

    elif vol.get('type') == "dasd":
        dasd_device = dasd.DasdDevice(vol.get('device_id'))
        volume_path = dasd_device.devname

    elif vol.get('type') == "disk":
        # Get path to block device for disk. Device_id param should refer
        # to id of device in storage config
        volume_path = None
        for disk_key in ['wwn', 'serial', 'device_id', 'path']:
            vol_value = vol.get(disk_key)
            try:
                if not vol_value:
                    continue
                if disk_key in ['wwn', 'serial']:
                    volume_path = block.lookup_disk(vol_value)
                elif disk_key == 'path':
                    if vol_value.startswith('iscsi:'):
                        i = iscsi.ensure_disk_connected(vol_value)
                        volume_path = os.path.realpath(i.devdisk_path)
                    else:
                        # resolve any symlinks to the dev_kname so
                        # sys/class/block access is valid.  ie, there are no
                        # udev generated values in sysfs
                        volume_path = os.path.realpath(vol_value)
                    # convert /dev/sdX to /dev/mapper/mpathX value
                    if multipath.is_mpath_member(volume_path):
                        volume_path = '/dev/mapper/' + (
                            multipath.get_mpath_id_from_device(volume_path))
                elif disk_key == 'device_id':
                    dasd_device = dasd.DasdDevice(vol_value)
                    volume_path = dasd_device.devname
            except ValueError:
                continue
            # verify path exists otherwise try the next key
            if os.path.exists(volume_path):
                break
            else:
                volume_path = None

        if volume_path is None:
            raise ValueError("Failed to find storage volume id='%s' config: %s"
                             % (vol['id'], vol))

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
        LOG.debug('got bcache volume path %s', volume_path)

    else:
        raise NotImplementedError("cannot determine the path to storage \
            volume '%s' with type '%s'" % (volume, vol.get('type')))

    # sync devices
    if not devsync_vol:
        devsync_vol = volume_path
    devsync(devsync_vol)

    LOG.debug('return volume path %s', volume_path)
    return volume_path


def dasd_handler(info, storage_config):
    """ Prepare the specified dasd device per configuration

    params: info: dictionary of configuration, required keys are:
        type, id, device_id
    params: storage_config:  ordered dictionary of entire storage config

    example:
    {
     'type': 'dasd',
     'id': 'dasd_142f',
     'device_id': '0.0.142f',
     'blocksize': 4096,
     'label': 'cloudimg-rootfs',
     'mode': 'quick',
     'disk_layout': 'cdl',
    }
    """
    device_id = info.get('device_id')
    blocksize = info.get('blocksize')
    disk_layout = info.get('disk_layout')
    label = info.get('label')
    mode = info.get('mode')
    force_format = config.value_as_boolean(info.get('wipe'))

    dasd_device = dasd.DasdDevice(device_id)
    if (force_format or dasd_device.needs_formatting(blocksize,
                                                     disk_layout, label)):
        if config.value_as_boolean(info.get('preserve')):
            raise ValueError(
                "dasd '%s' does not match configured properties and"
                "preserve is set to true.  The dasd needs formatting"
                "with the specified parameters to continue." % info.get('id'))

        LOG.debug('Formatting dasd id=%s device_id=%s devname=%s',
                  info.get('id'), device_id, dasd_device.devname)
        dasd_device.format(blksize=blocksize, layout=disk_layout,
                           set_label=label, mode=mode)

        # check post-format to ensure values match
        if dasd_device.needs_formatting(blocksize, disk_layout, label):
            raise RuntimeError(
                "Dasd %s failed to format" % dasd_device.devname)


def disk_handler(info, storage_config):
    _dos_names = ['dos', 'msdos']
    ptable = info.get('ptable')
    if ptable and ptable not in PTABLES_VALID:
        raise ValueError(
            'Invalid partition table type: %s in %s' % (ptable, info))

    disk = get_path_to_storage_volume(info.get('id'), storage_config)
    if config.value_as_boolean(info.get('preserve')):
        # Handle preserve flag, verifying if ptable specified in config
        if ptable and ptable != PTABLE_UNSUPPORTED:
            current_ptable = block.get_part_table_type(disk)
            LOG.debug('disk: current ptable type: %s', current_ptable)
            if current_ptable not in PTABLES_SUPPORTED:
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
            elif ptable == "vtoc":
                # ignore dasd partition tables
                pass
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


def find_extended_partition(part_device, storage_config):
    """ Scan storage config for a partition entry from the same device
        with the 'extended' flag set.

        :param: part_device: string specifiying the device id to match
        :param: storage_config: Ordered dict of storage configation
        :returns: string: item_id if found or None
    """
    for item_id, item in storage_config.items():
        if item.get('type') == "partition" and \
           item.get('device') == part_device and \
           item.get('flag') == "extended":
            return item_id


def calc_dm_partition_info(partition):
    # dm- partitions are not in the same dir as disk dm device,
    # dmsetup table <dm_name>
    # handle linear types only
    #    mpatha-part1: 0 6291456 linear 253:0, 2048
    #    <dm_name>: <log. start sec> <num sec> <type> <dest dev>  <start sec>
    #
    # Mapping this:
    #   previous_size_sectors = <num_sec> | /sys/class/block/dm-1/size
    #   previous_start_sectors = <start_sec> |  No 'start' sysfs file
    pp_size_sec = pp_start_sec = None
    mpath_id = multipath.get_mpath_id_from_device(block.dev_path(partition))
    if mpath_id is None:
        raise RuntimeError('Failed to find mpath_id for partition')
    table_cmd = ['dmsetup', 'table', '--target', 'linear', mpath_id]
    out, _err = util.subp(table_cmd, capture=True)
    if out:
        (_logical_start, previous_size_sectors, _table_type,
         _destination, previous_start_sectors) = out.split()
        pp_size_sec = int(previous_size_sectors)
        pp_start_sec = int(previous_start_sectors)

    return (pp_start_sec, pp_size_sec)


def calc_partition_info(disk, partition, logical_block_size_bytes):
    if partition.startswith('dm-'):
        pp = partition
        pp_start_sec, pp_size_sec = calc_dm_partition_info(partition)
    else:
        pp = os.path.join(disk, partition)
        # XXX: sys/block/X/{size,start} is *ALWAYS* in 512b value
        pp_size = int(
            util.load_file(os.path.join(pp, "size")))
        pp_size_sec = int(pp_size * 512 / logical_block_size_bytes)
        pp_start = int(util.load_file(os.path.join(pp, "start")))
        pp_start_sec = int(pp_start * 512 / logical_block_size_bytes)

    LOG.debug("previous partition: %s size_sectors=%s start_sectors=%s",
              pp, pp_size_sec, pp_start_sec)
    if not all([pp_size_sec, pp_start_sec]):
        raise RuntimeError(
            'Failed to determine previous partition %s info', partition)

    return (pp_start_sec, pp_size_sec)


def verify_exists(devpath):
    LOG.debug('Verifying %s exists', devpath)
    if not os.path.exists(devpath):
        raise RuntimeError("Device %s does not exist" % devpath)


def verify_size(devpath, expected_size_bytes, sfdisk_info=None):
    if not sfdisk_info:
        sfdisk_info = block.sfdisk_info(devpath)

    part_info = block.get_partition_sfdisk_info(devpath,
                                                sfdisk_info=sfdisk_info)
    (found_type, _code) = ptable_uuid_to_flag_entry(part_info.get('type'))
    if found_type == 'extended':
        found_size_bytes = int(part_info['size']) * 512
    else:
        found_size_bytes = block.read_sys_block_size_bytes(devpath)
    msg = (
        'Verifying %s size, expecting %s bytes, found %s bytes' % (
         devpath, expected_size_bytes, found_size_bytes))
    LOG.debug(msg)
    if expected_size_bytes != found_size_bytes:
        raise RuntimeError(msg)


def verify_ptable_flag(devpath, expected_flag, sfdisk_info=None):
    if (expected_flag not in SGDISK_FLAGS.keys()) and (expected_flag not in
                                                       MSDOS_FLAGS.keys()):
        raise RuntimeError(
            'Cannot verify unknown partition flag: %s' % expected_flag)

    if not sfdisk_info:
        sfdisk_info = block.sfdisk_info(devpath)

    entry = block.get_partition_sfdisk_info(devpath, sfdisk_info=sfdisk_info)
    LOG.debug("Device %s ptable entry: %s", devpath, util.json_dumps(entry))
    found_flag = None
    if (sfdisk_info['label'] in ('dos', 'msdos')):
        if expected_flag == 'boot':
            found_flag = 'boot' if entry.get('bootable') is True else None
        elif expected_flag == 'extended':
            (found_flag, _code) = ptable_uuid_to_flag_entry(entry['type'])
        elif expected_flag == 'logical':
            (_parent, partnumber) = block.get_blockdev_for_partition(devpath)
            found_flag = 'logical' if int(partnumber) > 4 else None
    else:
        (found_flag, _code) = ptable_uuid_to_flag_entry(entry['type'])
    msg = (
        'Verifying %s partition flag, expecting %s, found %s' % (
         devpath, expected_flag, found_flag))
    LOG.debug(msg)
    if expected_flag != found_flag:
        raise RuntimeError(msg)


def partition_verify(devpath, info):
    verify_exists(devpath)
    sfdisk_info = block.sfdisk_info(devpath)
    if not sfdisk_info:
        raise RuntimeError('Failed to extract sfdisk info from %s' % devpath)
    verify_size(devpath, int(util.human2bytes(info['size'])),
                sfdisk_info=sfdisk_info)
    expected_flag = info.get('flag')
    if expected_flag:
        verify_ptable_flag(devpath, info['flag'], sfdisk_info=sfdisk_info)


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
        (logical_block_size_bytes, _) = block.get_blockdev_sector_size(disk)
        LOG.debug("%s logical_block_size_bytes: %s",
                  disk_kname, logical_block_size_bytes)
    except OSError as e:
        LOG.warning("Couldn't read block size, using default size 512: %s", e)
        logical_block_size_bytes = 512

    if partnumber > 1:
        pnum = None
        if partnumber == 5 and disk_ptable == "msdos":
            extended_part_id = find_extended_partition(device, storage_config)
            if not extended_part_id:
                msg = ("Logical partition id=%s requires an extended partition"
                       " and no extended partition '(type: partition, flag: "
                       "extended)' was found in the storage config.")
                LOG.error(msg, info['id'])
                raise RuntimeError(msg, info['id'])
            pnum = determine_partition_number(extended_part_id, storage_config)
        else:
            pnum = find_previous_partition(device, info['id'], storage_config)

        # In case we fail to find previous partition let's error out now
        if pnum is None:
            raise RuntimeError(
                'Cannot find previous partition on disk %s' % disk)

        LOG.debug("previous partition number for '%s' found to be '%s'",
                  info.get('id'), pnum)
        partition_kname = block.partition_kname(disk_kname, pnum)
        LOG.debug('partition_kname=%s', partition_kname)
        (previous_start_sectors, previous_size_sectors) = (
            calc_partition_info(disk_sysfs_path, partition_kname,
                                logical_block_size_bytes))

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
    create_partition = True
    if config.value_as_boolean(info.get('preserve')):
        part_path = block.dev_path(
            block.partition_kname(disk_kname, partnumber))
        partition_verify(part_path, info)
        LOG.debug('Partition %s already present, skipping create', part_path)
        create_partition = False

    if create_partition:
        # Set flag
        # 'sgdisk --list-types'
        LOG.info("adding partition '%s' to disk '%s' (ptable: '%s')",
                 info.get('id'), device, disk_ptable)
        LOG.debug("partnum: %s offset_sectors: %s length_sectors: %s",
                  partnumber, offset_sectors, length_sectors)

        # Pre-Wipe the partition if told to do so, do not wipe dos extended
        # partitions as this may damage the extended partition table
        if config.value_as_boolean(info.get('wipe')):
            LOG.info("Preparing partition location on disk %s", disk)
            if info.get('flag') == "extended":
                LOG.warn("extended partitions do not need wiping, "
                         "so skipping: '%s'" % info.get('id'))
            else:
                # wipe the start of the new partition first by zeroing 1M at
                # the length of the previous partition
                wipe_offset = int(offset_sectors * logical_block_size_bytes)
                LOG.debug('Wiping 1M on %s at offset %s', disk, wipe_offset)
                # We don't require exclusive access as we're wiping data at an
                # offset and the current holder maybe part of the current
                # storage configuration.
                block.zero_file_at_offsets(disk, [wipe_offset],
                                           exclusive=False)

        if disk_ptable == "msdos":
            if flag and flag == 'prep':
                raise ValueError(
                    'PReP partitions require a GPT partition table')

            if flag in ["extended", "logical", "primary"]:
                partition_type = flag
            else:
                partition_type = "primary"
            cmd = ["parted", disk, "--script", "mkpart", partition_type,
                   "%ss" % offset_sectors, "%ss" % str(offset_sectors +
                                                       length_sectors)]
            if flag == 'boot':
                cmd.extend(['set', str(partnumber), 'boot', 'on'])

            util.subp(cmd, capture=True)
        elif disk_ptable == "gpt":
            if flag and flag in SGDISK_FLAGS:
                typecode = SGDISK_FLAGS[flag]
            else:
                typecode = SGDISK_FLAGS['linux']
            cmd = ["sgdisk", "--new", "%s:%s:%s" % (partnumber, offset_sectors,
                   length_sectors + offset_sectors),
                   "--typecode=%s:%s" % (partnumber, typecode), disk]
            util.subp(cmd, capture=True)
        elif disk_ptable == "vtoc":
            disk_device_id = storage_config.get(device).get('device_id')
            dasd_device = dasd.DasdDevice(disk_device_id)
            dasd_device.partition(partnumber, length_bytes)
        else:
            raise ValueError("parent partition has invalid partition table")

        # ensure partition exists
        if multipath.is_mpath_device(disk):
            udevadm_settle()  # allow partition creation to happen
            # update device mapper table mapping to mpathX-partN
            part_path = disk + "-part%s" % partnumber
            # sometimes multipath lib creates a block device instead of
            # a udev symlink, remove this and allow kpartx to create it
            if os.path.exists(part_path) and not os.path.islink(part_path):
                util.del_file(part_path)
            util.subp(['kpartx', '-v', '-a', '-s', '-p', '-part', disk])
        else:
            part_path = block.dev_path(block.partition_kname(disk_kname,
                                                             partnumber))
            block.rescan_block_devices([disk])
        udevadm_settle(exists=part_path)

    wipe_mode = info.get('wipe')
    if wipe_mode:
        if wipe_mode == 'superblock' and create_partition:
            # partition creation pre-wipes partition superblock locations
            pass
        else:
            LOG.debug('Wiping partition %s mode=%s', part_path, wipe_mode)
            block.wipe_volume(part_path, mode=wipe_mode, exclusive=False)

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
    LOG.debug("mkfs %s info: %s", volume_path, info)
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


def _get_volume_type(device_path):
    lsblock = block._lsblock([device_path])
    kname = block.path_to_kname(device_path)
    return lsblock[kname]['TYPE']


def get_volume_spec(device_path):
    """
       Return the most reliable spec for a device per Ubuntu FSTAB wiki

       https://wiki.ubuntu.com/FSTAB
    """
    info = udevadm_info(path=device_path)
    block_type = _get_volume_type(device_path)
    LOG.debug('volspec: path=%s type=%s', device_path, block_type)
    LOG.debug('info[DEVLINKS] = %s', info['DEVLINKS'])

    devlinks = []
    # util-linux lsblk may return type=part or type=md for raid partitions
    # handle both by checking path (e.g. /dev/md0p1 should use md-uuid
    # https://github.com/karelzak/util-linux/commit/ef2ce68b1f
    if 'raid' in block_type or device_path.startswith('/dev/md'):
        devlinks = [link for link in info['DEVLINKS']
                    if os.path.basename(link).startswith('md-uuid-')]
    elif block_type in ['crypt', 'lvm', 'mpath']:
        devlinks = [link for link in info['DEVLINKS']
                    if os.path.basename(link).startswith('dm-uuid-')]
    elif block_type in ['disk', 'part']:
        if device_path.startswith('/dev/bcache'):
            devlinks = [link for link in info['DEVLINKS']
                        if link.startswith('/dev/bcache/by-uuid')]
        # on s390x prefer by-path links which are stable and unique.
        if platform.machine() == 's390x':
            devlinks = [link for link in info['DEVLINKS']
                        if link.startswith('/dev/disk/by-path')]
        # use device-mapper uuid if present
        if 'DM_UUID' in info:
            devlinks = [link for link in info['DEVLINKS']
                        if os.path.basename(link).startswith('dm-uuid-')]
        if len(devlinks) == 0:
            # use FS UUID if present
            devlinks = [link for link in info['DEVLINKS']
                        if '/by-uuid' in link]
            if len(devlinks) == 0 and block_type == 'part':
                devlinks = [link for link in info['DEVLINKS']
                            if '/by-partuuid' in link]

    return devlinks[0] if len(devlinks) else device_path


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
        spec = get_volume_spec(fdata.device)
    else:
        spec = fdata.spec

    if fdata.options in (None, "", "defaults"):
        if fdata.fstype == "swap":
            options = "sw"
        else:
            options = "defaults"
    else:
        options = fdata.options

    if path != "none":
        # prefer provided spec over device
        device = fdata.spec if fdata.spec else None
        # if not provided a spec, derive device from calculated spec value
        if not device:
            device = fdata.device if fdata.device else spec
        comment = "# %s was on %s during curtin installation" % (path, device)
    else:
        comment = None

    entry = ' '.join((spec, path, fdata.fstype, options,
                      fdata.freq, fdata.passno)) + "\n"
    line = '\n'.join([comment, entry] if comment else [entry])
    return line


def mount_fstab_data(fdata, target=None):
    """mount the FstabData fdata with root at target.

    :param fdata: a FstabData type
    :return None."""
    mp = paths.target_path(target, fdata.path)
    if fdata.device:
        device = fdata.device
    else:
        if fdata.spec.startswith("/") and not fdata.spec.startswith("/dev/"):
            device = paths.target_path(target, fdata.spec)
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
    state = util.load_command_environment(strict=True)
    mount_apply(mount_data(info, storage_config),
                target=state.get('target'), fstab=state.get('fstab'))


def verify_volgroup_members(vg_name, pv_paths):
    # LVM may be offline, so start it
    lvm.activate_volgroups()
    # Verify that volgroup exists and contains all specified devices
    found_pvs = set(lvm.get_pvols_in_volgroup(vg_name))
    expected_pvs = set(pv_paths)
    msg = ('Verifying lvm volgroup %s members, expected %s, found %s ' % (
           vg_name, expected_pvs, found_pvs))
    LOG.debug(msg)
    if expected_pvs != found_pvs:
        raise RuntimeError(msg)


def lvm_volgroup_verify(vg_name, device_paths):
    verify_volgroup_members(vg_name, device_paths)


def lvm_volgroup_handler(info, storage_config):
    devices = info.get('devices')
    device_paths = []
    name = info.get('name')
    preserve = config.value_as_boolean(info.get('preserve'))
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

    create_vg = True
    if preserve:
        lvm_volgroup_verify(name, device_paths)
        LOG.debug('lvm_volgroup %s already present, skipping create', name)
        create_vg = False

    if create_vg:
        # Create vgrcreate command and run
        # capture output to avoid printing it to log
        # Use zero to clear target devices of any metadata
        util.subp(['vgcreate', '--force', '--zero=y', '--yes',
                   name] + device_paths, capture=True)

    # refresh lvmetad
    lvm.lvm_scan()


def verify_lv_in_vg(lv_name, vg_name):
    found_lvols = lvm.get_lvols_in_volgroup(vg_name)
    msg = ('Verifying %s logical volume is in %s volume '
           'group, found %s ' % (lv_name, vg_name, found_lvols))
    LOG.debug(msg)
    if lv_name not in found_lvols:
        raise RuntimeError(msg)


def verify_lv_size(lv_name, size):
    expected_size_bytes = util.human2bytes(size)
    found_size_bytes = lvm.get_lv_size_bytes(lv_name)
    msg = ('Verifying %s logical value is size bytes %s, found %s '
           % (lv_name, expected_size_bytes, found_size_bytes))
    LOG.debug(msg)
    if expected_size_bytes != found_size_bytes:
        raise RuntimeError(msg)


def lvm_partition_verify(lv_name, vg_name, info):
    verify_lv_in_vg(lv_name, vg_name)
    if 'size' in info:
        verify_lv_size(lv_name, info['size'])


def lvm_partition_handler(info, storage_config):
    volgroup = storage_config[info['volgroup']]['name']
    name = info['name']
    if not volgroup:
        raise ValueError("lvm volgroup for lvm partition must be specified")
    if not name:
        raise ValueError("lvm partition name must be specified")
    if info.get('ptable'):
        raise ValueError("Partition tables on top of lvm logical volumes is "
                         "not supported")
    preserve = config.value_as_boolean(info.get('preserve'))

    create_lv = True
    if preserve:
        lvm_partition_verify(name, volgroup, info)
        LOG.debug('lvm_partition %s already present, skipping create', name)
        create_lv = False

    if create_lv:
        # Use 'wipesignatures' (if available) and 'zero' to clear target lv
        # of any fs metadata
        cmd = ["lvcreate", volgroup, "--name", name, "--zero=y"]
        release = distro.lsb_release()['codename']
        if release not in ['precise', 'trusty']:
            cmd.extend(["--wipesignatures=y"])

        if info.get('size'):
            size = util.human2bytes(info["size"])
            cmd.extend(["--size", "{}B".format(size)])
        else:
            cmd.extend(["--extents", "100%FREE"])

        util.subp(cmd)

    # refresh lvmetad
    lvm.lvm_scan()

    wipe_mode = info.get('wipe', 'superblock')
    if wipe_mode and create_lv:
        lv_path = get_path_to_storage_volume(info['id'], storage_config)
        LOG.debug('Wiping logical volume %s mode=%s', lv_path, wipe_mode)
        block.wipe_volume(lv_path, mode=wipe_mode, exclusive=False)

    make_dname(info['id'], storage_config)


def verify_blkdev_used(dmcrypt_dev, expected_blkdev):
    dminfo = block.dmsetup_info(dmcrypt_dev)
    found_blkdev = dminfo['blkdevs_used']
    msg = (
        'Verifying %s volume, expecting %s , found %s ' % (
         dmcrypt_dev, expected_blkdev, found_blkdev))
    LOG.debug(msg)
    if expected_blkdev != found_blkdev:
        raise RuntimeError(msg)


def dm_crypt_verify(dmcrypt_dev, volume_path):
    verify_exists(dmcrypt_dev)
    verify_blkdev_used(dmcrypt_dev, volume_path)


def dm_crypt_handler(info, storage_config):
    state = util.load_command_environment(strict=True)
    volume = info.get('volume')
    keysize = info.get('keysize')
    cipher = info.get('cipher')
    dm_name = info.get('dm_name')
    if not dm_name:
        dm_name = info.get('id')
    dmcrypt_dev = os.path.join("/dev", "mapper", dm_name)
    preserve = config.value_as_boolean(info.get('preserve'))
    if not volume:
        raise ValueError("volume for cryptsetup to operate on must be \
            specified")

    volume_path = get_path_to_storage_volume(volume, storage_config)
    volume_byid_path = block.disk_to_byid_path(volume_path)

    if 'keyfile' in info:
        if 'key' in info:
            raise ValueError("cannot specify both key and keyfile")
        keyfile_is_tmp = False
        keyfile = info['keyfile']
    elif 'key' in info:
        # TODO: this is insecure, find better way to do this
        key = info.get('key')
        keyfile = tempfile.mkstemp()[1]
        keyfile_is_tmp = True
        util.write_file(keyfile, key, mode=0o600)
    else:
        raise ValueError("encryption key or keyfile must be specified")

    create_dmcrypt = True
    if preserve:
        dm_crypt_verify(dmcrypt_dev, volume_path)
        LOG.debug('dm_crypt %s already present, skipping create', dmcrypt_dev)
        create_dmcrypt = False

    if create_dmcrypt:
        # if zkey is available, attempt to generate and use it; if it's not
        # available or fails to setup properly, fallback to normal cryptsetup
        # passing strict=False downgrades log messages to warnings
        zkey_used = None
        if block.zkey_supported(strict=False):
            volume_name = "%s:%s" % (volume_byid_path, dm_name)
            LOG.debug('Attempting to setup zkey for %s', volume_name)
            luks_type = 'luks2'
            gen_cmd = ['zkey', 'generate', '--xts', '--volume-type', luks_type,
                       '--sector-size', '4096', '--name', dm_name,
                       '--description',
                       "curtin generated zkey for %s" % volume_name,
                       '--volumes', volume_name]
            run_cmd = ['zkey', 'cryptsetup', '--run', '--volumes',
                       volume_byid_path, '--batch-mode', '--key-file', keyfile]
            try:
                util.subp(gen_cmd, capture=True)
                util.subp(run_cmd, capture=True)
                zkey_used = os.path.join(os.path.split(state['fstab'])[0],
                                         "zkey_used")
                # mark in state that we used zkey
                util.write_file(zkey_used, "1")
            except util.ProcessExecutionError as e:
                LOG.exception(e)
                msg = 'Setup of zkey on %s failed, fallback to cryptsetup.'
                LOG.error(msg % volume_path)

        if not zkey_used:
            LOG.debug('Using cryptsetup on %s', volume_path)
            luks_type = "luks"
            cmd = ["cryptsetup"]
            if cipher:
                cmd.extend(["--cipher", cipher])
            if keysize:
                cmd.extend(["--key-size", keysize])
            cmd.extend(["luksFormat", volume_path, keyfile])
            util.subp(cmd)

        cmd = ["cryptsetup", "open", "--type", luks_type, volume_path, dm_name,
               "--key-file", keyfile]

        util.subp(cmd)

        if keyfile_is_tmp:
            os.remove(keyfile)

    wipe_mode = info.get('wipe')
    if wipe_mode:
        if wipe_mode == 'superblock' and create_dmcrypt:
            # newly created dmcrypt volumes do not need superblock wiping
            pass
        else:
            LOG.debug('Wiping dm_crypt device %s mode=%s',
                      dmcrypt_dev, wipe_mode)
            block.wipe_volume(dmcrypt_dev, mode=wipe_mode, exclusive=False)

    # A crypttab will be created in the same directory as the fstab in the
    # configuration. This will then be copied onto the system later
    if state['fstab']:
        state_dir = os.path.dirname(state['fstab'])
        crypt_tab_location = os.path.join(state_dir, "crypttab")
        uuid = block.get_volume_uuid(volume_path)
        util.write_file(crypt_tab_location,
                        "%s UUID=%s none luks\n" % (dm_name, uuid), omode="a")
    else:
        LOG.info("fstab configuration is not present in environment, so \
            cannot locate an appropriate directory to write crypttab in \
            so not writing crypttab")


def verify_md_components(md_devname, raidlevel, device_paths, spare_paths):
    # check if the array is already up, if not try to assemble
    check_ok = mdadm.md_check(md_devname, raidlevel, device_paths,
                              spare_paths)
    if not check_ok:
        LOG.info("assembling preserved raid for %s", md_devname)
        mdadm.mdadm_assemble(md_devname, device_paths, spare_paths)
        check_ok = mdadm.md_check(md_devname, raidlevel, device_paths,
                                  spare_paths)
    msg = ('Verifying %s raid composition, found raid is %s'
           % (md_devname, 'OK' if check_ok else 'not OK'))
    LOG.debug(msg)
    if not check_ok:
        raise RuntimeError(msg)


def raid_verify(md_devname, raidlevel, device_paths, spare_paths):
    verify_md_components(md_devname, raidlevel, device_paths, spare_paths)


def raid_handler(info, storage_config):
    state = util.load_command_environment(strict=True)
    devices = info.get('devices')
    raidlevel = info.get('raidlevel')
    spare_devices = info.get('spare_devices')
    md_devname = block.dev_path(info.get('name'))
    preserve = config.value_as_boolean(info.get('preserve'))
    if not devices:
        raise ValueError("devices for raid must be specified")
    if raidlevel not in ['linear', 'raid0', 0, 'stripe', 'raid1', 1, 'mirror',
                         'raid4', 4, 'raid5', 5, 'raid6', 6, 'raid10', 10]:
        raise ValueError("invalid raidlevel '%s'" % raidlevel)
    if raidlevel in ['linear', 'raid0', 0, 'stripe']:
        if spare_devices:
            raise ValueError("spareunsupported in raidlevel '%s'" % raidlevel)

    LOG.debug('raid: cfg: %s', util.json_dumps(info))
    device_paths = list(get_path_to_storage_volume(dev, storage_config) for
                        dev in devices)
    LOG.debug('raid: device path mapping: %s',
              list(zip(devices, device_paths)))

    spare_device_paths = []
    if spare_devices:
        spare_device_paths = list(get_path_to_storage_volume(dev,
                                  storage_config) for dev in spare_devices)
        LOG.debug('raid: spare device path mapping: %s',
                  list(zip(spare_devices, spare_device_paths)))

    create_raid = True
    if preserve:
        raid_verify(md_devname, raidlevel, device_paths, spare_device_paths)
        LOG.debug('raid %s already present, skipping create', md_devname)
        create_raid = False

    if create_raid:
        mdadm.mdadm_create(md_devname, raidlevel,
                           device_paths, spare_device_paths,
                           info.get('mdname', ''))

    wipe_mode = info.get('wipe')
    if wipe_mode:
        if wipe_mode == 'superblock' and create_raid:
            # Newly created raid devices already wipe member superblocks at
            # their data offset (this is equivalent to wiping the assembled
            # device, see curtin.block.mdadm.zero_device for more details.
            pass
        else:
            LOG.debug('Wiping raid device %s mode=%s', md_devname, wipe_mode)
            block.wipe_volume(md_devname, mode=wipe_mode, exclusive=False)

    # Make dname rule for this dev
    make_dname(info.get('id'), storage_config)

    # A mdadm.conf will be created in the same directory as the fstab in the
    # configuration. This will then be copied onto the installed system later.
    # The file must also be written onto the running system to enable it to run
    # mdadm --assemble and continue installation
    if state['fstab']:
        state_dir = os.path.dirname(state['fstab'])
        mdadm_location = os.path.join(state_dir, "mdadm.conf")
        mdadm_scan_data = mdadm.mdadm_detail_scan()
        util.write_file(mdadm_location, mdadm_scan_data)
    else:
        LOG.info("fstab configuration is not present in the environment, so \
            cannot locate an appropriate directory to write mdadm.conf in, \
            so not writing mdadm.conf")

    # If ptable is specified, call disk_handler on this mdadm device to create
    # the table
    if info.get('ptable'):
        disk_handler(info, storage_config)


def verify_bcache_cachedev(cachedev):
    """ verify that the specified cache_device is a bcache cache device."""
    result = bcache.is_caching(cachedev)
    msg = ('Verifying %s is bcache cache device, found device is %s'
           % (cachedev, 'OK' if result else 'not OK'))
    LOG.debug(msg)
    if not result:
        raise RuntimeError(msg)


def verify_bcache_backingdev(backingdev):
    """ verify that the specified backingdev is a bcache backing device."""
    result = bcache.is_backing(backingdev)
    msg = ('Verifying %s is bcache backing device, found device is %s'
           % (backingdev, 'OK' if result else 'not OK'))
    LOG.debug(msg)
    if not result:
        raise RuntimeError(msg)


def verify_cache_mode(backing_dev, backing_superblock, expected_mode):
    """ verify the backing device cache-mode is set as expected. """
    found = backing_superblock.get('dev.data.cache_mode', '')
    msg = ('Verifying %s bcache cache-mode, expecting %s, found %s'
           % (backing_dev, expected_mode, found))
    LOG.debug(msg)
    if expected_mode not in found:
        raise RuntimeError(msg)


def verify_bcache_cset_uuid_match(backing_dev, cinfo, binfo):
    expected_cset_uuid = cinfo.get('cset.uuid')
    found_cset_uuid = binfo.get('cset.uuid')
    result = ((expected_cset_uuid == found_cset_uuid)
              if expected_cset_uuid else False)
    msg = ('Verifying bcache backing_device %s cset.uuid is %s, found %s'
           % (backing_dev, expected_cset_uuid, found_cset_uuid))
    LOG.debug(msg)
    if not result:
        raise RuntimeError(msg)


def bcache_verify_cachedev(cachedev):
    verify_bcache_cachedev(cachedev)
    return True


def bcache_verify_backingdev(backingdev):
    verify_bcache_backingdev(backingdev)
    return True


def bcache_verify(cachedev, backingdev, cache_mode):
    bcache_verify_cachedev(cachedev)
    bcache_verify_backingdev(backingdev)
    cache_info = bcache.superblock_asdict(cachedev)
    backing_info = bcache.superblock_asdict(backingdev)
    verify_bcache_cset_uuid_match(backingdev, cache_info, backing_info)
    if cache_mode:
        verify_cache_mode(backingdev, backing_info, cache_mode)

    return True


def bcache_handler(info, storage_config):
    backing_device = get_path_to_storage_volume(info.get('backing_device'),
                                                storage_config)
    cache_device = get_path_to_storage_volume(info.get('cache_device'),
                                              storage_config)
    cache_mode = info.get('cache_mode', None)
    preserve = config.value_as_boolean(info.get('preserve'))

    if not backing_device or not cache_device:
        raise ValueError("backing device and cache device for bcache"
                         " must be specified")

    create_bcache = True
    if preserve:
        if cache_device and backing_device:
            if bcache_verify(cache_device, backing_device, cache_mode):
                create_bcache = False
        elif cache_device:
            if bcache_verify_cachedev(cache_device):
                create_bcache = False
        elif backing_device:
            if bcache_verify_backingdev(backing_device):
                create_bcache = False
        if not create_bcache:
            LOG.debug('bcache %s already present, skipping create', info['id'])

    cset_uuid = bcache_dev = None
    if create_bcache and cache_device:
        cset_uuid = bcache.create_cache_device(cache_device)

    if create_bcache and backing_device:
        bcache_dev = bcache.create_backing_device(backing_device, cache_device,
                                                  cache_mode, cset_uuid)

    if cache_mode and not backing_device:
        raise ValueError("cache mode specified which can only be set on "
                         "backing devices, but none was specified")

    wipe_mode = info.get('wipe')
    if wipe_mode and bcache_dev:
        LOG.debug('Wiping bcache device %s mode=%s', bcache_dev, wipe_mode)
        block.wipe_volume(bcache_dev, mode=wipe_mode, exclusive=False)

    if info.get('name'):
        # Make dname rule for this dev
        make_dname(info.get('id'), storage_config)

    if info.get('ptable'):
        disk_handler(info, storage_config)

    LOG.debug('Finished bcache creation for backing %s or caching %s',
              backing_device, cache_device)


def zpool_handler(info, storage_config):
    """
    Create a zpool based in storage_configuration
    """
    zfs.zfs_assert_supported()

    state = util.load_command_environment(strict=True)

    # extract /dev/disk/by-id paths for each volume used
    vdevs = [get_path_to_storage_volume(v, storage_config)
             for v in info.get('vdevs', [])]
    poolname = info.get('pool')
    mountpoint = info.get('mountpoint')
    pool_properties = info.get('pool_properties', {})
    fs_properties = info.get('fs_properties', {})
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
                     mountpoint=mountpoint, altroot=altroot,
                     pool_properties=pool_properties,
                     zfs_properties=fs_properties)


def zfs_handler(info, storage_config):
    """
    Create a zfs filesystem
    """
    zfs.zfs_assert_supported()

    state = util.load_command_environment(strict=True)
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


def get_device_paths_from_storage_config(storage_config):
    """Returns a list of device paths in a storage config which have wipe
       config enabled filtering out constructed paths that do not exist.

    :param: storage_config: Ordered dict of storage configation
    """
    dpaths = []
    for (k, v) in storage_config.items():
        if v.get('type') in ['disk', 'partition']:
            if config.value_as_boolean(v.get('wipe')):
                try:
                    # skip paths that do not exit, nothing to wipe
                    dpath = get_path_to_storage_volume(k, storage_config)
                    if os.path.exists(dpath):
                        dpaths.append(dpath)
                except Exception:
                    pass
    return dpaths


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


def meta_clear(devices, report_prefix=''):
    """ Run clear_holders on specified list of devices.

    :param: devices: a list of block devices (/dev/XXX) to be cleared
    :param: report_prefix: a string to pass to the ReportEventStack
    """
    # shut down any already existing storage layers above any disks used in
    # config that have 'wipe' set
    with events.ReportEventStack(
            name=report_prefix + '/clear-holders',
            reporting_enabled=True, level='INFO',
            description="removing previous storage devices"):
        clear_holders.start_clear_holders_deps()
        clear_holders.clear_holders(devices)
        # if anything was not properly shut down, stop installation
        clear_holders.assert_clear(devices)


def meta_custom(args):
    """Does custom partitioning based on the layout provided in the config
    file. Section with the name storage contains information on which
    partitions on which disks to create. It also contains information about
    overlays (raid, lvm, bcache) which need to be setup.
    """

    command_handlers = {
        'dasd': dasd_handler,
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

    state = util.load_command_environment(strict=True)
    cfg = config.load_command_config(args, state)

    storage_config_dict = extract_storage_ordered_dict(cfg)

    storage_config_dict = zfsroot_update_storage_config(storage_config_dict)

    # set up reportstack
    stack_prefix = state.get('report_stack_prefix', '')

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
    state = util.load_command_environment(strict=True)
    cfg = config.load_command_config(args, state)
    if args.target is not None:
        state['target'] = args.target

    if state['target'] is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

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

    devices = args.devices
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
