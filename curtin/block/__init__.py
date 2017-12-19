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

import errno
import os
import stat
import shlex
import tempfile

from curtin import util


def get_dev_name_entry(devname):
    bname = os.path.basename(devname)
    return (bname, "/dev/" + bname)


def is_valid_device(devname):
    devent = get_dev_name_entry(devname)[1]
    try:
        return stat.S_ISBLK(os.stat(devent).st_mode)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    return False


def _lsblock_pairs_to_dict(lines, key="NAME"):
    ret = {}
    for line in lines.splitlines():
        toks = shlex.split(line)
        cur = {}
        for tok in toks:
            k, v = tok.split("=", 1)
            cur[k] = v
        cur['device_path'] = get_dev_name_entry(cur['NAME'])[1]
        ret[cur['NAME']] = cur
    return ret


def _lsblock(args=None):
    # lsblk  --help | sed -n '/Available/,/^$/p' |
    #     sed -e 1d -e '$d' -e 's,^[ ]\+,,' -e 's, .*,,' | sort
    keys = ['ALIGNMENT', 'DISC-ALN', 'DISC-GRAN', 'DISC-MAX', 'DISC-ZERO',
            'FSTYPE', 'GROUP', 'KNAME', 'LABEL', 'LOG-SEC', 'MAJ:MIN',
            'MIN-IO', 'MODE', 'MODEL', 'MOUNTPOINT', 'NAME', 'OPT-IO', 'OWNER',
            'PHY-SEC', 'RM', 'RO', 'ROTA', 'RQ-SIZE', 'SCHED', 'SIZE', 'STATE',
            'TYPE', 'UUID']
    if args is None:
        args = []
    # in order to avoid a very odd error with '-o' and all output fields above
    # we just drop one.  doesn't really matter which one.
    keys.remove('SCHED')
    basecmd = ['lsblk', '--noheadings', '--bytes', '--pairs',
               '--out=' + ','.join(keys)]
    (out, _err) = util.subp(basecmd + list(args), capture=True)
    return _lsblock_pairs_to_dict(out)


def get_unused_blockdev_info():
    # return a list of unused block devices. These are devices that
    # do not have anything mounted on them.

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
    # return a list of devices (full paths) used by the provided mountpoint
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
    with open("/proc/mounts", "r") as fp:
        for line in fp:
            try:
                (dev, mp, vfs, opts, freq, passno) = line.split(None, 5)
                if mp == mountpoint:
                    return [os.path.realpath(dev)]
            except ValueError:
                continue
    return []


def get_installable_blockdevs():
    good = []
    unused = get_unused_blockdev_info()
    for devname, data in unused.iteritems():
        if data.get('RO') == "0" and data.get('TYPE') == "disk":
            good.append(devname)
    return good


def get_blockdev_for_partition(devpath):
    # convert an entry in /dev/ to parent disk and partition number
    # if devpath is a block device and not a partition, return (devpath, None)

    # input of /dev/vdb or /dev/disk/by-label/foo
    # rpath is hopefully a real-ish path in /dev (vda, sdb..)
    rpath = os.path.realpath(devpath)

    bname = os.path.basename(rpath)
    syspath = "/sys/class/block/%s" % bname

    if not os.path.exists(syspath):
        raise ValueError("%s had no syspath (%s)" % (devpath, syspath))

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


def get_pardevs_on_blockdevs(devs):
    # return a dict of partitions with their info that are on provided devs
    if devs is None:
        devs = []
    devs = [get_dev_name_entry(d)[1] for d in devs]
    found = _lsblock(devs)
    ret = {}
    for short in found:
        if found[short]['device_path'] not in devs:
            ret[short] = found[short]
    return ret


def get_root_device(dev, fpath="curtin"):
    """
    Get root partition for specified device, based on presence of /curtin.
    """
    partitions = get_pardevs_on_blockdevs(dev)
    target = None
    tmp_mount = tempfile.mkdtemp()
    for i in partitions:
        dev_path = partitions[i]['device_path']
        mp = None
        try:
            util.do_mount(dev_path, tmp_mount)
            mp = tmp_mount
            curtin_dir = os.path.join(tmp_mount, fpath)
            if os.path.isdir(curtin_dir):
                target = dev_path
                break
        except:
            pass
        finally:
            if mp:
                util.do_umount(mp)

    os.rmdir(tmp_mount)

    if target is None:
        raise ValueError("Could not find root device")
    return target


# vi: ts=4 expandtab syntax=python
