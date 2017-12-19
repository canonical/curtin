#   Copyright (C) 2015 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
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


# This module wraps calls to the mdadm utility for examing Linux SoftRAID
# virtual devices.  Functions prefixed with 'mdadm_' involve executing
# the 'mdadm' command in a subprocess.  The remaining functions handle
# manipulation of the mdadm output.


import os
import re
import shlex
from subprocess import CalledProcessError

from curtin.block import (dev_short, dev_path, is_valid_device, sys_block_path)
from curtin import util
from curtin.log import LOG

NOSPARE_RAID_LEVELS = [
    'linear', 'raid0', '0', 0,
]

SPARE_RAID_LEVELS = [
    'raid1', 'stripe', 'mirror', '1', 1,
    'raid4', '4', 4,
    'raid5', '5', 5,
    'raid6', '6', 6,
    'raid10', '10', 10,
]

VALID_RAID_LEVELS = NOSPARE_RAID_LEVELS + SPARE_RAID_LEVELS

#  https://www.kernel.org/doc/Documentation/md.txt
'''
     clear
         No devices, no size, no level
         Writing is equivalent to STOP_ARRAY ioctl
     inactive
         May have some settings, but array is not active
            all IO results in error
         When written, doesn't tear down array, but just stops it
     suspended (not supported yet)
         All IO requests will block. The array can be reconfigured.
         Writing this, if accepted, will block until array is quiessent
     readonly
         no resync can happen.  no superblocks get written.
         write requests fail
     read-auto
         like readonly, but behaves like 'clean' on a write request.

     clean - no pending writes, but otherwise active.
         When written to inactive array, starts without resync
         If a write request arrives then
           if metadata is known, mark 'dirty' and switch to 'active'.
           if not known, block and switch to write-pending
         If written to an active array that has pending writes, then fails.
     active
         fully active: IO and resync can be happening.
         When written to inactive array, starts with resync

     write-pending
         clean, but writes are blocked waiting for 'active' to be written.

     active-idle
       like active, but no writes have been seen for a while (safe_mode_delay).
'''

ERROR_RAID_STATES = [
    'clear',
    'inactive',
    'suspended',
]

READONLY_RAID_STATES = [
    'readonly',
]

READWRITE_RAID_STATES = [
    'read-auto',
    'clean',
    'active',
    'active-idle',
    'write-pending',
]

VALID_RAID_ARRAY_STATES = (
    ERROR_RAID_STATES +
    READONLY_RAID_STATES +
    READWRITE_RAID_STATES
)

# need a on-import check of version and set the value for later reference
''' mdadm version < 3.3 doesn't include enough info when using --export
    and we must use --detail and parse out information.  This method
    checks the mdadm version and will return True if we can use --export
    for key=value list with enough info, false if version is less than
'''
MDADM_USE_EXPORT = util.lsb_release()['codename'] not in ['precise', 'trusty']

#
# mdadm executors
#


def mdadm_assemble(md_devname=None, devices=[], spares=[], scan=False):
    # md_devname is a /dev/XXXX
    # devices is non-empty list of /dev/xxx
    # if spares is non-empt list append of /dev/xxx
    cmd = ["mdadm", "--assemble"]
    if scan:
        cmd += ['--scan']
    else:
        valid_mdname(md_devname)
        cmd += [md_devname, "--run"] + devices
        if spares:
            cmd += spares

    util.subp(cmd, capture=True, rcs=[0, 1, 2])
    util.subp(["udevadm", "settle"])


