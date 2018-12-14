# This file is part of curtin. See LICENSE file for copyright and license info.

import collections
import os
import re
from curtin import util

Dasdvalue = collections.namedtuple('Dasdvalue', ['hex', 'dec', 'txt'])


def get_status(device_id=None):
    """Query DASD status via lzdasd command.

    :param device_id: filter results for device_id, default None lists all.
    :returns: dictionary of status for each detected dasd device

    Example output:
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
    """
    lsdasd_output = lsdasd(device_id=device_id)
    return {d_id: d_status for parsed in
            [_parse_lsdasd(entry)
             for entry in lsdasd_output.split('\n\n') if entry]
            for d_id, d_status in parsed.items()}


def lsdasd(device_id=None, offline=True):
    ''' Run lsdasd command and return its standard output.

    :param device_id:  string, device_id appended to command defaults to None
    :param offline: boolean, defaults True, appends --offline to command

    :returns: string of standard output from constructed lsdasd command
    '''
    opts = ['--long']
    if offline:
        opts.append('--offline')
    if device_id:
        opts.append(device_id)

    out, _ = util.subp(['lsdasd'] + opts, capture=True)

    return out


def dasdinfo(device_id):
    ''' Run dasdinfo command and return the exported values.

    :param: device_id:  string, device_id of the dasd device to query
    :returns: dictionary of udev key=value pairs
    :raises: ValueError on None-ish device_id
    :raises: ProcessExecutionError if dasdinfo returns non-zero

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

    out, _ = util.subp(
        ['dasdinfo', '--all', '--export',
         '--busid=%s' % device_id], capture=True)

    return util.load_shell_content(out)


def dasdview(devname):
    ''' Run dasdview on devname and return dictionary of data

    dasdview --extended has 3 sections
    general (2, 6), geometry (8:12), extended (14:)

    '''
    if not os.path.exists(devname):
        raise ValueError("Invalid dasd device name: '%s'" % devname)

    out, _ = util.subp(['dasdview', '--extended', devname], capture=True)

    return out


def _parse_dasdview(dasdview_output):
    """ Parse dasdview --extended output into a dictionary

    Input:

    Output:

    info = {
        'general': {
            'device_node':
            'busid':
            'type':
            'device_type':},
        'geometry': {
            'number_of_cylinders':,
            'tracks_per_cylinder':,
            'blocks_per_track':,
            'blocksize':},
        'extended': {
            'real_device_number':,
            'subchannel_identifier':,
            'cu_type_senseid':,
            'cu_model_senseid':,
            'device_type_senseid':,
            'device_model_senseid':,
            'open_count':,
            'req_queue_len':,
            'chanq_len':,
            'status':,
            'label_block':,
            'fba_layout':,
            'characteristics_size':,
            'confdata_size':,
            'format':,
            'features',
            'characteristics':,
            'configuration_data':,}
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
        for line in status:
            if not line:
                continue
            if ':' in line:
                key, value = map(lambda x: x.strip(),
                                 line.lstrip().split(':'))
                # normalize lvalue
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

    info = {
        'general': _parse_output(general_output),
        'geometry': _parse_output(geometry_output),
        'extended': _parse_output(extended_output),
    }
    return info


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


def is_valid_device_id(device_id, ):
    """ validate device_id string.

    :param device_id: string representing a s390 ccs device in the format
       <channel subsystem number>.<data source number>.<device id>
       e.g. 0.0.74fc

    :returns boolean: True if valid, False otherwise.
    """
    if not device_id or not isinstance(device_id, util.string_types):
        raise ValueError("device_id parameter value invalid: '%s'" % device_id)

    if device_id.count('.') != 2:
        raise ValueError(
            "device_id format invalid, requires two '.' chars: %s" % device_id)

    # maxsplit=2
    (css, dsn, dev) = device_id.split('.')

    if not all([css, dsn, dev]):
        raise ValueError(
            "device_id format invalid, must be X.X.XXXX: '%s'" % device_id)

    if int(css) not in range(0, 256):
        raise ValueError("device_id css invalid, not in 0-256: '%s'" % css)

    if int(dsn) not in range(0, 256):
        raise ValueError("device_id dsn invalid, not in 0-256: '%s'" % dsn)

    if not re.match(r'^[a-f0-9]+$', dev.lower()):
        raise ValueError("device number invalid: not in 0xFFFF: '%s'" % dev)


def valid_device_id(device_id):
    """Return a boolean indicating if device_id is valid."""
    try:
        is_valid_device_id(device_id)
        return True
    except ValueError:
        return False


def ccw_device_attr(device_id, attr):
    attrdata = ''
    if not valid_device_id(device_id):
        raise ValueError("Invalid device_id:'%s'" % device_id)

    sysfs_attr_path = '/sys/bus/ccw/devices/%s/%s' % (device_id, attr)
    if os.path.isfile(sysfs_attr_path):
        attrdata = util.load_file(sysfs_attr_path).strip()

    return attrdata


def is_active(device_id):
    return ccw_device_attr(device_id, 'status') == "online"


def is_alias(device_id):
    return ccw_device_attr(device_id, 'alias') == "1"


def is_not_formatted(device_id, status=None):
    return ccw_device_attr(device_id, 'status') == "unformatted"


def is_online(device_id):
    return ccw_device_attr(device_id, 'online') == "1"


def device_id_to_kname(device_id):
    if not valid_device_id(device_id):
        raise ValueError("Invalid device_id:'%s'" % device_id)

    if not is_online(device_id):
        raise RuntimeError(
            'Cannot determine dasd kname for offline device: %s' % device_id)

    blockdir = '/sys/bus/ccw/devices/%s/block' % device_id
    if not os.path.isdir(blockdir):
        raise RuntimeError('Unexpectedly not a directory: %s' % blockdir)

    [dasd_kname] = os.listdir(blockdir)

    return dasd_kname


def kname_to_device_id(devname):
    """ Return the device_id of a dasd kname specified """
    pass


def status(device_id):
    return ccw_device_attr(device_id, 'status')


def blocksize(device_id):
    devname = device_id_to_kname(device_id)
    blkattr = 'block/%s/queue/hw_sector_size' % devname
    return ccw_device_attr(device_id, blkattr)


def disk_layout(device_id=None, devname=None):
    if not any(device_id, devname):
        raise ValueError('Must provide "device_id" or "devname"')

    if not devname:
        devname = '/dev/' + device_id_to_kname(device_id)

    if not os.path.exists(devname):
        raise ValueError('Cannot find device: "%s"' % devname)

    info = dasdinfo(devname)
    return info.get('extended', {}).get('format').txt


def needs_formatting(device_id, blocksize, disk_layout, label):
    """ determine if the specified device_id matches the required
        format parameters.

    Note that devices that indicate they are unformatted will require
    formatting.

    :param device_id: string in X.X.XXXX format to select the dasd
    :param blocksize: expected blocksize of the device
    :param disk_layout: expected disk layout
    :param label: expected label, if None, label is ignored
    :returns: boolean, True if formatting is needed, else False
    """

    if is_not_formatted(device_id):
        return True

    if blocksize != blocksize(device_id):
        return True

    if disk_layout != disk_layout(device_id):
        return True

    if label != label(device_id):
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
        mode = 'quick'

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

# vi: ts=4 expandtab syntax=python
