# This file is part of curtin. See LICENSE file for copyright and license info.

import glob
import os
import re
import tempfile
from curtin import util
from curtin.log import LOG, logged_time


class DasdPartition:
    def __init__(self, device, start, end, length, id, system):
        self.device = device
        self.start = int(start)
        self.end = int(end)
        self.length = int(length)
        self.id = id
        self.system = system


class DasdPartitionTable:
    def __init__(self, devname, blocks_per_track, bytes_per_block):
        self.devname = devname
        self.blocks_per_track = blocks_per_track
        self.bytes_per_block = bytes_per_block
        self.partitions = []

    @property
    def bytes_per_track(self):
        return self.bytes_per_block * self.blocks_per_track

    def tracks_needed(self, size_in_bytes):
        return ((size_in_bytes - 1) // self.bytes_per_track) + 1

    @classmethod
    def from_fdasd_output(cls, devname, output):
        line_iter = iter(output.splitlines())
        for line in line_iter:
            if line.startswith("Disk"):
                break
        kw = {'devname': devname}
        label_to_attr = {
            'blocks per track': 'blocks_per_track',
            'bytes per block': 'bytes_per_block'
            }
        for line in line_iter:
            if '--- tracks ---' in line:
                break
            if ':' in line:
                label, value = line.split(':', 1)
                label = label.strip(' .')
                value = value.strip()
                if label in label_to_attr:
                    kw[label_to_attr[label]] = int(value)
        table = cls(**kw)
        for line in line_iter:
            if line.startswith('exiting'):
                break
            vals = line.split(None, 5)
            if vals[0].startswith('/dev/'):
                table.partitions.append(DasdPartition(*vals))
        return table

    @classmethod
    def from_fdasd(cls, devname):
        """Use fdasd to construct a DasdPartitionTable.

        % fdasd --table /dev/dasdc
        reading volume label ..: VOL1
        reading vtoc ..........: ok


        Disk /dev/dasdc:
          cylinders ............: 10017
          tracks per cylinder ..: 15
          blocks per track .....: 12
          bytes per block ......: 4096
          volume label .........: VOL1
          volume serial ........: 0X1522
          max partitions .......: 3

         ------------------------------- tracks -------------------------------
                       Device      start      end   length   Id  System
                  /dev/dasdc1          2    43694    43693    1  Linux native
                  /dev/dasdc2      43695    87387    43693    2  Linux native
                  /dev/dasdc3      87388   131080    43693    3  Linux native
                                  131081   150254    19174       unused
        exiting...
        """
        cmd = ['fdasd', '--table', devname]
        out, _err = util.subp(cmd, capture=True)
        LOG.debug("from_fdasd output:\n---\n%s\n---\n", out)
        return cls.from_fdasd_output(devname, out)


def dasdinfo(device_id):
    ''' Run dasdinfo command and return the exported values.

    :param: device_id:  string, device_id of the dasd device to query.
    :returns: dictionary of udev key=value pairs.
    :raises: ValueError on None-ish device_id.
    :raises: ProcessExecutionError if dasdinfo returns non-zero.

    e.g.

    % info = dasdinfo('0.0.1544')
    % pprint.pprint(info)
    {'ID_BUS': 'ccw',
     'ID_SERIAL': '0X1544',
     'ID_TYPE': 'disk',
     'ID_UID': 'IBM.750000000DXP71.1500.44',
     'ID_XUID': 'IBM.750000000DXP71.1500.44'}
    '''
    _valid_device_id(device_id)

    out, err = util.subp(
        ['dasdinfo', '--all', '--export', '--busid=%s' % device_id],
        capture=True)

    return util.load_shell_content(out)


def dasd_format(devname):
    """Return the format (ldl/cdl/not-formatted) of devname."""
    if not os.path.exists(devname):
        raise ValueError("Invalid dasd device name: '%s'" % devname)

    out, err = util.subp(['dasdview', '--extended', devname], capture=True)

    return _dasd_format(out)


DASD_FORMAT = r"^format\s+:.+\s+(?P<value>\w+\s\w+)$"


def find_val(regex, content):
    m = re.search(regex, content, re.MULTILINE)
    if m is not None:
        return m.group("value")


def _dasd_format(dasdview_output):
    """ Read and return specified device "disk_layout" value.

    :returns: string: One of ['cdl', 'ldl', 'not-formatted'].
    :raises: ValueError if dasdview result missing 'format' section.

    """
    if not dasdview_output:
        return

    mapping = {
       'cdl formatted': 'cdl',
       'ldl formatted': 'ldl',
       'not formatted': 'not-formatted',
    }
    diskfmt = find_val(DASD_FORMAT, dasdview_output)
    if diskfmt is not None:
        return mapping.get(diskfmt.lower())


def _valid_device_id(device_id):
    """ validate device_id string.

    :param device_id: string representing a s390 ccs device in the format
       <channel subsystem number>.<data source number>.<device id>
       e.g. 0.0.74fc
    """
    if not device_id or not isinstance(device_id, util.string_types):
        raise ValueError(
            "device_id invalid: value None or non-string: '%s'" % device_id)

    if device_id.count('.') != 2:
        raise ValueError(
            "device_id invalid: format requires two '.' chars: %s" % device_id)

    (css, dsn, dev) = device_id.split('.')

    if not all([css, dsn, dev]):
        raise ValueError(
            "device_id invalid: format must be X.X.XXXX: '%s'" % device_id)

    if not (0 <= int(css, 16) < 256):
        raise ValueError("device_id invalid: css not in 0-255: '%s'" % css)

    if not (0 <= int(dsn, 16) < 256):
        raise ValueError("device_id invalid: dsn not in 0-255: '%s'" % dsn)

    if not (0 <= int(dev.lower(), 16) <= 65535):
        raise ValueError(
            "device_id invalid: devno not in 0-0xffff: '%s'" % dev)

    return True


class CcwDevice(object):

    def __init__(self, device_id):
        self.device_id = device_id
        _valid_device_id(self.device_id)

    def ccw_device_attr_path(self, attr):
        return '/sys/bus/ccw/devices/%s/%s' % (self.device_id, attr)

    def ccw_device_attr(self, attr):
        """ Read a ccw_device attribute from sysfs for specified device_id.

        :param device_id: string of device ccw bus_id
        :param attr: string of which sysfs attribute to read
        :returns stripped string of the value in the specified attribute
            otherwise empty string if path to attribute does not exist.
        :raises: ValueError if device_id is not valid
        """
        attrdata = None

        sysfs_attr_path = self.ccw_device_attr_path(attr)
        if os.path.isfile(sysfs_attr_path):
            attrdata = util.load_file(sysfs_attr_path).strip()

        return attrdata


class DasdDevice(CcwDevice):

    @property
    def devname(self):
        return '/dev/disk/by-path/ccw-%s' % self.device_id

    def partition(self, partnumber, partsize, strict=True):
        """ Add a partition to this DasdDevice specifying partnumber and size.

        :param partnumber: integer value of partition number (1, 2 or 3)
        :param partsize: partition sizes in bytes.
        :param strict: boolean which enforces that dasd device exists before
            issuing fdasd command, defaults to True.

        :raises: RuntimeError if strict==True and devname does not exist.
        :raises: ValueError on invalid devname

        Example fdasd command with defaults:
          fdasd --verbose --config=/tmp/curtin/dasd-part1.fdasd /dev/dasdb
        """
        if partnumber > 3:
            raise ValueError('DASD devices only allow 3 partitions')

        if strict and not os.path.exists(self.devname):
            raise RuntimeError("devname '%s' does not exist" % self.devname)

        pt = DasdPartitionTable.from_fdasd(self.devname)
        new_partitions = []
        for partinfo in pt.partitions[0:partnumber]:
            new_partitions.append((partinfo.start, partinfo.end))

        # first partition always starts at track 2
        # all others start after the previous partition ends
        if partnumber == 1:
            start = 2
        else:
            start = int(pt.partitions[-1].end) + 1
        # end is inclusive
        end = start + pt.tracks_needed(partsize) - 1
        new_partitions.append((start, end))

        content = "\n".join(["[%s,%s]" % (part[0], part[1])
                             for part in new_partitions])
        LOG.debug("fdasd: partitions to be created: %s", new_partitions)
        LOG.debug("fdasd: content=\n%s", content)
        wfp = tempfile.NamedTemporaryFile(suffix=".fdasd", delete=False)
        wfp.close()
        util.write_file(wfp.name, content)
        cmd = ['fdasd', '--verbose', '--config=%s' % wfp.name, self.devname]
        LOG.debug('Partitioning %s with %s', self.devname, cmd)
        try:
            out, err = util.subp(cmd, capture=True)
        except util.ProcessExecutionError as e:
            LOG.error("Partitioning failed: %s", e)
            raise
        finally:
            if os.path.exists(wfp.name):
                os.unlink(wfp.name)

    def is_not_formatted(self):
        """ Returns a boolean indicating if the specified device_id is not yet
            formatted.

        :returns: boolean: True if the device is not formatted.
        """
        return self.ccw_device_attr('status') == "unformatted"

    def blocksize(self):
        """ Read and return device_id's 'blocksize' value.

        :param: device_id: string of device ccw bus_id.
        :returns: string: the device's current blocksize.
        """
        blkattr = 'block/*/queue/hw_sector_size'
        # In practice there will only be one entry in the directory
        # /sys/bus/ccw/devices/{device_id}/block/, but in case
        # something strange happens and there are more, this assumes
        # all block devices connected to the dasd have the same block
        # size...
        path = glob.glob(self.ccw_device_attr_path(blkattr))[0]
        return util.load_file(path)

    def disk_layout(self):
        """ Read and return specified device "disk_layout" value.

        :returns: string: One of ['cdl', 'ldl', 'not-formatted'].
        :raises: ValueError if dasdview result missing 'format' section.
        """
        format = dasd_format(self.devname)
        if not format:
            raise ValueError(
                'could not determine format of %s' % self.devname)
        return format

    def label(self):
        """Read and return specified device label (VOLSER) value.

        :returns: string: devices's label (VOLSER) value.
        :raises: ValueError if it cannot get label value.
        """
        info = dasdinfo(self.device_id)
        if 'ID_SERIAL' not in info:
            raise ValueError(
                'Failed to read %s label (VOLSER)' % self.device_id)

        return info['ID_SERIAL']

    def needs_formatting(self, blksize, layout, volser):
        """ Determine if DasdDevice attributes matches the required parameters.

        Note that devices that indicate they are unformatted will require
        formatting.

        :param blksize: expected blocksize of the device.
        :param layout: expected disk layout.
        :param volser: expected label, if None, label is ignored.
        :returns: boolean, True if formatting is needed, else False.
        """
        LOG.debug('Checking if dasd %s needs formatting', self.device_id)
        if self.is_not_formatted():
            LOG.debug('dasd %s is not formatted', self.device_id)
            return True

        if int(blksize) != int(self.blocksize()):
            LOG.debug('dasd %s block size (%s) does not match (%s)',
                      self.device_id, self.blocksize(), blksize)
            return True

        if layout != self.disk_layout():
            LOG.debug('dasd %s disk layout (%s) does not match %s',
                      self.device_id, self.disk_layout(), layout)
            return True

        if volser and volser != self.label():
            LOG.debug('dasd %s volser (%s) does not match %s',
                      self.device_id, self.label(), volser)
            return True

        return False

    @logged_time("DASD.FORMAT")
    def format(self, blksize=4096, layout='cdl', force=False, set_label=None,
               keep_label=False, no_label=False, mode='quick'):
        """ Format DasdDevice with supplied parameters.

        :param blksize: integer value to configure disk block size in bytes.
            Must be one of 512, 1024, 2048, 4096; defaults to 4096.
        :param layout: string specify disk layout format. Must be one of
            'cdl' (Compatible Disk Layout, default) or
            'ldl' (Linux Disk Layout).
        :param force: boolean set true to skip sanity checks,
            defaults to False
        :param set_label: string to write to the volume label for
            identification.  If no label provided, a label is generated from
            device number of the dasd.
            Note: is interpreted as ASCII string and is automatically converted
            to uppercase and then to EBCDIC.  e.g. 'a@b\\$c#' to get A@B$C#.
        :param keep_label: boolean set true to keep existing label on dasd,
            ignores label param value, defaults to False.
        :param no_label: boolean set true to skip writing label to dasd,
            ignores label and keep_label params, defaults to False.
        :param mode: string to control format mode.  Must be one of
            'full'   (Format the full disk),
            'quick'  (Format the first two tracks, default),
            'expand' (Format unformatted tracks at device end).
        :param strict: boolean which enforces that dasd device exists before
            issuing format command, defaults to True.

        :raises: RuntimeError if devname does not exist.
        :raises: ValueError on invalid blocksize, disk_layout and mode.
        :raises: ProcessExecutionError on errors running 'dasdfmt' command.

        Example dadsfmt command with defaults:
          dasdformat -y --blocksize=4096 --disk_layout=cdl \
                     --mode=quick /dev/dasda
        """
        if not os.path.exists(self.devname):
            raise RuntimeError("devname '%s' does not exist" % self.devname)

        if no_label:
            keep_label = False
            set_label = None

        if keep_label:
            set_label = None

        valid_blocksize = [512, 1024, 2048, 4096]
        if blksize not in valid_blocksize:
            raise ValueError(
                "blksize: '%s' not one of '%s'" % (blksize, valid_blocksize))

        valid_layouts = ['cdl', 'ldl']
        if layout not in valid_layouts:
            raise ValueError("layout: '%s' not one of '%s'" % (layout,
                                                               valid_layouts))
        if not mode:
            mode = 'quick'

        valid_modes = ['full', 'quick', 'expand']
        if mode not in valid_modes:
            raise ValueError("mode: '%s' not one of '%s'" % (mode,
                                                             valid_modes))

        opts = [
            '-y',
            '--blocksize=%s' % blksize,
            '--disk_layout=%s' % layout,
            '--mode=%s' % mode
        ]
        if set_label:
            opts += ['--label=%s' % set_label]
        if keep_label:
            opts += ['--keep_label']
        if no_label:
            opts += ['--no_label']
        if force:
            opts += ['--force']

        cmd = ['dasdfmt'] + opts + [self.devname]
        LOG.debug('Formatting %s with %s', self.devname, cmd)
        try:
            out, _err = util.subp(cmd, capture=True)
        except util.ProcessExecutionError as e:
            LOG.error("Formatting failed: %s", e)
            raise

# vi: ts=4 expandtab syntax=python