def mdadm_create(md_devname, raidlevel, devices, spares=None, md_name=""):
    LOG.debug('mdadm_create: ' +
              'md_name=%s raidlevel=%s ' % (md_devname, raidlevel) +
              ' devices=%s spares=%s name=%s' % (devices, spares, md_name))

    assert_valid_devpath(md_devname)

    if raidlevel not in VALID_RAID_LEVELS:
        raise ValueError('Invalid raidlevel: [{}]'.format(raidlevel))

    min_devices = md_minimum_devices(raidlevel)
    if len(devices) < min_devices:
        err = 'Not enough devices for raidlevel: ' + str(raidlevel)
        err += ' minimum devices needed: ' + str(min_devices)
        raise ValueError(err)

    if spares and raidlevel not in SPARE_RAID_LEVELS:
        err = ('Raidlevel does not support spare devices: ' + str(raidlevel))
        raise ValueError(err)

    (hostname, _err) = util.subp(["hostname", "-s"], rcs=[0], capture=True)

    cmd = ["mdadm", "--create", md_devname, "--run",
           "--homehost=%s" % hostname.strip(),
           "--level=%s" % raidlevel,
           "--raid-devices=%s" % len(devices)]
    if md_name:
        cmd.append("--name=%s" % md_name)

    for device in devices:
        # Zero out device superblock just in case device has been used for raid
        # before, as this will cause many issues
        util.subp(["mdadm", "--zero-superblock", device], capture=True)
        cmd.append(device)

    if spares:
        cmd.append("--spare-devices=%s" % len(spares))
        for device in spares:
            util.subp(["mdadm", "--zero-superblock", device], capture=True)
            cmd.append(device)

    # Create the raid device
    util.subp(["udevadm", "settle"])
    util.subp(["udevadm", "control", "--stop-exec-queue"])
    try:
        util.subp(cmd, capture=True)
    except util.ProcessExecutionError:
        # frequent issues by modules being missing (LP: #1519470) - add debug
        LOG.debug('mdadm_create failed - extra debug regarding md modules')
        (out, _err) = util.subp(["lsmod"], capture=True)
        if not _err:
            LOG.debug('modules loaded: \n%s' % out)
        raidmodpath = '/lib/modules/%s/kernel/drivers/md' % os.uname()[2]
        (out, _err) = util.subp(["find", raidmodpath],
                                rcs=[0, 1], capture=True)
        if out:
            LOG.debug('available md modules: \n%s' % out)
        else:
            LOG.debug('no available md modules found')
        raise
    util.subp(["udevadm", "control", "--start-exec-queue"])
    util.subp(["udevadm", "settle",
               "--exit-if-exists=%s" % md_devname])


def mdadm_examine(devpath, export=MDADM_USE_EXPORT):
    ''' exectute mdadm --examine, and optionally
        append --export.
        Parse and return dict of key=val from output'''
    assert_valid_devpath(devpath)

    cmd = ["mdadm", "--examine"]
    if export:
        cmd.extend(["--export"])

    cmd.extend([devpath])
    try:
        (out, _err) = util.subp(cmd, capture=True)
    except CalledProcessError:
        LOG.exception('Error: not a valid md device: ' + devpath)
        return {}

    if export:
        data = __mdadm_export_to_dict(out)
    else:
        data = __upgrade_detail_dict(__mdadm_detail_to_dict(out))

    return data


def mdadm_stop(devpath):
    assert_valid_devpath(devpath)

    LOG.info("mdadm stopping: %s" % devpath)
    util.subp(["mdadm", "--stop", devpath], rcs=[0, 1], capture=True)


def mdadm_remove(devpath):
    assert_valid_devpath(devpath)

    LOG.info("mdadm removing: %s" % devpath)
    util.subp(["mdadm", "--remove", devpath], rcs=[0, 1], capture=True)


def mdadm_query_detail(md_devname, export=MDADM_USE_EXPORT):
    valid_mdname(md_devname)

    cmd = ["mdadm", "--query", "--detail"]
    if export:
        cmd.extend(["--export"])
    cmd.extend([md_devname])
    (out, _err) = util.subp(cmd, capture=True)

    if export:
        data = __mdadm_export_to_dict(out)
    else:
        data = __upgrade_detail_dict(__mdadm_detail_to_dict(out))

    return data


def mdadm_detail_scan():
    (out, _err) = util.subp(["mdadm", "--detail", "--scan"], capture=True)
    if not _err:
        return out


# ------------------------------ #
def valid_mdname(md_devname):
    assert_valid_devpath(md_devname)

    if not is_valid_device(md_devname):
        raise ValueError('Specified md device does not exist: ' + md_devname)
        return False

    return True


def valid_devpath(devpath):
    if devpath:
        return devpath.startswith('/dev')
    return False


def assert_valid_devpath(devpath):
    if not valid_devpath(devpath):
        raise ValueError("Invalid devpath: '%s'" % devpath)


