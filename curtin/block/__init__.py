# This file is part of curtin. See LICENSE file for copyright and license info.
import re
from contextlib import contextmanager
import errno
import itertools
import os
import stat
import sys
import tempfile

from curtin import util
from curtin.block import lvm
from curtin.block import multipath
from curtin.log import LOG
from curtin.udev import udevadm_settle, udevadm_info
from curtin.util import NotExclusiveError
from curtin import storage_config


SECTOR_SIZE_BYTES = 512


def get_dev_name_entry(devname):
    """
    convert device name to path in /dev
    """
    bname = devname.split('/dev/')[-1]
    return (bname, "/dev/" + bname)


def is_valid_device(devname):
    """
    check if device is a valid device
    """
    devent = get_dev_name_entry(devname)[1]
    return is_block_device(devent)


def is_block_device(path):
    """
    check if path is a block device
    """
    try:
        return stat.S_ISBLK(os.stat(path).st_mode)
    except OSError as e:
        if not util.is_file_not_found_exc(e):
            raise
    return False


def dev_short(devname):
    """
    get short form of device name
    """
    devname = os.path.normpath(devname)
    if os.path.sep in devname:
        return os.path.basename(devname)
    return devname


def dev_path(devname):
    """
    convert device name to path in /dev
    """
    if devname.startswith('/dev/'):
        # it could be something like /dev/mapper/mpatha-part2
        return os.path.realpath(devname)
    else:
        return '/dev/' + devname


def md_path(mdname):
    """ Convert device name to path in /dev/md """
    full_mdname = dev_path(mdname)
    if full_mdname.startswith('/dev/md/'):
        return full_mdname
    elif re.match(r'/dev/md\d+$', full_mdname):
        return full_mdname
    elif '/' in mdname:
        raise ValueError("Invalid RAID device name: {}".format(mdname))
    else:
        return '/dev/md/{}'.format(mdname)


def path_to_kname(path):
    """
    converts a path in /dev or a path in /sys/block to the device kname,
    taking special devices and unusual naming schemes into account
    """
    # if path given is a link, get real path
    # only do this if given a path though, if kname is already specified then
    # this would cause a failure where the function should still be able to run
    if os.path.sep in path:
        path = os.path.realpath(path)
    # using basename here ensures that the function will work given a path in
    # /dev, a kname, or a path in /sys/block as an arg
    dev_kname = os.path.basename(path)
    # cciss devices need to have 'cciss!' prepended
    if path.startswith('/dev/cciss'):
        dev_kname = 'cciss!' + dev_kname
    return dev_kname


def kname_to_path(kname):
    """
    converts a kname to a path in /dev, taking special devices and unusual
    naming schemes into account
    """
    # if given something that is already a dev path, return it
    if os.path.exists(kname) and is_valid_device(kname):
        path = kname
        return os.path.realpath(path)
    # adding '/dev' to path is not sufficient to handle cciss devices and
    # possibly other special devices which have not been encountered yet
    path = os.path.realpath(os.sep.join(['/dev'] + kname.split('!')))
    # make sure path we get is correct
    if not (os.path.exists(path) and is_valid_device(path)):
        raise OSError('could not get path to dev from kname: {}'.format(kname))
    return path


def partition_kname(disk_kname, partition_number):
    """
    Add number to disk_kname prepending a 'p' if needed
    """
    if disk_kname.startswith('dm-'):
        # device-mapper devices may create a new dm device for the partition,
        # e.g. multipath disk is at dm-2, new partition could be dm-11, but
        # linux will create a -partX symlink against the disk by-id name.
        devpath = '/dev/' + disk_kname
        disk_link = get_device_mapper_links(devpath, first=True)
        return path_to_kname(
                    os.path.realpath('%s-part%s' % (disk_link,
                                                    partition_number)))

    # follow the same rules the kernel check_partition() does
    # https://github.com/torvalds/linux/blob/0473719/block/partitions/core.c#L330
    if disk_kname[-1:].isdigit():
        partition_number = "p%s" % partition_number
    return "%s%s" % (disk_kname, partition_number)


def sysfs_to_devpath(sysfs_path):
    """
    convert a path in /sys/class/block to a path in /dev
    """
    path = kname_to_path(path_to_kname(sysfs_path))
    if not is_block_device(path):
        raise ValueError('could not find blockdev for sys path: {}'
                         .format(sysfs_path))
    return path


def sys_block_path(devname, add=None, strict=True):
    """
    get path to device in /sys/class/block
    """
    toks = ['/sys/class/block']
    # insert parent dev if devname is partition
    devname = os.path.normpath(devname)
    if devname.startswith('/dev/') and not os.path.exists(devname):
        LOG.warning('block.sys_block_path: devname %s does not exist', devname)

    toks.append(path_to_kname(devname))

    if add is not None:
        toks.append(add)
    path = os.sep.join(toks)

    if strict and not os.path.exists(path):
        err = OSError(
            "devname '{}' did not have existing syspath '{}'".format(
                devname, path))
        err.errno = errno.ENOENT
        raise err

    return os.path.normpath(path)


def get_holders(device):
    """
    Look up any block device holders, return list of knames
    """
    # block.sys_block_path works when given a /sys or /dev path
    sysfs_path = sys_block_path(device)
    # get holders
    holders = os.listdir(os.path.join(sysfs_path, 'holders'))
    LOG.debug("devname '%s' had holders: %s", device, holders)
    return holders


def get_device_slave_knames(device):
    """
    Find the underlying knames of a given device by walking sysfs
    recursively.

    Returns a list of knames
    """
    slave_knames = []
    slaves_dir_path = os.path.join(sys_block_path(device), 'slaves')

    # if we find a 'slaves' dir, recurse and check
    # the underlying devices
    if os.path.exists(slaves_dir_path):
        slaves = os.listdir(slaves_dir_path)
        if len(slaves) > 0:
            for slave_kname in slaves:
                slave_knames.extend(get_device_slave_knames(slave_kname))
        else:
            slave_knames.append(path_to_kname(device))

        return slave_knames
    else:
        # if a device has no 'slaves' attribute then
        # we've found the underlying device, return
        # the kname of the device
        return [path_to_kname(device)]


