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
import tempfile


CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'default': None, }),
     ('--fstype', {'help': 'root filesystem type',
                   'choices': ['ext4', 'ext3'], 'default': 'ext4'}),
     ('mode', {'help': 'meta-mode to use', 'choices': ['raid0', 'simple', 'simple-boot']}),
     )
)


def block_meta(args):
    # main entry point for the block-meta command.
    if args.mode == "simple":
        meta_simple(args)
    elif args.mode == "simple-boot":
        meta_simple_boot(args)
    else:
        raise NotImplementedError("mode=%s is not implemenbed" % args.mode)


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
    util.subp(['partprobe'])
    util.subp(['udevadm', 'settle'])
    return block.get_root_device([devname, ])


def meta_simple(args):
    state = util.load_command_environment()

    cfg = util.load_command_config(args, state)

    devices = args.devices
    if devices is None:
        devices = cfg.get('block-meta', {}).get('devices', [])

    # Remove duplicates but maintain ordering.
    devices = list(OrderedDict.fromkeys(devices))

    if len(devices) == 0:
        devices = block.get_installable_blockdevs()
        LOG.warn("simple mode, no devices given. unused list: %s", devices)

    if len(devices) > 1:
        if args.devices is not None:
            LOG.warn("simple mode but multiple devices given. "
                     "using first found")
        available = [f for f in devices
                     if block.is_valid_device(f)]
        target = sorted(available)[0]
        LOG.warn("mode is 'simple'. multiple devices given. using '%s' "
                 "(first available)", target)
    else:
        target = devices[0]

    if not block.is_valid_device(target):
        raise Exception("target device '%s' is not a valid device" % target)

    (devname, devnode) = block.get_dev_name_entry(target)

    LOG.info("installing in simple mode to '%s'", devname)

    sources = cfg.get('sources', {})
    dd_images = util.get_dd_images(sources)
    if len(dd_images):
        # we have at least one dd-able image
        # we will only take the first one
        rootdev = write_image_to_disk(dd_images[0], devname)
        util.subp(['mount', rootdev, state['target']])
        return 0

    # helper partition will forcibly set up partition there
    if util.is_uefi_bootable():
        logtime(
            "partition --format uefi %s" % devnode,
            util.subp, ("partition", "--format", "uefi", devnode))
    else:
        logtime(
            "partition %s" % devnode,
            util.subp, ("partition", devnode))

    rootdev = devnode + "1"

    cmd = ['mkfs.%s' % args.fstype, '-q', '-L', 'cloudimg-rootfs', rootdev]
    logtime(' '.join(cmd), util.subp, cmd)

    util.subp(['mount', rootdev, state['target']])

    with open(state['fstab'], "w") as fp:
        fp.write("LABEL=%s / %s defaults 0 0\n" % ('cloudimg-rootfs', args.fstype))

    return 0


def meta_simple_boot(args):
    """Similar to meta_simple but it also creates an extra /boot partition.
    This is needed from some instances of u-boot.
    """
    # This is loading command environment k,v pairs such as 'fstab': 
    # 'OUTPUT_FSTAB', which points to the fstab file path
    state = util.load_command_environment()

    # This is taking the state dictionary above and finds whether either the
    # args or the state have a configuration file and this is what is returned
    cfg = util.load_command_config(args, state)

    # I believe this is finding if there are any /dev/sda etc. devices using
    # the --device (or is it --devices) flag from the config file
    devices = args.devices
    if devices is None:
        devices = cfg.get('block-meta', {}).get('devices', [])

    # Remove duplicates but maintain ordering.
    devices = list(OrderedDict.fromkeys(devices))

    if len(devices) == 0:
        devices = block.get_installable_blockdevs()
        LOG.warn("simple-boot mode, no devices given. unused list: %s", devices)

    if len(devices) > 1:
        if args.devices is not None:
            LOG.warn("simple-boot mode but multiple devices given. "
                     "using first found")
        available = [f for f in devices
                     if block.is_valid_device(f)]
        target = sorted(available)[0]
        LOG.warn("mode is 'simple-boot'. multiple devices given. using '%s' "
                 "(first available)", target)
    else:
        target = devices[0]

    if not block.is_valid_device(target):
        raise Exception("target device '%s' is not a valid device" % target)

    (devname, devnode) = block.get_dev_name_entry(target)

    LOG.info("installing in simple-boot mode to '%s'", devname)

    sources = cfg.get('sources', {})
    dd_images = util.get_dd_images(sources)
    LOG.info("NEWELL: dd_images found %s" % dd_images)
    LOG.info("NEWELL: len(dd_images) found %s" % len(dd_images))
    if len(dd_images):
        # we have at least one dd-able image
        # we will only take the first one
        rootdev = write_image_to_disk(dd_images[0], devname)
        util.subp(['mount', rootdev, state['target']])
        return 0

    # I believe this is where I will need to create the extra partition size
    # helper partition will forcibly set up partition there
    if util.is_uefi_bootable():
        logtime(
            "partition --format uefi --boot %s" % devnode,
            util.subp, ("partition", "--format", "uefi", "--boot", devnode))
    else:
        logtime(
            "partition --boot %s" % devnode,
            util.subp, ("partition", "--boot", devnode))

    bootdev = devnode + "1"
    rootdev = devnode + "2"
    LOG.info("NEWELL: bootdev %s" % bootdev)
    LOG.info("NEWELL: rootdev %s" % rootdev)

    cmd = ['mkfs.%s' % args.fstype, '-q', '-L', 'cloudimg-rootfs-boot', bootdev]
    LOG.info("NEWELL: cmd %s" % cmd)    
    logtime(' '.join(cmd), util.subp, cmd)
    util.subp(['mount', bootdev, state['target']])

    cmd = ['mkfs.%s' % args.fstype, '-q', '-L', 'cloudimg-rootfs', rootdev]
    LOG.info("NEWELL: cmd %s" % cmd)    
    logtime(' '.join(cmd), util.subp, cmd)
    util.subp(['mount', rootdev, state['target']])

    with open(state['fstab'], "w") as fp:
        fp.write("LABEL=%s /boot %s defaults 0 0\n" % ('cloudimg-rootfs-boot', args.fstype))
        fp.write("LABEL=%s / %s defaults 0 0\n" % ('cloudimg-rootfs', args.fstype))

    return 0


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_meta)

# vi: ts=4 expandtab syntax=python
