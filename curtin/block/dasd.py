# This file is part of curtin. See LICENSE file for copyright and license info.

import collections
import os
from curtin import util
from curtin.log import LOG

Dasdvalue = collections.namedtuple('Dasdvalue', ['hex', 'dec', 'txt'])


def is_valid_device_id(device_id):
    """ validate device_id string.

    :param device_id: string representing a s390 ccs device in the format
       <channel subsystem number>.<data source number>.<device id>
       e.g. 0.0.74fc
    """
    if not device_id or not isinstance(device_id, util.string_types):
        raise ValueError("device_id parameter value invalid: '%s'" % device_id)

    if device_id.count('.') != 2:
        raise ValueError(
            "device_id format invalid, requires two '.' chars: %s" % device_id)

    (css, dsn, dev) = device_id.split('.')

    if not all([css, dsn, dev]):
        raise ValueError(
            "device_id format invalid, must be X.X.XXXX: '%s'" % device_id)

    if int(css, 16) not in range(0, 256):
        raise ValueError("device_id css invalid, not in 0-256: '%s'" % css)

    if int(dsn, 16) not in range(0, 256):
        raise ValueError("device_id dsn invalid, not in 0-256: '%s'" % dsn)

    if int(dev.lower(), 16) not in range(0, 65535):
        raise ValueError("device number invalid: not < 0x10000: '%s'" % dev)


def valid_device_id(device_id):
    """ Return a boolean indicating if device_id is valid."""
    try:
        is_valid_device_id(device_id)
        return True
    except ValueError:
        return False


def device_id_to_kname(device_id):
    """ Return the kernel name of the device specified by parameter."""
    if not valid_device_id(device_id):
        raise ValueError("Invalid device_id:'%s'" % device_id)

    if not is_online(device_id):
        raise RuntimeError(
            'Cannot determine dasd kname for offline device: %s' % device_id)

    blockdir = '/sys/bus/ccw/devices/%s/block' % device_id
    if not os.path.isdir(blockdir):
        raise RuntimeError('Unexpectedly not a directory: %s' % blockdir)

    try:
        knames = os.listdir(blockdir)
        [dasd_kname] = knames
    except ValueError:
        raise RuntimeError('Unexpected os.listdir result at sysfs path '
                           '%s: "%s"' % (blockdir, knames))

    return dasd_kname


def kname_to_device_id(kname):
    """ Return the device_id of a dasd kernel name specified """
    if not kname:
        raise ValueError("Invalid kname: '%s'" % kname)

    # handle devname passed in instead
    if kname.startswith('/dev/'):
        kname = kname.replace('/dev/', '')

    sysfs_path = '/sys/class/block/%s/device' % kname
    if not os.path.exists(sysfs_path):
        raise RuntimeError(
            "Sysfs path of kname doesn't exist: '%s'" % sysfs_path)

    # /sys/class/block/dasda/device -> ../../../0.0.1544
    # /sys/devices/css0/0.0.01a4/0.0.1544
    # 0.0.1544
    return os.path.basename(os.path.realpath(sysfs_path))


def ccw_device_attr(device_id, attr):
    """ Read a ccw_device attribute from sysfs for specified device_id.

    :param device_id: string of device ccw bus_id
    :param attr: string of which sysfs attribute to read
    :returns stripped string of the value in the specified attribute
        otherwise empty string if path to attribute does not exist.
    :raises: ValueError if device_id is not valid
    """
    attrdata = ''
    if not valid_device_id(device_id):
        raise ValueError("Invalid device_id:'%s'" % device_id)

    sysfs_attr_path = '/sys/bus/ccw/devices/%s/%s' % (device_id, attr)
    if os.path.isfile(sysfs_attr_path):
        attrdata = util.load_file(sysfs_attr_path).strip()

    return attrdata


def is_active(device_id):
    """ Returns a boolean indicating if the specified device_id is active.

    :param device_id: string of device ccw bus_id.
    :returns: boolean: True if device is active.
    """
    return ccw_device_attr(device_id, 'status') == "online"


def is_alias(device_id):
    """ Returns a boolean indicating if the specified device_id is an alias.

    :param device_id: string of device ccw bus_id.
    :returns: boolean: True if device is an alias.
    """
    return ccw_device_attr(device_id, 'alias') == "1"


