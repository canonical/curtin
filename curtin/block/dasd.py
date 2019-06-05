# This file is part of curtin. See LICENSE file for copyright and license info.

import collections
import os
import re
import tempfile
from curtin import util
from curtin.log import LOG, logged_time

Dasdvalue = collections.namedtuple('Dasdvalue', ['hex', 'dec', 'txt'])


def dasdinfo(device_id, rawoutput=False, strict=False):
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

    try:
        out, err = util.subp(
            ['dasdinfo', '--all', '--export',
             '--busid=%s' % device_id], capture=True)
    except util.ProcessExecutionError as e:
        LOG.warning('dasdinfo result may be incomplete: %s', e)
        if strict:
            raise
        out = e.stdout
        err = e.stderr

    if rawoutput:
        return (out, err)

    return util.load_shell_content(out)


def dasdview(devname, rawoutput=False):
    ''' Run dasdview on devname and return dictionary of data.

    dasdview --extended has 3 sections
    general (2:6), geometry (8:12), extended (14:)

    '''
    if not os.path.exists(devname):
        raise ValueError("Invalid dasd device name: '%s'" % devname)

    out, err = util.subp(['dasdview', '--extended', devname], capture=True)

    if rawoutput:
        return (out, err)

    return _parse_dasdview(out)