def md_sysfs_attr(md_devname, attrname):
    if not valid_mdname(md_devname):
        raise ValueError('Invalid md devicename: [{}]'.format(md_devname))

    attrdata = ''
    #  /sys/class/block/<md_short>/md
    sysmd = sys_block_path(md_devname, "md")

    #  /sys/class/block/<md_short>/md/attrname
    sysfs_attr_path = os.path.join(sysmd, attrname)
    if os.path.isfile(sysfs_attr_path):
        attrdata = util.load_file(sysfs_attr_path).strip()

    return attrdata


def md_raidlevel_short(raidlevel):
    if isinstance(raidlevel, int) or raidlevel in ['linear', 'stripe']:
        return raidlevel

    return int(raidlevel.replace('raid', ''))


def md_minimum_devices(raidlevel):
    ''' return the minimum number of devices for a given raid level '''
    rl = md_raidlevel_short(raidlevel)
    if rl in [0, 1, 'linear', 'stripe']:
        return 2
    if rl in [5]:
        return 3
    if rl in [6, 10]:
        return 4

    return -1


def __md_check_array_state(md_devname, mode='READWRITE'):
    modes = {
        'READWRITE': READWRITE_RAID_STATES,
        'READONLY': READONLY_RAID_STATES,
        'ERROR': ERROR_RAID_STATES,
    }
    if mode not in modes:
        raise ValueError('Invalid Array State mode: ' + mode)

    array_state = md_sysfs_attr(md_devname, 'array_state')
    if array_state in modes[mode]:
        return True

    return False


def md_check_array_state_rw(md_devname):
    return __md_check_array_state(md_devname, mode='READWRITE')


def md_check_array_state_ro(md_devname):
    return __md_check_array_state(md_devname, mode='READONLY')


def md_check_array_state_error(md_devname):
    return __md_check_array_state(md_devname, mode='ERROR')


def __mdadm_export_to_dict(output):
    ''' convert Key=Value text output into dictionary '''
    return dict(tok.split('=', 1) for tok in shlex.split(output))


def __mdadm_detail_to_dict(input):
    ''' Convert mdadm --detail output to dictionary

    /dev/vde:
              Magic : a92b4efc
            Version : 1.2
        Feature Map : 0x0
         Array UUID : 93a73e10:427f280b:b7076c02:204b8f7a
               Name : wily-foobar:0  (local to host wily-foobar)
      Creation Time : Sat Dec 12 16:06:05 2015
         Raid Level : raid1
       Raid Devices : 2

     Avail Dev Size : 20955136 (9.99 GiB 10.73 GB)
      Used Dev Size : 20955136 (9.99 GiB 10.73 GB)
         Array Size : 10477568 (9.99 GiB 10.73 GB)
        Data Offset : 16384 sectors
       Super Offset : 8 sectors
       Unused Space : before=16296 sectors, after=0 sectors
              State : clean
        Device UUID : 8fcd62e6:991acc6e:6cb71ee3:7c956919

        Update Time : Sat Dec 12 16:09:09 2015
      Bad Block Log : 512 entries available at offset 72 sectors
           Checksum : 65b57c2e - correct
             Events : 17


       Device Role : spare
       Array State : AA ('A' == active, '.' == missing, 'R' == replacing)
    '''
    data = {}

    device = re.findall('^(\/dev\/[a-zA-Z0-9-\._]+)', input)
    if len(device) == 1:
        data.update({'device': device[0]})
    else:
        raise ValueError('Failed to determine device in input')

    #  FIXME: probably could do a better regex to match the LHS which
    #         has one, two or three words
    for f in re.findall('(\w+|\w+\ \w+|\w+\ \w+\ \w+)' +
                        '\ \:\ ([a-zA-Z0-9\-\.,: \(\)=\']+)',
                        input, re.MULTILINE):
        key = f[0].replace(' ', '_').lower()
        val = f[1]
        if key in data:
            raise ValueError('Duplicate key in mdadm regex parsing: ' + key)
        data.update({key: val})

    return data


def md_device_key_role(devname):
    if not devname:
        raise ValueError('Missing parameter devname')
    return 'MD_DEVICE_' + dev_short(devname) + '_ROLE'