def is_not_formatted(device_id, status=None):
    """ Returns a boolean indicating if the specified device_id is not yet
        formatted.

    :param device_id: string of device ccw bus_id.
    :returns: boolean: True if the device is not formatted.
    """
    return ccw_device_attr(device_id, 'status') == "unformatted"


def is_online(device_id):
    """ Returns a boolean indicating if specified device is online.

    :param device_id: string of device ccw bus_id.
    :returns: boolean: True if device is online.
    """
    return ccw_device_attr(device_id, 'online') == "1"


def status(device_id):
    """ Read and return device_id's 'status' sysfs attribute value'

    :param device_id: string of device ccw bus_id.
    :returns: string: the value inside the 'status' sysfs attribute.
    """
    return ccw_device_attr(device_id, 'status')


def blocksize(device_id):
    """ Read and return device_id's 'blocksize' value.

    :param: device_id: string of device ccw bus_id.
    :returns: string: the device's current blocksize.
    """
    devname = device_id_to_kname(device_id)
    blkattr = 'block/%s/queue/hw_sector_size' % devname
    return ccw_device_attr(device_id, blkattr)


def disk_layout(device_id=None, devname=None):
    """ Read and return specified device "disk_layout" value.

    :param device_id: string of device ccw bus_id, defaults to None.
    :param devname: string of path to device, defaults to None.
    :returns: string: One of ['cdl', 'ldl', 'not-formatted'].
    :raises: ValueError if neither device_id or devname are valid.
             ValueError if a path to specified device does not exist.

    Note: One of either device_id or devname must be supplied.
    """
    if not any([device_id, devname]):
        raise ValueError('Must provide "device_id" or "devname"')

    if not devname:
        devname = '/dev/' + device_id_to_kname(device_id)

    if not os.path.exists(devname):
        raise ValueError('Cannot find device: "%s"' % devname)

    view = dasdview(devname)
    return view.get('extended', {}).get('format').txt


def label(device_id):
    """Read and return specified device label (VOLSER) value.

    :param: device_id: string of device ccw bus_id.
    :returns: string: devices's label (VOLSER) value.
    :raises: ValueError if it cannot get label value.
    """
    info = dasdinfo(device_id)
    if 'ID_SERIAL' not in info:
        raise ValueError('Failed to read %s label (VOLSER)' % device_id)

    return info.get('ID_SERIAL')


def needs_formatting(device_id, blocksize, disk_layout, label):
    """ Determine if the specified device_id matches the required
        format parameters.

    Note that devices that indicate they are unformatted will require
    formatting.

    :param device_id: string in X.X.XXXX format to select the dasd.
    :param blocksize: expected blocksize of the device.
    :param disk_layout: expected disk layout.
    :param label: expected label, if None, label is ignored.
    :returns: boolean, True if formatting is needed, else False.
    """
    if is_not_formatted(device_id):
        return True

    if blocksize != blocksize(device_id):
        return True

    if disk_layout != disk_layout(device_id):
        return True

    if label and label != label(device_id):
        return True

    return False