def _lsblock_pairs_to_dict(lines):
    """
    parse lsblock output and convert to dict
    """
    ret = {}
    for line in lines.splitlines():
        toks = util.shlex_split(line)
        cur = {}
        for tok in toks:
            k, v = tok.split("=", 1)
            if k == 'MAJ_MIN':
                k = 'MAJ:MIN'
            else:
                k = k.replace('_', '-')
            cur[k] = v
        # use KNAME, as NAME may include spaces and other info,
        # for example, lvm decices may show 'dm0 lvm1'
        cur['device_path'] = get_dev_name_entry(cur['KNAME'])[1]
        ret[cur['KNAME']] = cur
    return ret


def _lsblock(args=None):
    """
    get lsblock data as dict
    """
    # lsblk  --help | sed -n '/Available/,/^$/p' |
    #     sed -e 1d -e '$d' -e 's,^[ ]\+,,' -e 's, .*,,' | sort
    keys = ['ALIGNMENT', 'DISC-ALN', 'DISC-GRAN', 'DISC-MAX', 'DISC-ZERO',
            'FSTYPE', 'GROUP', 'KNAME', 'LABEL', 'LOG-SEC', 'MAJ:MIN',
            'MIN-IO', 'MODE', 'MODEL', 'MOUNTPOINT', 'NAME', 'OPT-IO', 'OWNER',
            'PHY-SEC', 'RM', 'RO', 'ROTA', 'RQ-SIZE', 'SCHED', 'SIZE', 'STATE',
            'TYPE', 'UUID']
    if args is None:
        args = []
    args = [x.replace('!', '/') for x in args]

    # in order to avoid a very odd error with '-o' and all output fields above
    # we just drop one.  doesn't really matter which one.
    keys.remove('SCHED')
    basecmd = ['lsblk', '--noheadings', '--bytes', '--pairs',
               '--output=' + ','.join(keys)]
    (out, _err) = util.subp(basecmd + list(args), capture=True)
    out = out.replace('!', '/')
    return _lsblock_pairs_to_dict(out)


def sfdisk_info(devpath):
    ''' returns dict of sfdisk info about disk partitions
    {
      "label": "gpt",
      "id": "877716F7-31D0-4D56-A1ED-4D566EFE418E",
      "device": "/dev/vda",
      "unit": "sectors",
      "firstlba": 34,
      "lastlba": 41943006,
      "partitions": [
         {"node": "/dev/vda1", "start": 227328, "size": 41715679,
          "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
          "uuid": "60541CAF-E2AC-48CD-BF89-AF16051C833F"},
      ]
    }
    {
      "label":"dos",
      "id":"0xb0dbdde1",
      "device":"/dev/vdb",
      "unit":"sectors",
      "partitions": [
         {"node":"/dev/vdb1", "start":2048, "size":8388608,
          "type":"83", "bootable":true},
         {"node":"/dev/vdb2", "start":8390656, "size":8388608, "type":"83"},
         {"node":"/dev/vdb3", "start":16779264, "size":62914560, "type":"5"},
         {"node":"/dev/vdb5", "start":16781312, "size":31457280, "type":"83"},
         {"node":"/dev/vdb6", "start":48240640, "size":10485760, "type":"83"},
         {"node":"/dev/vdb7", "start":58728448, "size":20965376, "type":"83"}
      ]
    }
    '''
    (parent, partnum) = get_blockdev_for_partition(devpath)
    try:
        (out, _err) = util.subp(['sfdisk', '--json', parent], capture=True)
    except util.ProcessExecutionError as e:
        out = None
        LOG.exception(e)
    if out is not None:
        return util.load_json(out).get('partitiontable', {})

    return {}


def get_partition_sfdisk_info(devpath, sfdisk_info=None):
    if not sfdisk_info:
        sfdisk_info = sfdisk_info(devpath)

    entry = [part for part in sfdisk_info['partitions']
             if os.path.realpath(part['node']) == os.path.realpath(devpath)]
    if len(entry) != 1:
        raise RuntimeError('Device %s not present in sfdisk dump:\n%s' %
                           devpath, util.json_dumps(sfdisk_info))
    return entry.pop()


def dmsetup_info(devname):
    ''' returns dict of info about device mapper dev.

    {'blkdevname': 'dm-0',
     'blkdevs_used': 'sda5',
     'name': 'sda5_crypt',
     'subsystem': 'CRYPT',
     'uuid': 'CRYPT-LUKS1-2b370697149743b0b2407d11f88311f1-sda5_crypt'
    }
    '''
    _SEP = '='
    fields = ('name,uuid,blkdevname,blkdevs_used,subsystem'.split(','))
    try:
        (out, _err) = util.subp(['dmsetup', 'info', devname, '-C', '-o',
                                 ','.join(fields), '--noheading',
                                 '--separator', _SEP], capture=True)
    except util.ProcessExecutionError as e:
        LOG.error('Failed to run dmsetup info: %s', e)
        return {}

    values = out.strip().split(_SEP)
    info = dict(zip(fields, values))
    return info


def get_unused_blockdev_info():
    """
    return a list of unused block devices.
    These are devices that do not have anything mounted on them.
    """

    # get a list of top level block devices, then iterate over it to get
    # devices dependent on those.  If the lsblk call for that specific
    # call has nothing 'MOUNTED", then this is an unused block device
    bdinfo = _lsblock(['--nodeps'])
    unused = {}
    for devname, data in bdinfo.items():
        cur = _lsblock([data['device_path']])
        mountpoints = [x for x in cur if cur[x].get('MOUNTPOINT')]
        if len(mountpoints) == 0:
            unused[devname] = data
    return unused


