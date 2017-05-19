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

from contextlib import contextmanager
import errno
import itertools
import os
import shlex
import stat
import sys
import tempfile

from curtin import util
from curtin.block import lvm
from curtin.log import LOG
from curtin.udev import udevadm_settle


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
        return devname
    else:
        return '/dev/' + devname


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
    for dev_type in ['nvme', 'mmcblk', 'cciss', 'mpath', 'dm', 'md']:
        if disk_kname.startswith(dev_type):
            partition_number = "p%s" % partition_number
            break
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
    (parent, partnum) = get_blockdev_for_partition(devname)
    if partnum:
        toks.append(path_to_kname(parent))

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


def _shlex_split(str_in):
    # shlex.split takes a string
    # but in python2 if input here is a unicode, encode it to a string.
    # http://stackoverflow.com/questions/2365411/
    #     python-convert-unicode-to-ascii-without-errors
    if sys.version_info.major == 2:
        try:
            if isinstance(str_in, unicode):
                str_in = str_in.encode('utf-8')
        except NameError:
            pass

        return shlex.split(str_in)
    else:
        return shlex.split(str_in)


def _lsblock_pairs_to_dict(lines):
    """
    parse lsblock output and convert to dict
    """
    ret = {}
    for line in lines.splitlines():
        toks = _shlex_split(line)
        cur = {}
        for tok in toks:
            k, v = tok.split("=", 1)
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


def get_blockdev_for_partition(devpath):
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
    if not os.path.exists(syspath):
        raise OSError("%s had no syspath (%s)" % (devpath, syspath))

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


def rescan_block_devices():
    """
    run 'blockdev --rereadpt' for all block devices not currently mounted
    """
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

    cmd = ['blockdev', '--rereadpt'] + devices
    try:
        util.subp(cmd, capture=True)
    except util.ProcessExecutionError as e:
        # FIXME: its less than ideal to swallow this error, but until
        # we fix LP: #1489521 we kind of need to.
        LOG.warn("Error rescanning devices, possibly known issue LP: #1489521")
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
    # blkid output is <device_path>: KEY=VALUE
    # where KEY is TYPE, UUID, PARTUUID, LABEL
    out, err = util.subp(cmd, capture=True)
    data = {}
    for line in out.splitlines():
        curdev, curdata = line.split(":", 1)
        data[curdev] = dict(tok.split('=', 1)
                            for tok in _shlex_split(curdata))
    return data


def detect_multipath(target_mountpoint):
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
    LOG.debug("detect_multipath found blkid info: %s", binfo)
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
    info = _lsblock([devpath])
    LOG.debug('get_blockdev_sector_size: info:\n%s' % util.json_dumps(info))
    # (LP: 1598310) The call to _lsblock() may return multiple results.
    # If it does, then search for a result with the correct device path.
    # If no such device is found among the results, then fall back to previous
    # behavior, which was taking the first of the results
    assert len(info) > 0
    for (k, v) in info.items():
        if v.get('device_path') == devpath:
            parent = k
            break
    else:
        parent = list(info.keys())[0]

    return (int(info[parent]['LOG-SEC']), int(info[parent]['PHY-SEC']))


def get_volume_uuid(path):
    """
    Get uuid of disk with given path. This address uniquely identifies
    the device and remains consistant across reboots
    """
    (out, _err) = util.subp(["blkid", "-o", "export", path], capture=True)
    for line in out.splitlines():
        if "UUID" in line:
            return line.split('=')[-1]
    return ''


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
    path = os.path.realpath("/dev/disk/by-id/%s" % disks[0])

    if not os.path.exists(path):
        raise ValueError("path '%s' to block device for disk with serial '%s' \
            does not exist" % (path, serial_udev))
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

    # queue property is only on parent devices, ie, we can't read
    # /sys/class/block/vda/vda1/queue/* as queue is only on the
    # parent device
    sysfs_prefix = sysfs_path
    (parent, partnum) = get_blockdev_for_partition(blockdev)
    if partnum:
        sysfs_prefix = sys_block_path(parent)
        partnum = int(partnum)

    block_size = int(util.load_file(os.path.join(
        sysfs_prefix, 'queue/logical_block_size')))
    unit = block_size

    ptdata = []
    for part_sysfs in get_sysfs_partitions(sysfs_prefix):
        data = {}
        for sfile in ('partition', 'start', 'size'):
            dfile = os.path.join(part_sysfs, sfile)
            if not os.path.isfile(dfile):
                continue
            data[sfile] = int(util.load_file(dfile))
        if partnum is None or data['partition'] == partnum:
            ptdata.append((path_to_kname(part_sysfs), data['partition'],
                           data['start'] * unit, data['size'] * unit,))

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
            'dos' if check_dos_signature(device) else None)