def format(devname, blocksize=None, disk_layout=None, force=None, label=None,
           keep_label=False, no_label=False, mode=None, strict=True):
    """ Format dasd device specified by kernel device name (/dev/dasda)

    :param blocksize: integer value to configure disk block size in bytes.
        Must be one of 512, 1024, 2048, 4096; defaults to 4096.
    :param disk_layout: string specify disk layout format. Must be one of
        'cdl' (Compatible Disk Layout, default) or
        'ldl' (Linux Disk Layout).
    :param force: boolean set true to skip sanity checks, defaults to False
    :param label: string to write to the volume label for identification.  If
        no label provided, a label is generated from device number of the dasd.
        Note: is interpreted as ASCII string and is automatically converted to
        uppercase and then to EBCDIC.  e.g. 'a@b\$c#' to get A@B$C#.
    :param keep_label: boolean set true to keep existing label on dasd,
        ignores label param value, defaults to False.
    :param no_label: boolean set true to skip writing label to dasd, ignores
        label and keep_label params, defaults to False.
    :param mode: string to control format mode.  Must be one of
        'full'   (Format the full disk),
        'quick'  (Format the first two tracks, default),
        'expand' (Format unformatted tracks at device end).
    :param strict: boolean which enforces that dasd device exists before
        issuing format command, defaults to True.

    :raises: RuntimeError if strict==True and devname does not exist.
    :raises: ValueError on invalid devname, blocksize, disk_layout, and mode.

    Example dadsfmt command with defaults:
      dasdformat -y --blocksize=4096 --disk_layout=cdl --mode=quick /dev/dasda
    """
    if not devname:
        raise ValueError("Invalid device name: '%s'" % devname)

    if strict and not os.path.exists(devname):
        raise RuntimeError("devname '%s' does not exist" % devname)

    if not blocksize:
        blocksize = 4096

    if not disk_layout:
        disk_layout = 'cdl'

    if not mode:
        mode = 'full'

    if no_label:
        label = None
        keep_label = None

    if keep_label:
        label = None

    valid_blocksize = [512, 1024, 2048, 4096]
    if blocksize not in valid_blocksize:
        raise ValueError("blocksize: '%s' not one of '%s'" % (blocksize,
                                                              valid_blocksize))

    valid_layouts = ['cdl', 'ldl']
    if disk_layout not in valid_layouts:
        raise ValueError("disk_layout: '%s' not one of '%s'" % (disk_layout,
                                                                valid_layouts))

    valid_modes = ['full', 'quick', 'expand']
    if mode not in valid_modes:
        raise ValueError("mode: '%s' not one of '%s'" % (mode, valid_modes))

    opts = [
        '-y',
        '--blocksize=%s' % blocksize,
        '--disk_layout=%s' % disk_layout,
        '--mode=%s' % mode
    ]
    if label:
        opts += ['--label=%s' % label]
    if keep_label:
        opts += ['--keep_label']
    if no_label:
        opts += ['--no_label']
    if force:
        opts += ['--force']

    out, err = util.subp(['dasdfmt'] + opts + [devname], capture=True)


def lsdasd(device_id=None, offline=True, rawoutput=False):
    ''' Run lsdasd command and return dict of info, optionally stdout, stderr.

    :param device_id:  string, device_id appended to command defaults to None
    :param offline: boolean, defaults True, appends --offline to command
    :param rawoutput: boolean, defaults False.  If True, returns raw output
        from lsdasd command, if False, parses and returns a dictionary

    :returns: dictionary or tuple of stdout, stderr.

    Example parsed output:
    {
     '0.0.1500': {'devid': None,
                  'eer_enabled': '0',
                  'erplog': '0',
                  'hpf': None,
                  'kname': None,
                  'paths_cuir_quiesced': None,
                  'paths_error_threshold_exceeded': None,
                  'paths_in_use': None,
                  'paths_installed': ['10', '11', '12', '13'],
                  'paths_invalid_cabling': None,
                  'paths_invalid_hpf_characteristics': None,
                  'paths_non_preferred': None,
                  'readonly': '0',
                  'status': 'offline',
                  'uid': None,
                  'use_diag': '0'},
     '0.0.1544': {'blksz': '4096',
                  'blocks': '5409180',
                  'devid': '94:0',
                  'eer_enabled': '0',
                  'erplog': '0',
                  'hpf': '1',
                  'kname': 'dasda',
                  'paths_cuir_quiesced': None,
                  'paths_error_threshold_exceeded': None,
                  'paths_in_use': ['10', '11', '12'],
                  'paths_installed': ['10', '11', '12', '13'],
                  'paths_invalid_cabling': None,
                  'paths_invalid_hpf_characteristics': None,
                  'paths_non_preferred': None,
                  'readonly': '0',
                  'size': '21129MB',
                  'status': 'active',
                  'type': 'ECKD',
                  'uid': 'IBM.750000000DXP71.1500.44',
                  'use_diag': '0'},
     '0.0.1520': {'blksz': '512',
                  'blocks': None,
                  'devid': '944',
                  'eer_enabled': '0',
                  'erplog': '0',
                  'hpf': '1',
                  'kname': 'dasdb',
                  'paths_cuir_quiesced': None,
                  'paths_error_threshold_exceeded': None,
                  'paths_in_use': ['10', '11', '12'],
                  'paths_installed': ['10', '11', '12', '13'],
                  'paths_invalid_cabling': None,
                  'paths_invalid_hpf_characteristics': None,
                  'paths_non_preferred': None,
                  'readonly': '0',
                  'size': None,
                  'status': 'n/f',
                  'type': 'ECKD',
                  'uid': 'IBM.750000000DXP71.1500.20',
                  'use_diag': '0'}
    }

    '''
    opts = ['--long']
    if offline:
        opts.append('--offline')
    if device_id:
        opts.append(device_id)

    out, err = util.subp(['lsdasd'] + opts, capture=True)

    if rawoutput:
        return (out, err)

    return {d_id: d_status for parsed in
            [_parse_lsdasd(entry)
             for entry in out.split('\n\n') if entry]
            for d_id, d_status in parsed.items()}