def get_devices_for_mp(mountpoint):
    """
    return a list of devices (full paths) used by the provided mountpoint
    """
    bdinfo = _lsblock()
    found = set()
    for devname, data in bdinfo.items():
        if data['MOUNTPOINT'] == mountpoint:
            found.add(data['device_path'])

    if found:
        return list(found)

    # for some reason, on some systems, lsblk does not list mountpoint
    # for devices that are mounted.  This happens on /dev/vdc1 during a run
    # using tools/launch.
    mountpoint = [os.path.realpath(dev)
                  for (dev, mp, vfs, opts, freq, passno) in
                  get_proc_mounts() if mp == mountpoint]

    return mountpoint


def get_installable_blockdevs(include_removable=False, min_size=1024**3):
    """
    find blockdevs suitable for installation
    """
    good = []
    unused = get_unused_blockdev_info()
    for devname, data in unused.items():
        if not include_removable and data.get('RM') == "1":
            continue
        if data.get('RO') != "0" or data.get('TYPE') != "disk":
            continue
        if min_size is not None and int(data.get('SIZE', '0')) < min_size:
            continue
        good.append(devname)
    return good


def get_blockdev_for_partition(devpath, strict=True):
    """
    find the parent device for a partition.
    returns a tuple of the parent block device and the partition number
    if device is not a partition, None will be returned for partition number
    """
    # normalize path
    rpath = os.path.realpath(devpath)

    # convert an entry in /dev/ to parent disk and partition number
    # if devpath is a block device and not a partition, return (devpath, None)
    base = '/sys/class/block'

    # input of /dev/vdb, /dev/disk/by-label/foo, /sys/block/foo,
    # /sys/block/class/foo, or just foo
    syspath = os.path.join(base, path_to_kname(devpath))

    # don't need to try out multiple sysfs paths as path_to_kname handles cciss
    if strict and not os.path.exists(syspath):
        raise OSError("%s had no syspath (%s)" % (devpath, syspath))

    if rpath.startswith('/dev/dm-'):
        parent_info = multipath.mpath_partition_to_mpath_id_and_partnumber(
            rpath)
        if parent_info is not None:
            mpath_id, ptnum = parent_info
            return os.path.realpath('/dev/mapper/' + mpath_id), ptnum

    ptpath = os.path.join(syspath, "partition")
    if not os.path.exists(ptpath):
        return (rpath, None)

    ptnum = util.load_file(ptpath).rstrip()

    # for a partition, real syspath is something like:
    # /sys/devices/pci0000:00/0000:00:04.0/virtio1/block/vda/vda1
    rsyspath = os.path.realpath(syspath)
    disksyspath = os.path.dirname(rsyspath)

    diskmajmin = util.load_file(os.path.join(disksyspath, "dev")).rstrip()
    diskdevpath = os.path.realpath("/dev/block/%s" % diskmajmin)

    # diskdevpath has something like 253:0
    # and udev has put links in /dev/block/253:0 to the device name in /dev/
    return (diskdevpath, ptnum)


def get_sysfs_partitions(device):
    """
    get a list of sysfs paths for partitions under a block device
    accepts input as a device kname, sysfs path, or dev path
    returns empty list if no partitions available
    """
    sysfs_path = sys_block_path(device)
    return [sys_block_path(kname) for kname in os.listdir(sysfs_path)
            if os.path.exists(os.path.join(sysfs_path, kname, 'partition'))]


def get_pardevs_on_blockdevs(devs):
    """
    return a dict of partitions with their info that are on provided devs
    """
    if devs is None:
        devs = []
    devs = [get_dev_name_entry(d)[1] for d in devs]
    found = _lsblock(devs)
    ret = {}
    for short in found:
        if found[short]['device_path'] not in devs:
            ret[short] = found[short]
    return ret


def stop_all_unused_multipath_devices():
    """
    Stop all unused multipath devices.
    """
    multipath = util.which('multipath')

    # Command multipath is not available only when multipath-tools package
    # is not installed. Nothing needs to be done in this case because system
    # doesn't create multipath devices without this package installed and we
    # have nothing to stop.
    if not multipath:
        return

    # Command multipath -F flushes all unused multipath device maps
    cmd = [multipath, '-F']
    try:
        # unless multipath cleared *everything* it will exit with 1
        util.subp(cmd, rcs=[0, 1])
    except util.ProcessExecutionError as e:
        LOG.warn("Failed to stop multipath devices: %s", e)


def rescan_block_devices(devices=None, warn_on_fail=True):
    """
    run 'blockdev --rereadpt' for all block devices not currently mounted
    """
    if not devices:
        unused = get_unused_blockdev_info()
        devices = []
        for devname, data in unused.items():
            if data.get('RM') == "1":
                continue
            if data.get('RO') != "0" or data.get('TYPE') != "disk":
                continue
            devices.append(data['device_path'])

    if not devices:
        LOG.debug("no devices found to rescan")
        return

    # blockdev needs /dev/ parameters, convert if needed
    cmd = ['blockdev', '--rereadpt'] + [dev if dev.startswith('/dev/')
                                        else sysfs_to_devpath(dev)
                                        for dev in devices]
    try:
        util.subp(cmd, capture=True)
    except util.ProcessExecutionError as e:
        if warn_on_fail:
            # FIXME: its less than ideal to swallow this error, but until
            # we fix LP: #1489521 we kind of need to.
            LOG.warn(
                "Error rescanning devices, possibly known issue LP: #1489521")
            # Reformatting the exception output so as to not trigger
            # vmtest scanning for Unexepected errors in install logfile
            LOG.warn("cmd: %s\nstdout:%s\nstderr:%s\nexit_code:%s", e.cmd,
                     e.stdout, e.stderr, e.exit_code)

    udevadm_settle()

    return