def _parse_dasdview(view_output):
    """ Parse dasdview --extended output into a dictionary

    Input:
    --- general DASD information ---------------------------------------------
    device node            : /dev/dasdd
    busid                  : 0.0.1518
    type                   : ECKD
    device type            : hex 3390       dec 13200

    --- DASD geometry --------------------------------------------------------
    number of cylinders    : hex 2721       dec 10017
    tracks per cylinder    : hex f          dec 15
    blocks per track       : hex c          dec 12
    blocksize              : hex 1000       dec 4096

    --- extended DASD information --------------------------------------------
    real device number     : hex 0          dec 0
    subchannel identifier  : hex 178        dec 376
    CU type  (SenseID)     : hex 3990       dec 14736
    CU model (SenseID)     : hex e9         dec 233
    device type  (SenseID) : hex 3390       dec 13200
    device model (SenseID) : hex c          dec 12
    open count             : hex 1          dec 1
    req_queue_len          : hex 0          dec 0
    chanq_len              : hex 0          dec 0
    status                 : hex 5          dec 5
    label_block            : hex 2          dec 2
    FBA_layout             : hex 0          dec 0
    characteristics_size   : hex 40         dec 64
    confdata_size          : hex 100        dec 256
    format                 : hex 2          dec 2           CDL formatted
    features               : hex 0          dec 0           default

    characteristics        : 3990e933 900c5e0c  39f72032 2721000f
                             e000e5a2 05940222  13090674 00000000
                             00000000 00000000  32321502 dfee0001
                             0677080f 007f4800  1f3c0000 00002721

    configuration_data     : dc010100 f0f0f2f1  f0f7f9f0 f0c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10818
                             d4020000 f0f0f2f1  f0f7f9f6 f1c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10800
                             d0000000 f0f0f2f1  f0f7f9f6 f1c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f00800
                             f0000001 f0f0f2f1  f0f7f9f0 f0c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10800
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             81000003 2d001e00  15000247 000c0016
                             000cc018 935e41ee  00030000 0000a000

    Output:

    view = {
    'extended': {
        'chanq_len': Dasdvalue(hex='0x0', dec=0, txt=None),
        'characteristics': ['3990e933', ...], # shortened for brevity
        'characteristics_size': Dasdvalue(hex='0x40', dec=64, txt=None),
        'confdata_size': Dasdvalue(hex='0x100', dec=256, txt=None),
        'configuration_data': ['dc010100', ...], # shortened for brevity
        'cu_model_senseid': Dasdvalue(hex='0xe9', dec=233, txt=None),
        'cu_type__senseid': Dasdvalue(hex='0x3990', dec=14736, txt=None),
        'device_model_senseid': Dasdvalue(hex='0xc', dec=12, txt=None),
        'device_type__senseid': Dasdvalue(hex='0x3390', dec=13200, txt=None),
        'fba_layout': Dasdvalue(hex='0x0', dec=0, txt=None),
        'features': Dasdvalue(hex='0x0', dec=0, txt='default'),
        'format': Dasdvalue(hex='0x2', dec=2, txt='cdl'),
        'label_block': Dasdvalue(hex='0x2', dec=2, txt=None),
        'open_count': Dasdvalue(hex='0x1', dec=1, txt=None),
        'real_device_number': Dasdvalue(hex='0x0', dec=0, txt=None),
        'req_queue_len': Dasdvalue(hex='0x0', dec=0, txt=None),
        'status': Dasdvalue(hex='0x5', dec=5, txt=None),
        'subchannel_identifier': Dasdvalue(hex='0x178', dec=376, txt=None)},
    'general': {
        'busid': ['0.0.1518'],
        'device_node': ['/dev/dasdd'],
        'device_type': Dasdvalue(hex='0x3390', dec=13200, txt=None),
        'type': ['ECKD']},
    'geometry': {
        'blocks_per_track': Dasdvalue(hex='0xc', dec=12, txt=None),
        'blocksize': Dasdvalue(hex='0x1000', dec=4096, txt=None),
        'number_of_cylinders': Dasdvalue(hex='0x2721', dec=10017, txt=None),
        'tracks_per_cylinder': Dasdvalue(hex='0xf', dec=15, txt=None)}
    }
    """

    info_key_map = {
        'CDL formatted': 'cdl',
        'LDL formatted': 'ldl',
        'NOT formatted': 'not-formatted',
    }

    def _mkdasdvalue(hex_str, dec_str, comment=None):
        v_hex = hex_str.replace('hex ', '0x')
        v_dec = int(dec_str.replace('dec ', ''))
        v_str = None
        if comment is not None:
            v_str = info_key_map.get(comment, comment)

        return Dasdvalue(v_hex, v_dec, v_str)

    def _map_strip(value):
        v_type = type(value)
        return v_type(map(lambda x: x.strip(), value))

    def _parse_output(output):
        parsed = {}
        key = prev_key = value = None
        for line in output:
            if not line:
                continue
            if ':' in line:
                key, value = map(lambda x: x.strip(),
                                 line.lstrip().split(':'))
                # normalize lvalue
                key = key.replace('  ', '_')
                key = key.replace(' ', '_')
                key = key.replace('(', '').replace(')', '')
                key = key.lower()
                prev_key = key
                if value and '\t' in value:
                    value = _map_strip(value.split('\t'))
                    # [hex X, dec Y]
                    # [hex X, dec Y, string]
                    value = _mkdasdvalue(*value)
                elif value and '  ' in value:
                    # characteristics : XXXXXXX XXXXXXX  XXXXXXXX XXXXXXX
                    #                   YYYYYYY YYYYYYY  YYYYYYYY YYYYYYY
                    # convert to list of strings.
                    value = value.lstrip().split()
                else:
                    value = None
            else:
                key = prev_key
                # no colon line, parse value from line
                #                   YYYYYYY YYYYYYY  YYYYYYYY YYYYYYY
                value = line.lstrip().split()

            # extend lists for existing keys
            if key in parsed and type(value) == list:
                parsed[key].extend(value)
            else:
                parsed.update({key: value})

        return parsed

    if not view_output or not isinstance(view_output, util.string_types):
        raise ValueError(
            'Invalid value for input to parse: ' + str(view_output))

    # XXX: dasdview --extended has 52 lines for dasd devices
    if len(view_output.splitlines()) < 52:
        raise ValueError(
            'dasdview output has fewer than 52 lines, cannot parse')

    lines = view_output.splitlines()
    gen_start, gen_end = (2, 6)
    geo_start, geo_end = (8, 12)
    ext_start, ext_end = (14, len(lines))

    general_output = lines[gen_start:gen_end]
    geometry_output = lines[geo_start:geo_end]
    extended_output = lines[ext_start:ext_end]

    view = {
        'general': _parse_output(general_output),
        'geometry': _parse_output(geometry_output),
        'extended': _parse_output(extended_output),
    }
    return view


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

    if not (0 <= int(dev.lower(), 16) < 65535):
        raise ValueError(
            "device_id invalid: devno not in 0-0x10000: '%s'" % dev)

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

    def __init__(self, device_id):
        super(DasdDevice, self).__init__(device_id)
        self._kname = None

    @property
    def kname(self):
        if not self._kname:
            self._kname = self._get_kname()
        return self._kname

    def _get_kname(self):
        """ Return the kernel name of the dasd device. """
        if not self.is_online():
            raise RuntimeError('Cannot determine dasd kname for offline '
                               'device: %s' % self.device_id)

        blockdir = self.ccw_device_attr_path('block')
        if not os.path.isdir(blockdir):
            raise RuntimeError('Unexpectedly not a directory: %s' % blockdir)

        try:
            knames = os.listdir(blockdir)
            [dasd_kname] = knames
        except ValueError:
            raise RuntimeError('Unexpected os.listdir result at sysfs path '
                               '%s: "%s"' % (blockdir, knames))

        return dasd_kname

    @property
    def devname(self):
        return '/dev/%s' % self.kname

    def _bytes_to_tracks(self, geometry, request_size):
        """ Return the number of tracks needed to hold the request size.

        :param geometry: dictionary from dasdview output which includes
            info on number of cylinders, tracks and blocksize.
        :param request_size: size in Bytes

        :raises: ValueError on missing or invalid geometry dict, missing
            request_size.

        Example geometry:
        'geometry': {
            'blocks_per_track': Dasdvalue(hex='0xc', dec=12, txt=None),
            'blocksize': Dasdvalue(hex='0x1000', dec=4096, txt=None),
            'number_of_cylinders':
                 Dasdvalue(hex='0x2721', dec=10017, txt=None),
            'tracks_per_cylinder': Dasdvalue(hex='0xf', dec=15, txt=None)}
        }
        """

        if not geometry or not isinstance(geometry, dict):
            raise ValueError('Missing or invalid geometry parameter.')

        if not all([key for key in geometry.keys()
                    if key in ['blocksize', 'blocks_per_track']]):
            raise ValueError('Geometry dict missing required keys')

        if not request_size or not isinstance(request_size,
                                              util.numeric_types):
            raise ValueError('Missing or invalid request_size.')

        # helper to extract the decimal value from Dasdvalue objects
        def _dval(dval):
            return dval.dec

        bytes_per_track = (
            _dval(geometry['blocksize']) * _dval(geometry['blocks_per_track']))
        tracks_needed = ((request_size - 1) // bytes_per_track) + 1
        return tracks_needed

    def get_partition_table(self):
        """ Use fdasd to query the partition table (VTOC).

            Returns a list of tuples, each tuple composed of the first 6
            fields of matching lines in the output.

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
        cmd = ['fdasd', '--table', self.devname]
        out, _err = util.subp(cmd, capture=True)
        lines = re.findall('.*%s.*Linux.*' % self.devname, out)
        partitions = []
        for line in lines:
            partitions.append(tuple(line.split()[0:5]))

        return partitions

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

        info = dasdview(self.devname)
        geo = info['geometry']

        existing_partitions = self.get_partition_table()
        partitions = []
        for partinfo in existing_partitions[0:partnumber]:
            # (devpath, start_track, end_track, nr_tracks, partnum)
            start = partinfo[1]
            end = partinfo[2]
            partitions.append((start, end))

        # first partition always starts at track 2
        # all others start after the previous partition ends
        if partnumber == 1:
            start = 2
        else:
            start = int(partitions[-1][1]) + 1
        # end is size + 1
        tracks_needed = int(self._bytes_to_tracks(geo, partsize))
        end = start + tracks_needed + 1
        partitions.append(("%s" % start, "%s" % end))

        content = "\n".join(["[%s,%s]" % (part[0], part[1])
                             for part in partitions])
        LOG.debug("fdasd: partitions to be created: %s", partitions)
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

        :param device_id: string of device ccw bus_id.
        :returns: boolean: True if the device is not formatted.
        """
        return self.ccw_device_attr('status') == "unformatted"

    def is_online(self):
        """ Returns a boolean indicating if specified device is online.

        :param device_id: string of device ccw bus_id.
        :returns: boolean: True if device is online.
        """
        return self.ccw_device_attr('online') == "1"

    def status(self):
        """ Read and return device_id's 'status' sysfs attribute value'

        :param device_id: string of device ccw bus_id.
        :returns: string: the value inside the 'status' sysfs attribute.
        """
        return self.ccw_device_attr('status')

    def blocksize(self):
        """ Read and return device_id's 'blocksize' value.

        :param: device_id: string of device ccw bus_id.
        :returns: string: the device's current blocksize.
        """
        blkattr = 'block/%s/queue/hw_sector_size' % self.kname
        return self.ccw_device_attr(blkattr)

    def disk_layout(self):
        """ Read and return specified device "disk_layout" value.

        :returns: string: One of ['cdl', 'ldl', 'not-formatted'].
        :raises: ValueError if dasdview result missing 'format' section.

        """
        view = dasdview(self.devname)
        disk_format = view.get('extended', {}).get('format')
        if not disk_format:
            raise ValueError(
                'dasdview on %s missing "format" section' % self.devname)

        return disk_format.txt

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
               keep_label=False, no_label=False, mode='quick', strict=True):
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

        :raises: RuntimeError if strict==True and devname does not exist.
        :raises: ValueError on invalid blocksize, disk_layout and mode.
        :raises: ProcessExecutionError on errors running 'dasdfmt' command.

        Example dadsfmt command with defaults:
          dasdformat -y --blocksize=4096 --disk_layout=cdl \
                     --mode=quick /dev/dasda
        """
        if strict and not os.path.exists(self.devname):
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