def _parse_lsdasd(status):
    """ Parse lsdasd --long output into a dictionary

    :param status: string of output from lsdasd --long for a single device
    :returns: dictionary of status attributes and values

    Input looks like:

    0.0.1520/dasdb/944
      status:               n/f
      type:                 ECKD
      blksz:                512
      size:
      blocks:
      use_diag:
      readonly:             0
      eer_enabled:          0
      erplog:               0
      hpf:                  1
      uid:                  IBM.750000000DXP71.1500.20
      paths_installed:      10 11 12 13
      paths_in_use:         10 11 12
      paths_non_preferred:
      paths_invalid_cabling:
      paths_cuir_quiesced:
      paths_invalid_hpf_characteristics:
      paths_error_threshold_exceeded:

    Output looks like:

    {'0.0.1520': {'blksz': '512',
                  'blocks': None,
                  'devid': '944',
                  'eer_enabled': '0',
                  'erplog': '0',
                  'hpf': '1',
                  'kname': 'dasdb',
                  'paths_cuir_quiesced': None,
                  'paths_error_threshold_exceeded': None,
                  'paths_in_use': ['10', '11', '12'],
                  'paths_installed': ['10', '11', '12', '13'],
                  'paths_invalid_cabling': None,
                  'paths_invalid_hpf_characteristics': None,
                  'paths_non_preferred': None,
                  'readonly': '0',
                  'size': None,
                  'status': 'n/f',
                  'type': 'ECKD',
                  'uid': 'IBM.750000000DXP71.1500.20',
                  'use_diag': '0'}}
    """
    if not status or not isinstance(status, util.string_types):
        raise ValueError('Invalid value for argument "status": ' + str(status))

    # XXX: lsdasd --offline --long on offline dasd is 15 lines
    if len(status.splitlines()) < 15:
        raise ValueError('Status input has fewer than 15 lines, cannot parse')

    parsed = {}
    firstline = status.splitlines()[0]
    device_id = kname = devid = None
    if '/' in firstline:
        device_id, kname, devid = firstline.split('/')
    else:
        device_id = firstline.strip()

    parsed.update({'kname': kname, 'devid': devid})
    status = status.splitlines()[1:]
    for line in status:
        if not line:
            continue
        key, value = map(lambda x: x.strip(),
                         line.lstrip().split(':'))
        if not value:
            value = None
        else:
            if ' ' in value:
                value = value.split()

        parsed.update({key: value})

    return {device_id: parsed}


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
    if not device_id:
        raise ValueError("Invalid device_id: '%s'" % device_id)

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


def _parse_dasdview(dasdview_output):
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

    def _mkdasdvalue(value):
        v_hex = value[0].replace('hex ', '0x')
        v_dec = int(value[1].replace('dec ', ''))
        v_str = None
        if len(value) == 3:
            v_str = info_key_map.get(value[2], value[2])

        return Dasdvalue(v_hex, v_dec, v_str)

    def _map_strip(value):
        v_type = type(value)
        return v_type(map(lambda x: x.strip(), value))

    def _parse_output(output):
        parsed = {}
        prev_key = None
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
                    value = _mkdasdvalue(value)
                elif value and '  ':
                    # characteristics : XXXXXXX XXXXXXX  XXXXXXXX XXXXXXX
                    #                   YYYYYYY YYYYYYY  YYYYYYYY YYYYYYY
                    # convert to list of strings.
                    value = value.lstrip().replace('  ', ' ').split(' ')
                else:
                    value = None
            else:
                key = prev_key

            # extend lists for existing keys
            if key in parsed and type(value) == list:
                parsed[key].extend(value)
            else:
                parsed.update({key: value})

        return parsed

    lines = dasdview_output.splitlines()
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


# vi: ts=4 expandtab syntax=python