def blkid(devs=None, cache=True):
    """
    get data about block devices from blkid and convert to dict
    """
    if devs is None:
        devs = []

    # 14.04 blkid reads undocumented /dev/.blkid.tab
    # man pages mention /run/blkid.tab and /etc/blkid.tab
    if not cache:
        cfiles = ("/run/blkid/blkid.tab", "/dev/.blkid.tab", "/etc/blkid.tab")
        for cachefile in cfiles:
            if os.path.exists(cachefile):
                os.unlink(cachefile)

    cmd = ['blkid', '-o', 'full']
    cmd.extend(devs)
    # blkid output is <device_path>: KEY=VALUE
    # where KEY is TYPE, UUID, PARTUUID, LABEL
    out, err = util.subp(cmd, capture=True)
    data = {}
    for line in out.splitlines():
        curdev, curdata = line.split(":", 1)
        data[curdev] = dict(tok.split('=', 1)
                            for tok in util.shlex_split(curdata))
    return data


def _legacy_detect_multipath(target_mountpoint=None):
    """
    Detect if the operating system has been installed to a multipath device.
    """
    # The obvious way to detect multipath is to use multipath utility which is
    # provided by the multipath-tools package. Unfortunately, multipath-tools
    # package is not available in all ephemeral images hence we can't use it.
    # Another reasonable way to detect multipath is to look for two (or more)
    # devices with the same World Wide Name (WWN) which can be fetched using
    # scsi_id utility. This way doesn't work as well because WWNs are not
    # unique in some cases which leads to false positives which may prevent
    # system from booting (see LP: #1463046 for details).
    # Taking into account all the issues mentioned above, curent implementation
    # detects multipath by looking for a filesystem with the same UUID
    # as the target device. It relies on the fact that all alternative routes
    # to the same disk observe identical partition information including UUID.
    # There are some issues with this approach as well though. We won't detect
    # multipath disk if it doesn't any filesystems.  Good news is that
    # target disk will always have a filesystem because curtin creates them
    # while installing the system.
    rescan_block_devices()
    binfo = blkid(cache=False)
    LOG.debug("legacy_detect_multipath found blkid info: %s", binfo)
    # get_devices_for_mp may return multiple devices by design. It is not yet
    # implemented but it should return multiple devices when installer creates
    # separate disk partitions for / and /boot. We need to do UUID-based
    # multipath detection against each of target devices.
    target_devs = get_devices_for_mp(target_mountpoint)
    LOG.debug("target_devs: %s" % target_devs)
    for devpath, data in binfo.items():
        # We need to figure out UUID of the target device first
        if devpath not in target_devs:
            continue
        # This entry contains information about one of target devices
        target_uuid = data.get('UUID')
        # UUID-based multipath detection won't work if target partition
        # doesn't have UUID assigned
        if not target_uuid:
            LOG.warn("Target partition %s doesn't have UUID assigned",
                     devpath)
            continue
        LOG.debug("%s: %s" % (devpath, data.get('UUID', "")))
        # Iterating over available devices to see if any other device
        # has the same UUID as the target device. If such device exists
        # we probably installed the system to the multipath device.
        for other_devpath, other_data in binfo.items():
            if ((other_data.get('UUID') == target_uuid) and
                    (other_devpath != devpath)):
                return True
    # No other devices have the same UUID as the target devices.
    # We probably installed the system to the non-multipath device.
    return False


def _device_is_multipathed(devpath):
    devpath = os.path.realpath(devpath)
    info = udevadm_info(devpath)
    if multipath.is_mpath_device(devpath, info=info):
        return True
    if multipath.is_mpath_partition(devpath, info=info):
        return True

    if devpath.startswith('/dev/dm-'):
        # check members of composed devices (LVM, dm-crypt)
        if 'DM_LV_NAME' in info:
            volgroup = info.get('DM_VG_NAME')
            if volgroup:
                if any((multipath.is_mpath_member(pv) for pv in
                        lvm.get_pvols_in_volgroup(volgroup))):
                    return True

    elif devpath.startswith('/dev/md'):
        if any((multipath.is_mpath_member(md) for md in
                md_get_devices_list(devpath) + md_get_spares_list(devpath))):
            return True

    result = multipath.is_mpath_member(devpath)
    return result


def _md_get_members_list(devpath, state_check):
    md_dev, _partno = get_blockdev_for_partition(devpath)
    sysfs_md = sys_block_path(md_dev, "md")
    return [
        dev_path(dev[4:]) for dev in os.listdir(sysfs_md)
        if (dev.startswith('dev-') and
            state_check(
                util.load_file(os.path.join(sysfs_md, dev, 'state')).strip()))]


def md_get_spares_list(devpath):
    def state_is_spare(state):
        return (state == 'spare')
    return _md_get_members_list(devpath, state_is_spare)


def md_get_devices_list(devpath):
    def state_is_not_spare(state):
        return (state != 'spare')
    return _md_get_members_list(devpath, state_is_not_spare)


def detect_multipath(target_mountpoint=None):
    if multipath.multipath_supported():
        for device in (os.path.realpath(dev)
                       for (dev, _mp, _vfs, _opts, _freq, _passno)
                       in get_proc_mounts() if dev.startswith('/dev/')):
            if not is_block_device(device):
                # A tmpfs can be mounted with any old junk in the "device"
                # field and unfortunately casper sometimes puts "/dev/shm"
                # there, which is usually a directory. Ignore such cases.
                # (See https://bugs.launchpad.net/bugs/1876626)
                continue
            if _device_is_multipathed(device):
                return device

    return _legacy_detect_multipath(target_mountpoint)


