#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

from collections import OrderedDict
from curtin import block
from curtin import util
from curtin.log import LOG

from . import populate_one_subcmd

import os
import parted
import platform
import string
import sys

SIMPLE = 'simple'
SIMPLE_BOOT = 'simple-boot'
CUSTOM = 'custom'

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
     ('mode', {'help': 'meta-mode to use',
               'choices': [CUSTOM, SIMPLE, SIMPLE_BOOT]}),
     )
)


def block_meta(args):
    # main entry point for the block-meta command.
    if args.mode in (SIMPLE, SIMPLE_BOOT):
        meta_simple(args)
    elif args.mode == CUSTOM:
        meta_custom(args)
    else:
        raise NotImplementedError("mode=%s is not implemented" % args.mode)


def logtime(msg, func, *args, **kwargs):
    with util.LogTimer(LOG.debug, msg):
        return func(*args, **kwargs)


def write_image_to_disk(source, dev):
    """
    Write disk image to block device
    """
    (devname, devnode) = block.get_dev_name_entry(dev)
    util.subp(args=['sh', '-c',
                    ('wget "$1" --progress=dot:mega -O - |'
                     'tar -SxOzf - | dd of="$2"'),
                    '--', source, devnode])
    util.subp(['partprobe', devnode])
    util.subp(['udevadm', 'settle'])
    return block.get_root_device([devname, ])


def get_bootpt_cfg(cfg, enabled=False, fstype=None, root_fstype=None):
    # 'cfg' looks like:
    #   enabled: boolean
    #   fstype: filesystem type (default to 'fstype')
    #   label:  filesystem label (default to 'boot')
    # parm enable can enable, but not disable
    # parm fstype overrides cfg['fstype']
    def_boot = platform.machine() in ('aarch64')
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


def get_path_to_storage_device(device_id, storage_config):
    # Get path to block device for physical device. Device_id param should refer
    # to id of device in storage config
    for item in storage_config:
        if item.get('id') == device_id:
            device = item
            break
    if not device:
        raise ValueError("device with id '%s' not found" % device_id)

    disk_block = block.lookup_disk(serial=device.get('serial'),
            busid=device.get('busid'))
    if not disk_block:
        raise ValueError("disk not found")

    return disk_block['device_path']


def get_path_to_storage_volume(volume, storage_config):
    # Get path to block device for volume. Volume param should refer to id of
    # volume in storage config

    for item in storage_config:
        if item.get('id') == volume:
            vol = item
            break
    if not vol:
        raise ValueError("volume with id '%s' not found" % device)

    # Find path to block device
    if vol.get('type') == "partition":
        # For partitions, get block device, and use Disk.getPartitionBySector()
        # to grab partition object, then get path using Partition.path()
        disk_block_path = get_path_to_storage_device(vol.get('device'), \
                storage_config)
        pdev = parted.getDevice(disk_block_path)
        pdisk = parted.newDisk(pdev)
        ppart = pdisk.getPartitionBySector(parted.sizeToSectors(int( \
            vol.get('offset').strip(string.ascii_letters)) + 1, \
            vol.get('offset').strip(string.digits), pdisk.device.sectorSize))
        volume_path = ppart.path
    else:
        raise NotImplementedError("volumes other than partitions not yet \
            supported")

    return volume_path


def disk_handler(info, storage_config):
    serial = info.get('serial')
    busid = info.get('busid')
    ptable = info.get('ptable')
    if not serial and not busid:
        raise ValueError("either serial number or bus id needs to"
                         "be specified to identify disk")
    disk = block.lookup_disk(serial=serial, busid=busid)
    if not disk:
        raise ValueError("disk with serial '%s' and bus id '%s'"
                         "not found" % (serial, busid))
    if not ptable:
        # TODO: check this behavior
        ptable = "msdos"

    # Get device and disk using parted using appropriate partition table
    pdev = parted.getDevice(disk['device_path'])
    pdisk = parted.freshDisk(pdev, ptable)
    LOG.info("labeling device: '%s' with '%s' partition table", disk, ptable)
    pdisk.commit()


def partition_handler(info, storage_config):
    device = info.get('device')
    offset = info.get('offset')
    size = info.get('size')
    flag = info.get('flag')
    if not device:
        raise ValueError("device must be set for partition to be created")
    if not offset:
        # TODO: instead of bailing, find beginning of free space on disk and go
        #       from there
        raise ValueError("offset must be specified for partition to be \
        created")
    if not size:
        raise ValueError("size must be specified for partition to be created")

    # Find device to attach to in storage_config
    # TODO: find a more efficient way to do this
    disk = get_path_to_storage_device(device, storage_config)
    pdev = parted.getDevice(disk)
    pdisk = parted.newDisk(pdev)

    # Convert offset and length into sectors
    offset_sectors = parted.sizeToSectors(int(offset.strip( \
        string.ascii_letters)), offset.strip(string.digits), \
        pdisk.device.sectorSize)
    length_sectors = parted.sizeToSectors(int(size.strip( \
        string.ascii_letters)), size.strip(string.digits), \
        pdisk.device.sectorSize)

    # Make geometry and partition
    geometry = parted.Geometry(device=pdisk.device, start=offset_sectors,
        length=length_sectors)
    partition = parted.Partition(disk=pdisk, type=parted.PARTITION_NORMAL,
        geometry=geometry)
    constraint = parted.Constraint(exactGeom=partition.geometry)

    # Set flag
    if flag:
        if flag == "boot":
            partition.setFlag(parted.PARTITION_BOOT)
        elif flag == "lvm":
            partition.setFlag(parted.PARTITION_LVM)
        else:
            raise ValueError("invalid partition flag '%s'" % flag)

    # Add partition to disk and commit changes
    LOG.info("adding partition '%s' to disk '%s'" % (info.get('id'), device))
    pdisk.addPartition(partition, constraint)
    pdisk.commit()