def md_device_key_dev(devname):
    if not devname:
        raise ValueError('Missing parameter devname')
    return 'MD_DEVICE_' + dev_short(devname) + '_DEV'


def __upgrade_detail_dict(detail):
    ''' This method attempts to convert mdadm --detail output into
        a KEY=VALUE output the same as mdadm --detail --export from mdadm v3.3
    '''
    # if the input already has MD_UUID, it's already been converted
    if 'MD_UUID' in detail:
        return detail

    md_detail = {
        'MD_LEVEL': detail['raid_level'],
        'MD_DEVICES': detail['raid_devices'],
        'MD_METADATA': detail['version'],
        'MD_NAME': detail['name'].split()[0],
    }

    # exmaine has ARRAY UUID
    if 'array_uuid' in detail:
        md_detail.update({'MD_UUID': detail['array_uuid']})
    # query,detail has UUID
    elif 'uuid' in detail:
        md_detail.update({'MD_UUID': detail['uuid']})

    device = detail['device']

    #  MD_DEVICE_vdc1_DEV=/dev/vdc1
    md_detail.update({md_device_key_dev(device): device})

    if 'device_role' in detail:
        role = detail['device_role']
        if role != 'spare':
            # device_role = Active device 1
            role = role.split()[-1]

        # MD_DEVICE_vdc1_ROLE=spare
        md_detail.update({md_device_key_role(device): role})

    return md_detail


def md_read_run_mdadm_map():
    '''
        md1 1.2 59beb40f:4c202f67:088e702b:efdf577a /dev/md1
        md0 0.90 077e6a9e:edf92012:e2a6e712:b193f786 /dev/md0

        return
        # md_shortname = (metaversion, md_uuid, md_devpath)
        data = {
            'md1': (1.2, 59beb40f:4c202f67:088e702b:efdf577a, /dev/md1)
            'md0': (0.90, 077e6a9e:edf92012:e2a6e712:b193f786, /dev/md0)
    '''

    mdadm_map = {}
    run_mdadm_map = '/run/mdadm/map'
    if os.path.exists(run_mdadm_map):
        with open(run_mdadm_map, 'r') as fp:
            data = fp.read().strip()
        for entry in data.split('\n'):
            (key, meta, md_uuid, dev) = entry.split()
            mdadm_map.update({key: (meta, md_uuid, dev)})

    return mdadm_map


def md_get_spares_list(devpath):
    sysfs_md = sys_block_path(devpath, "md")
    spares = [dev_path(dev[4:])
              for dev in os.listdir(sysfs_md)
              if (dev.startswith('dev-') and
                  util.load_file(os.path.join(sysfs_md,
                                              dev,
                                              'state')).strip() == 'spare')]

    return spares


def md_get_devices_list(devpath):
    sysfs_md = sys_block_path(devpath, "md")
    devices = [dev_path(dev[4:])
               for dev in os.listdir(sysfs_md)
               if (dev.startswith('dev-') and
                   util.load_file(os.path.join(sysfs_md,
                                               dev,
                                               'state')).strip() != 'spare')]
    return devices


def md_check_array_uuid(md_devname, md_uuid):
    valid_mdname(md_devname)

    # confirm we have /dev/{mdname} by following the udev symlink
    mduuid_path = ('/dev/disk/by-id/md-uuid-' + md_uuid)
    mdlink_devname = dev_path(os.path.realpath(mduuid_path))
    if md_devname != mdlink_devname:
        err = ('Mismatch between devname and md-uuid symlink: ' +
               '%s -> %s != %s' % (mduuid_path, mdlink_devname, md_devname))
        raise ValueError(err)

    return True


def md_get_uuid(md_devname):
    valid_mdname(md_devname)

    md_query = mdadm_query_detail(md_devname)
    return md_query.get('MD_UUID', None)


def _compare_devlist(expected, found):
    LOG.debug('comparing device lists: '
              'expected: {} found: {}'.format(expected, found))
    expected = set(expected)
    found = set(found)
    if expected != found:
        missing = expected.difference(found)
        extra = found.difference(expected)
        raise ValueError("RAID array device list does not match."
                         " Missing: {} Extra: {}".format(missing, extra))