def get_scsi_wwid(device, replace_whitespace=False):
    """
    Issue a call to scsi_id utility to get WWID of the device.
    """
    cmd = ['/lib/udev/scsi_id', '--whitelisted', '--device=%s' % device]
    if replace_whitespace:
        cmd.append('--replace-whitespace')
    try:
        (out, err) = util.subp(cmd, capture=True)
        LOG.debug("scsi_id output raw:\n%s\nerror:\n%s", out, err)
        scsi_wwid = out.rstrip('\n')
        return scsi_wwid
    except util.ProcessExecutionError as e:
        LOG.warn("Failed to get WWID: %s", e)
        return None


def get_multipath_wwids():
    """
    Get WWIDs of all multipath devices available in the system.
    """
    multipath_devices = set()
    multipath_wwids = set()
    devuuids = [(d, i['UUID']) for d, i in blkid().items() if 'UUID' in i]
    # Looking for two disks which contain filesystems with the same UUID.
    for (dev1, uuid1), (dev2, uuid2) in itertools.combinations(devuuids, 2):
        if uuid1 == uuid2:
            multipath_devices.add(get_blockdev_for_partition(dev1)[0])
    for device in multipath_devices:
        wwid = get_scsi_wwid(device)
        # Function get_scsi_wwid() may return None in case of errors or
        # WWID field may be empty for some buggy disk. We don't want to
        # propagate both of these value further to avoid generation of
        # incorrect /etc/multipath/bindings file.
        if wwid:
            multipath_wwids.add(wwid)
    return multipath_wwids


def get_root_device(dev, paths=None):
    """
    Get root partition for specified device, based on presence of any
    paths in the provided paths list:
    """
    if paths is None:
        paths = ["curtin"]
    LOG.debug('Searching for filesystem on %s containing one of: %s',
              dev, paths)
    partitions = get_pardevs_on_blockdevs(dev)
    LOG.debug('Known partitions %s', list(partitions.keys()))
    target = None
    tmp_mount = tempfile.mkdtemp()
    for i in partitions:
        dev_path = partitions[i]['device_path']
        mp = None
        try:
            util.do_mount(dev_path, tmp_mount)
            mp = tmp_mount
            for path in paths:
                fullpath = os.path.join(tmp_mount, path)
                if os.path.isdir(fullpath):
                    target = dev_path
                    LOG.debug("Found path '%s' on device '%s'",
                              path, dev_path)
                    break
        except Exception:
            pass
        finally:
            if mp:
                util.do_umount(mp)

    os.rmdir(tmp_mount)
    if target is None:
        raise ValueError(
            "Did not find any filesystem on %s that contained one of %s" %
            (dev, paths))
    return target


def get_blockdev_sector_size(devpath):
    """
    Get the logical and physical sector size of device at devpath
    Returns a tuple of integer values (logical, physical).
    """
    info = {}
    try:
        info = _lsblock([devpath])
    except util.ProcessExecutionError as e:
        # raise on all errors except device missing error
        if str(e.exit_code) != "32":
            raise
    if info:
        LOG.debug('get_blockdev_sector_size: info:\n%s', util.json_dumps(info))
        # (LP: 1598310) The call to _lsblock() may return multiple results.
        # If it does, then search for a result with the correct device path.
        # If no such device is found among the results, then fall back to
        # previous behavior, which was taking the first of the results
        assert len(info) > 0
        for (k, v) in info.items():
            if v.get('device_path') == devpath:
                parent = k
                break
        else:
            parent = list(info.keys())[0]
        logical = info[parent]['LOG-SEC']
        physical = info[parent]['PHY-SEC']
    else:
        sys_path = sys_block_path(devpath)
        logical = util.load_file(
            os.path.join(sys_path, 'queue/logical_block_size'))
        physical = util.load_file(
            os.path.join(sys_path, 'queue/hw_sector_size'))

    LOG.debug('get_blockdev_sector_size: (log=%s, phys=%s)', logical, physical)
    return (int(logical), int(physical))


def read_sys_block_size_bytes(device):
    """ /sys/class/block/<device>/size and return integer value in bytes"""
    device_dir = os.path.join('/sys/class/block', os.path.basename(device))
    blockdev_size = os.path.join(device_dir, 'size')
    with open(blockdev_size) as d:
        size = int(d.read().strip()) * SECTOR_SIZE_BYTES
    return size


def get_volume_id(path):
    """
    Get identifier of device with given path. This address uniquely identifies
    the device and remains consistant across reboots.
    """
    ids = blkid([path])[path]
    for key in ("UUID", "PARTUUID", "PTUUID"):
        if key in ids:
            return (key, ids[key])
    return (None, '')


def get_mountpoints():
    """
    Returns a list of all mountpoints where filesystems are currently mounted.
    """
    info = _lsblock()
    proc_mounts = [mp for (dev, mp, vfs, opts, freq, passno) in
                   get_proc_mounts()]
    lsblock_mounts = list(i.get("MOUNTPOINT") for name, i in info.items() if
                          i.get("MOUNTPOINT") is not None and
                          i.get("MOUNTPOINT") != "")

    return list(set(proc_mounts + lsblock_mounts))


def get_proc_mounts():
    """
    Returns a list of tuples for each entry in /proc/mounts
    """
    mounts = []
    with open("/proc/mounts", "r") as fp:
        for line in fp:
            try:
                (dev, mp, vfs, opts, freq, passno) = \
                    line.strip().split(None, 5)
                mounts.append((dev, mp, vfs, opts, freq, passno))
            except ValueError:
                continue
    return mounts


def _get_dev_disk_by_prefix(prefix):
    """
    Construct a dictionary mapping devname to disk/<prefix> paths

    :returns: Dictionary populated by examining /dev/disk/<prefix>/*

    {
     '/dev/sda': '/dev/disk/<prefix>/virtio-aaaa',
     '/dev/sda1': '/dev/disk/<prefix>/virtio-aaaa-part1',
    }
    """
    if not os.path.exists(prefix):
        return {}
    return {
        os.path.realpath(bypfx): bypfx
        for bypfx in [os.path.join(prefix, path)
                      for path in os.listdir(prefix)]
    }