def format_handler(info, storage_config):
    fstype = info.get('fstype')
    volume = info.get('volume')
    part_id = info.get('id')
    if not volume:
        raise ValueError("volume must be specified for partition '%s'" %
            info.get('id'))

    # Get path to volume
    volume_path = get_path_to_storage_volume(volume, storage_config)

    # Generate mkfs command and run
    if fstype in ["ext4", "ext3"]:
        cmd = ['mkfs.%s' % fstype, '-q', '-L', part_id[:16], volume_path]
    elif fstype in ["fat16", "fat32", "fat"]:
        cmd = ["mkfs.fat"]
        fat_size = fstype.strip(string.ascii_letters)
        if fat_size in ["12", "16", "32"]:
            cmd.extend(["-F", fat_size])
        cmd.extend(["-n", part_id[:11], volume_path])
    else:
        raise ValueError("fstype '%s' not supported" % fstype)
    LOG.info("formatting volume '%s' with format '%s'" % (volume_path, fstype))
    logtime(' '.join(cmd), util.subp, cmd)


def mount_handler(info, storage_config):
    state = util.load_command_environment()
    path = info.get('path')
    device = info.get('device')
    if not path:
        raise ValueError("path to mountpoint must be specified")
    if not device:
        raise ValueError("formated volume must be specified")

    # Get filesystem in storage_config
    for item in storage_config:
        if item.get('id') == device:
            filesystem = item
            break
    if not filesystem:
        raise ValueError("filesystem '%s' could not be found" % device)

    # Get path to volume
    volume_path = get_path_to_storage_volume(filesystem.get('volume'), \
            storage_config)

    # Figure out what point should be
    while len(path) > 0 and path[0] == "/":
        path = path[1:]
    mount_point = os.path.join(state['target'], path)

    # Create mount point if does not exist
    if not os.path.isdir(mount_point):
        os.makedirs(mount_point)

    # Mount volume
    util.subp(['mount', volume_path, mount_point])

    # Add volume to fstab
    if state['fstab']:
        with open(state['fstab'], "a") as fp:
            fp.write("LABEL=%s /%s %s defaults 0 0\n" %
                    (filesystem.get('id')[:16], path, filesystem.get('fstype')))
    else:
        LOG.info("fstab not in environment, so not writing")


def lvm_volgroup_handler(info, storage_config):
    devices = info.get('devices')
    if not devices:
        raise ValueError("devices for volgroup '%s' must be specified" %
                info.get('id'))

    cmd = ["vgcreate", info.get('id')]
    for device_id in devices:
        # Get device in config
        for item in storage_config:
            if item.get('id') == device_id:
                device = item
                break
        if not device:
            raise ValueError("device '%s' could not be found in storage config"
                    % device_id)
        if device.get('type') == "partition":
            device_path = get_path_to_storage_volume(device_id, storage_config)
        elif device.get('type') == "disk":
            device_path = get_path_to_storage_device(device_id, storage_config)
        else:
            raise ValueError("volumes for lvm other than partitions and \
                physical volumes not supported")

        # Add device to command
        cmd.append(device_path)

    util.subp(cmd)


def lvm_partition_handler(info, storage_config):
    volgroup = info.get('volgroup')
    if not volgroup:
        raise ValueError("lvm volgroup for lvm partition must be specified")
    cmd = ["lvcreate", volgroup, "-n", info.get('id')]
    if info.get('size'):
        cmd.extend(["-L", info.get('size')])
    else:
        cmd.extend(["-l", "100%FREE"])

    util.subp(cmd)


def meta_custom(args):
    """Does custom partitioning based on the layout provided in the config
    file. Section with the name storage contains information on which
    partitions on which disks to create. It also contains information about
    overlays (raid, lvm, bcache) which need to be setup.
    """

    command_handlers = {
        'disk': disk_handler,
        'partition': partition_handler,
        'format' : format_handler,
        'mount' : mount_handler,
        'lvm_volgroup' : lvm_volgroup_handler,
        'lvm_partition' : lvm_partition_handler
    }

    state = util.load_command_environment()
    cfg = util.load_command_config(args, state)

    storage_config = cfg.get('storage', [])
    if not storage_config:
        raise Exception("storage configuration is required by mode '%s' "
                        "but not provided in the config file" % CUSTOM)

    for command in storage_config:
        handler = command_handlers.get(command['type'])
        if not handler:
            raise ValueError("unknown command type '%s'" % command['type'])
        handler(command, storage_config)

    return 0


def meta_simple(args):
    """Creates a root partition. If args.mode == SIMPLE_BOOT, it will also
    create a separate /boot partition.
    """
    state = util.load_command_environment()

    cfg = util.load_command_config(args, state)

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

    if len(devices) == 0:
        devices = block.get_installable_blockdevs()
        LOG.warn("'%s' mode, no devices given. unused list: %s",
                 args.mode, devices)

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

    if state['fstab']:
        with open(state['fstab'], "w") as fp:
            if bootpt['enabled']:
                fp.write("LABEL=%s /boot %s defaults 0 0\n" %
                         (bootpt['label'], bootpt['fstype']))
            fp.write("LABEL=%s / %s defaults 0 0\n" %
                     ('cloudimg-rootfs', args.fstype))
    else:
        LOG.info("fstab not in environment, so not writing")

    return 0


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_meta)

# vi: ts=4 expandtab syntax=python