def check_dos_signature(device):
    """
    check if there is a dos partition table signature present on device
    """
    # the last 2 bytes of a dos partition table have the signature with the
    # value 0xAA55. the dos partition table is always 0x200 bytes long, even if
    # the underlying disk uses a larger logical block size, so the start of
    # this signature must be at 0x1fe
    # https://en.wikipedia.org/wiki/Master_boot_record#Sector_layout
    return (is_block_device(device) and util.file_size(device) >= 0x200 and
            (util.load_file(device, decode=False, read_len=2, offset=0x1fe) ==
             b'\x55\xAA'))


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
    sector_size = get_blockdev_sector_size(device)[0]
    return (is_block_device(device) and
            util.file_size(device) >= 2 * sector_size and
            (util.load_file(device, decode=False, read_len=8,
                            offset=sector_size) == b'EFI PART'))


def is_extended_partition(device):
    """
    check if the specified device path is a dos extended partition
    """
    # an extended partition must be on a dos disk, must be a partition, must be
    # within the first 4 partitions and will have a valid dos signature,
    # because the format of the extended partition matches that of a real mbr
    (parent_dev, part_number) = get_blockdev_for_partition(device)
    return (get_part_table_type(parent_dev) in ['dos', 'msdos'] and
            part_number is not None and int(part_number) <= 4 and
            check_dos_signature(device))


@contextmanager
def exclusive_open(path):
    """
    Obtain an exclusive file-handle to the file/device specified
    """
    mode = 'rb+'
    fd = None
    if not os.path.exists(path):
        raise ValueError("No such file at path: %s" % path)

    try:
        fd = os.open(path, os.O_RDWR | os.O_EXCL)
        try:
            fd_needs_closing = True
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
    except OSError:
        LOG.exception("Failed to exclusively open path: %s", path)
        holders = get_holders(path)
        LOG.error('Device holders with exclusive access: %s', holders)
        mount_points = util.list_device_mounts(path)
        LOG.error('Device mounts: %s', mount_points)
        raise


def wipe_file(path, reader=None, buflen=4 * 1024 * 1024):
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

    with exclusive_open(path) as fp:
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


def quick_zero(path, partitions=True):
    """
    zero 1M at front, 1M at end, and 1M at front
    if this is a block device and partitions is true, then
    zero 1M at front and end of each partition.
    """
    buflen = 1024
    count = 1024
    zero_size = buflen * count
    offsets = [0, -zero_size]
    is_block = is_block_device(path)
    if not (is_block or os.path.isfile(path)):
        raise ValueError("%s: not an existing file or block device", path)

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

    LOG.debug("wiping 1M on %s at offsets %s", path, offsets)
    return zero_file_at_offsets(path, offsets, buflen=buflen, count=count)


def zero_file_at_offsets(path, offsets, buflen=1024, count=1024, strict=False):
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

    with exclusive_open(path) as fp:
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


def wipe_volume(path, mode="superblock"):
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
        wipe_file(path)
    elif mode == "random":
        with open("/dev/urandom", "rb") as reader:
            wipe_file(path, reader=reader.read)
    elif mode == "superblock":
        quick_zero(path, partitions=False)
    elif mode == "superblock-recursive":
        quick_zero(path, partitions=True)
    else:
        raise ValueError("wipe mode %s not supported" % mode)

# vi: ts=4 expandtab syntax=python