def get_dev_disk_byid():
    """
    Construct a dictionary mapping devname to disk/by-id paths

    :returns: Dictionary populated by examining /dev/disk/by-id/*

    {
     '/dev/sda': '/dev/disk/by-id/virtio-aaaa',
     '/dev/sda1': '/dev/disk/by-id/virtio-aaaa-part1',
    }
    """
    return _get_dev_disk_by_prefix('/dev/disk/by-id')


def disk_to_byid_path(kname):
    """"
    Return a /dev/disk/by-id path to kname if present.
    """

    mapping = get_dev_disk_byid()
    return mapping.get(dev_path(kname))


def disk_to_bypath_path(kname):
    """"
    Return a /dev/disk/by-path path to kname if present.
    """

    mapping = _get_dev_disk_by_prefix('/dev/disk/by-path')
    return mapping.get(dev_path(kname))


def get_device_mapper_links(devpath, first=False):
    """ Return the best devlink to device at devpath. """
    info = udevadm_info(devpath)
    if 'DEVLINKS' not in info:
        raise ValueError('Device %s does not have device symlinks' % devpath)
    devlinks = [devlink for devlink in sorted(info['DEVLINKS']) if devlink]
    if not devlinks:
        raise ValueError('Unexpected DEVLINKS list contained empty values')

    if first:
        return devlinks[0]

    return devlinks


def lookup_disk(serial):
    """
    Search for a disk by its serial number using /dev/disk/by-id/
    """
    # Get all volumes in /dev/disk/by-id/ containing the serial string. The
    # string specified can be either in the short or long serial format
    # hack, some serials have spaces, udev usually converts ' ' -> '_'
    serial_udev = serial.replace(' ', '_')
    LOG.info('Processing serial %s via udev to %s', serial, serial_udev)

    disks = list(filter(lambda x: serial_udev in x,
                        os.listdir("/dev/disk/by-id/")))
    if not disks or len(disks) < 1:
        raise ValueError("no disk with serial '%s' found" % serial_udev)

    # Sort by length and take the shortest path name, as the longer path names
    # will be the partitions on the disk. Then use os.path.realpath to
    # determine the path to the block device in /dev/
    disks.sort(key=lambda x: len(x))
    LOG.debug('lookup_disks found: %s', disks)
    path = os.path.realpath("/dev/disk/by-id/%s" % disks[0])
    # /dev/dm-X
    if multipath.is_mpath_device(path):
        info = udevadm_info(path)
        path = os.path.join('/dev/mapper', info['DM_NAME'])
    # /dev/sdX
    elif multipath.is_mpath_member(path):
        mp_name = multipath.find_mpath_id_by_path(path)
        path = os.path.join('/dev/mapper', mp_name)

    if not os.path.exists(path):
        raise ValueError("path '%s' to block device for disk with serial '%s' \
            does not exist" % (path, serial_udev))
    LOG.debug('block.lookup_disk() returning path %s', path)
    return path


def lookup_dasd(bus_id):
    """
    Search for a dasd by its bus_id.

    :param bus_id: s390x ccw bus_id 0.0.NNNN specifying the dasd
    :returns: dasd kernel device path (/dev/dasda)
    """

    LOG.info('Processing ccw bus_id %s', bus_id)
    sys_ccw_dev = '/sys/bus/ccw/devices/%s/block' % bus_id
    if not os.path.exists(sys_ccw_dev):
        raise ValueError('Failed to find a block device at %s' % sys_ccw_dev)

    dasds = os.listdir(sys_ccw_dev)
    if not dasds or len(dasds) < 1:
        raise ValueError("no dasd with device_id '%s' found" % bus_id)

    path = '/dev/%s' % dasds[0]
    if not os.path.exists(path):
        raise ValueError("path '%s' to block device for dasd with bus_id '%s' \
            does not exist" % (path, bus_id))
    return path


def sysfs_partition_data(blockdev=None, sysfs_path=None):
    # given block device or sysfs_path, return a list of tuples
    # of (kernel_name, number, offset, size)
    if blockdev:
        blockdev = os.path.normpath(blockdev)
        sysfs_path = sys_block_path(blockdev)
    elif sysfs_path:
        # use normpath to ensure that paths with trailing slash work
        sysfs_path = os.path.normpath(sysfs_path)
        blockdev = os.path.join('/dev', os.path.basename(sysfs_path))
    else:
        raise ValueError("Blockdev and sysfs_path cannot both be None")

    sysfs_prefix = sysfs_path
    (parent, partnum) = get_blockdev_for_partition(blockdev)
    if partnum:
        sysfs_prefix = sys_block_path(parent)
        partnum = int(partnum)

    keys = {'partition', 'start', 'size'}
    ptdata = []
    for part_sysfs in get_sysfs_partitions(sysfs_prefix):
        data = {}
        for sfile in keys:
            dfile = os.path.join(part_sysfs, sfile)
            if not os.path.isfile(dfile):
                continue
            data[sfile] = int(util.load_file(dfile))
        if partnum is None or data['partition'] == partnum:
            if data.keys() == keys:
                ptdata.append((
                    path_to_kname(part_sysfs),
                    data['partition'],
                    data['start'] * SECTOR_SIZE_BYTES,
                    data['size'] * SECTOR_SIZE_BYTES,
                    ))
            else:
                LOG.debug(
                    "sysfs_partition_data: "
                    f"skipping {part_sysfs} - incomplete sysfs read"
                )

    return ptdata


def get_part_table_type(device):
    """
    check the type of partition table present on the specified device
    returns None if no ptable was present or device could not be read
    """
    # it is neccessary to look for the gpt signature first, then the dos
    # signature, because a gpt formatted disk usually has a valid mbr to
    # protect the disk from being modified by older partitioning tools
    return ('gpt' if check_efi_signature(device) else
            'dos' if check_dos_signature(device) else
            'vtoc' if check_vtoc_signature(device) else None)