def md_check_raidlevel(raidlevel):
    # Validate raidlevel against what curtin supports configuring
    if raidlevel not in VALID_RAID_LEVELS:
        err = ('Invalid raidlevel: ' + raidlevel +
               ' Must be one of: ' + str(VALID_RAID_LEVELS))
        raise ValueError(err)
    return True


def md_block_until_in_sync(md_devname):
    '''
    sync_completed
    This shows the number of sectors that have been completed of
    whatever the current sync_action is, followed by the number of
    sectors in total that could need to be processed.  The two
    numbers are separated by a '/'  thus effectively showing one
    value, a fraction of the process that is complete.
    A 'select' on this attribute will return when resync completes,
    when it reaches the current sync_max (below) and possibly at
    other times.
    '''
    # FIXME: use selectors to block on: /sys/class/block/mdX/md/sync_completed
    pass


def md_check_array_state(md_devname):
    # check array state

    writable = md_check_array_state_rw(md_devname)
    degraded = md_sysfs_attr(md_devname, 'degraded')
    sync_action = md_sysfs_attr(md_devname, 'sync_action')

    if not writable:
        raise ValueError('Array not in writable state: ' + md_devname)
    if degraded != "0":
        raise ValueError('Array in degraded state: ' + md_devname)
    if sync_action != "idle":
        raise ValueError('Array syncing, not idle state: ' + md_devname)

    return True


def md_check_uuid(md_devname):
    md_uuid = md_get_uuid(md_devname)
    if not md_uuid:
        raise ValueError('Failed to get md UUID from device: ' + md_devname)
    return md_check_array_uuid(md_devname, md_uuid)


def md_check_devices(md_devname, devices):
    if not devices or len(devices) == 0:
        raise ValueError('Cannot verify raid array with empty device list')

    # collect and compare raid devices based on md name versus
    # expected device list.
    #
    # NB: In some cases, a device might report as a spare until
    #     md has finished syncing it into the array.  Currently
    #     we fail the check since the specified raid device is not
    #     yet in its proper role.  Callers can check mdadm_sync_action
    #     state to see if the array is currently recovering, which would
    #     explain the failure.  Also  mdadm_degraded will indicate if the
    #     raid is currently degraded or not, which would also explain the
    #     failure.
    md_raid_devices = md_get_devices_list(md_devname)
    LOG.debug('md_check_devices: md_raid_devs: ' + str(md_raid_devices))
    _compare_devlist(devices, md_raid_devices)


def md_check_spares(md_devname, spares):
    # collect and compare spare devices based on md name versus
    # expected device list.
    md_raid_spares = md_get_spares_list(md_devname)
    _compare_devlist(spares, md_raid_spares)


def md_check_array_membership(md_devname, devices):
    # validate that all devices are members of the correct array
    md_uuid = md_get_uuid(md_devname)
    for device in devices:
        dev_examine = mdadm_examine(device, export=False)
        if 'MD_UUID' not in dev_examine:
            raise ValueError('Device is not part of an array: ' + device)
        dev_uuid = dev_examine['MD_UUID']
        if dev_uuid != md_uuid:
            err = "Device {} is not part of {} array. ".format(device,
                                                               md_devname)
            err += "MD_UUID mismatch: device:{} != array:{}".format(dev_uuid,
                                                                    md_uuid)
            raise ValueError(err)


def md_check(md_devname, raidlevel, devices=[], spares=[]):
    ''' Check passed in variables from storage configuration against
        the system we're running upon.
    '''
    LOG.debug('RAID validation: ' +
              'name={} raidlevel={} devices={} spares={}'.format(md_devname,
                                                                 raidlevel,
                                                                 devices,
                                                                 spares))
    assert_valid_devpath(md_devname)

    md_check_array_state(md_devname)
    md_check_raidlevel(raidlevel)
    md_check_uuid(md_devname)
    md_check_devices(md_devname, devices)
    md_check_spares(md_devname, spares)
    md_check_array_membership(md_devname, devices + spares)

    LOG.debug('RAID array OK: ' + md_devname)
    return True


# vi: ts=4 expandtab syntax=python