def check_dos_signature(device):
    """
    check if there is a dos partition table signature present on device
    """
    # the last 2 bytes of a dos partition table have the signature with the
    # value 0xAA55. the dos partition table is always 0x200 bytes long, even if
    # the underlying disk uses a larger logical block size, so the start of
    # this signature must be at 0x1fe
    # https://en.wikipedia.org/wiki/Master_boot_record#Sector_layout
    devname = dev_path(path_to_kname(device))
    if not is_block_device(devname):
        return False
    file_size = util.file_size(devname)
    if file_size < 0x200:
        return False
    signature = util.load_file(devname, decode=False, read_len=2, offset=0x1fe)
    return signature == b'\x55\xAA'


def check_efi_signature(device):
    """
    check if there is a gpt partition table signature present on device
    """
    # the gpt partition table header is always on lba 1, regardless of the
    # logical block size used by the underlying disk. therefore, a static
    # offset cannot be used, the offset to the start of the table header is
    # always the sector size of the disk
    # the start of the gpt partition table header shoult have the signaure
    # 'EFI PART'.
    # https://en.wikipedia.org/wiki/GUID_Partition_Table
    devname = dev_path(path_to_kname(device))
    sector_size = get_blockdev_sector_size(devname)[0]
    return (is_block_device(devname) and
            util.file_size(devname) >= 2 * sector_size and
            (util.load_file(devname, decode=False, read_len=8,
                            offset=sector_size) == b'EFI PART'))


def check_vtoc_signature(device):
    """ check if the specified device has a vtoc partition table. """
    devname = dev_path(path_to_kname(device))
    try:
        util.subp(['fdasd', '--table', devname])
    except util.ProcessExecutionError:
        return False

    return True


def is_extended_partition(device):
    """
    check if the specified device path is a dos extended partition
    """
    # an extended partition must be on a dos disk, must be a partition, must be
    # within the first 4 partitions and will have a valid dos signature,
    # because the format of the extended partition matches that of a real mbr
    (parent_dev, part_number) = get_blockdev_for_partition(device)
    if (get_part_table_type(parent_dev) in ['dos', 'msdos'] and
            part_number is not None and int(part_number) <= 4):
        try:
            return check_dos_signature(device)
        except OSError as ose:
            # Some older series have the extended partition block device but
            # return ENXIO when attempting to read it.  Make a best guess from
            # the parent_dev.
            if ose.errno == errno.ENXIO:
                return check_dos_signature(parent_dev)
            else:
                raise
    else:
        return False


def is_zfs_member(device):
    """
    check if the specified device path is a zfs member
    """
    info = _lsblock()
    kname = path_to_kname(device)
    if kname in info and info[kname].get('FSTYPE') == 'zfs_member':
        return True

    return False


def is_online(device):
    """  check if device is online """
    sys_path = sys_block_path(device)
    device_size = util.load_file(
        os.path.join(sys_path, 'size'))
    # a block device should have non-zero size to be usable
    return int(device_size) > 0


def zkey_supported(strict=True):
    """ Return True if zkey cmd present and can generate keys, else False."""
    LOG.debug('Checking if zkey encryption is supported...')
    try:
        util.load_kernel_module('pkey')
    except util.ProcessExecutionError as err:
        msg = "Failed to load 'pkey' kernel module"
        LOG.error(msg + ": %s" % err) if strict else LOG.warning(msg)
        return False

    try:
        with tempfile.NamedTemporaryFile() as tf:
            util.subp(['zkey', 'generate', tf.name], capture=True)
            LOG.debug('zkey encryption supported.')
            return True
    except util.ProcessExecutionError as err:
        msg = "zkey not supported"
        LOG.error(msg + ": %s" % err) if strict else LOG.warning(msg)

    return False


@contextmanager
def exclusive_open(path, exclusive=True):
    """
    Obtain an exclusive file-handle to the file/device specified unless
    caller specifics exclusive=False.
    """
    mode = 'rb+'
    fd = None
    if not os.path.exists(path):
        raise ValueError("No such file at path: %s" % path)

    flags = os.O_RDWR
    if exclusive:
        flags += os.O_EXCL
    try:
        fd = os.open(path, flags)
        fd_needs_closing = True
        try:
            with os.fdopen(fd, mode) as fo:
                yield fo
            fd_needs_closing = False
        except OSError:
            LOG.exception("Failed to create file-object from fd")
            raise
        finally:
            # python2 leaves fd open if there os.fdopen fails
            if fd_needs_closing and sys.version_info.major == 2:
                os.close(fd)
    except OSError as exc:
        LOG.error("Failed to exclusively open path: %s", path)
        holders = get_holders(path)
        LOG.error('Device holders with exclusive access: %s', holders)
        mount_points = util.list_device_mounts(path)
        LOG.error('Device mounts: %s', mount_points)
        fusers = util.fuser_mount(path)
        LOG.error('Possible users of %s:\n%s', path, fusers)
        if exclusive and exc.errno == errno.EBUSY:
            raise NotExclusiveError from exc
        else:
            raise


def wipe_file(path, reader=None, buflen=4 * 1024 * 1024, exclusive=True):
    """
    wipe the existing file at path.
    if reader is provided, it will be called as a 'reader(buflen)'
    to provide data for each write.  Otherwise, zeros are used.
    writes will be done in size of buflen.
    """
    if reader:
        readfunc = reader
    else:
        buf = buflen * b'\0'

        def readfunc(size):
            return buf

    size = util.file_size(path)
    LOG.debug("%s is %s bytes. wiping with buflen=%s",
              path, size, buflen)

    with exclusive_open(path, exclusive=exclusive) as fp:
        while True:
            pbuf = readfunc(buflen)
            pos = fp.tell()
            if len(pbuf) != buflen and len(pbuf) + pos < size:
                raise ValueError(
                    "short read on reader got %d expected %d after %d" %
                    (len(pbuf), buflen, pos))

            if pos + buflen >= size:
                fp.write(pbuf[0:size-pos])
                break
            else:
                fp.write(pbuf)


def quick_zero(path, partitions=True, exclusive=True):
    """
    Call wipefs -a -f on path, then zero 1M at front, 1M at end.
    If this is a block device and partitions is true, then
    zero 1M at front and end of each partition before zeroing path.
    """
    buflen = 1024
    count = 1024
    zero_size = buflen * count
    offsets = [0, -zero_size]
    is_block = is_block_device(path)
    if not (is_block or os.path.isfile(path)):
        raise ValueError("%s: not an existing file or block device" % path)

    pt_names = []
    if partitions and is_block:
        ptdata = sysfs_partition_data(path)
        for kname, ptnum, start, size in ptdata:
            pt_names.append((dev_path(kname), kname, ptnum))
        pt_names.reverse()

    for (pt, kname, ptnum) in pt_names:
        LOG.debug('Wiping path: dev:%s kname:%s partnum:%s',
                  pt, kname, ptnum)
        quick_zero(pt, partitions=False)

    util.subp(['wipefs', '--all', '--force', path])

    LOG.debug("wiping 1M on %s at offsets %s", path, offsets)
    util.not_exclusive_retry(
            zero_file_at_offsets,
            path, offsets, buflen=buflen, count=count, exclusive=exclusive)


def zero_file_at_offsets(path, offsets, buflen=1024, count=1024, strict=False,
                         exclusive=True):
    """
    write zeros to file at specified offsets
    """
    bmsg = "{path} (size={size}): "
    m_short = bmsg + "{tot} bytes from {offset} > size."
    m_badoff = bmsg + "invalid offset {offset}."
    if not strict:
        m_short += " Shortened to {wsize} bytes."
        m_badoff += " Skipping."

    buf = b'\0' * buflen
    tot = buflen * count
    msg_vals = {'path': path, 'tot': buflen * count}

    # allow caller to control if we require exclusive open
    with exclusive_open(path, exclusive=exclusive) as fp:
        # get the size by seeking to end.
        fp.seek(0, 2)
        size = fp.tell()
        msg_vals['size'] = size

        for offset in offsets:
            if offset < 0:
                pos = size + offset
            else:
                pos = offset
            msg_vals['offset'] = offset
            msg_vals['pos'] = pos
            if pos > size or pos < 0:
                if strict:
                    raise ValueError(m_badoff.format(**msg_vals))
                else:
                    LOG.debug(m_badoff.format(**msg_vals))
                    continue

            msg_vals['wsize'] = size - pos
            if pos + tot > size:
                if strict:
                    raise ValueError(m_short.format(**msg_vals))
                else:
                    LOG.debug(m_short.format(**msg_vals))
            fp.seek(pos)
            for i in range(count):
                pos = fp.tell()
                if pos + buflen > size:
                    fp.write(buf[0:size-pos])
                else:
                    fp.write(buf)


def wipe_volume(path, mode="superblock", exclusive=True):
    """wipe a volume/block device

    :param path: a path to a block device
    :param mode: how to wipe it.
       pvremove: wipe a lvm physical volume
       zero: write zeros to the entire volume
       random: write random data (/dev/urandom) to the entire volume
       superblock: zero the beginning and the end of the volume
       superblock-recursive: zero the beginning of the volume, the end of the
                    volume and beginning and end of any partitions that are
                    known to be on this device.
    :param exclusive: boolean to control how path is opened
    """
    if mode == "pvremove":
        # We need to use --force --force in case it's already in a volgroup and
        # pvremove doesn't want to remove it

        # If pvremove is run and there is no label on the system,
        # then it exits with 5. That is also okay, because we might be
        # wiping something that is already blank
        util.subp(['pvremove', '--force', '--force', '--yes', path],
                  rcs=[0, 5], capture=True)
        lvm.lvm_scan()
    elif mode == "zero":
        wipe_file(path, exclusive=exclusive)
    elif mode == "random":
        with open("/dev/urandom", "rb") as reader:
            wipe_file(path, reader=reader.read, exclusive=exclusive)
    elif mode == "superblock":
        quick_zero(path, partitions=False, exclusive=exclusive)
    elif mode == "superblock-recursive":
        quick_zero(path, partitions=True, exclusive=exclusive)
    else:
        raise ValueError("wipe mode %s not supported" % mode)


def get_supported_filesystems():
    """ Return a list of filesystems that the kernel currently supports
        as read from /proc/filesystems.

        Raises RuntimeError if /proc/filesystems does not exist.
    """
    proc_fs = "/proc/filesystems"
    if not os.path.exists(proc_fs):
        raise RuntimeError("Unable to read 'filesystems' from %s" % proc_fs)

    return [line.split('\t')[1].strip()
            for line in util.load_file(proc_fs).splitlines()]


def _discover_get_probert_data():
    try:
        LOG.debug('Importing probert prober')
        from probert import prober
    except Exception:
        LOG.error('Failed to import probert, discover disabled')
        return {}

    probe = prober.Prober()
    LOG.debug('Probing system for storage devices')
    probe.probe_storage()
    return probe.get_results()


def discover():
    probe_data = _discover_get_probert_data()
    if 'storage' not in probe_data:
        raise ValueError('Probing storage failed')

    LOG.debug('Extracting storage config from discovered devices')
    try:
        return storage_config.extract_storage_config(probe_data.get('storage'))
    except ImportError as e:
        LOG.exception(e)

    return {}


def get_resize_fstypes():
    from curtin.commands.block_meta_v2 import resizers
    return {fstype for fstype in resizers.keys()}


# vi: ts=4 expandtab syntax=python
