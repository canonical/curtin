# This file is part of curtin. See LICENSE file for copyright and license info.

import os
from curtin import util


def get_status(bus_id=None):
    """Query DASD status via lzdasd command.

    :param bus_id: filter results for specific bus_id, default None lists all.
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
    lsdasd_output = lsdasd(bus_id=bus_id)
    return {d_id: d_status for parsed in
            [_parse_lsdasd(entry)
             for entry in lsdasd_output.split('\n\n') if entry]
            for d_id, d_status in parsed.items()}


def lsdasd(bus_id=None, offline=True):
    ''' Run lsdasd command and return its standard output.

    :param bus_id:  string, bus_id appended to command defaults to None
    :param offline: boolean, defaults True, appends --offline to command

    :returns: string of standard output from constructed lsdasd command
    '''
    opts = ['--long']
    if offline:
        opts.append('--offline')
    if bus_id:
        opts.append(bus_id)

    out, _ = util.subp(['lsdasd'] + opts, capture=True)

    return out


def dasdinfo(bus_id):
    ''' Run dasdinfo command and return the exported values.

    :param: bus_id:  string, bus_id of the dasd device to query
    :returns: dictionary of udev key=value pairs
    :raises: ValueError on None-ish bus_id
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
    if not bus_id:
        raise ValueError("Invalid bus_id: '%s'" % bus_id)

    out, _ = util.subp(
        ['dasdinfo', '--all', '--export', '--busid=%s' % bus_id], capture=True)

    return util.load_shell_content(out)


def dasdview(devname):
    ''' Run dasdview on devname and return dictionary of data '''


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
    bus_id = kname = devid = None
    if '/' in firstline:
        bus_id, kname, devid = firstline.split('/')
    else:
        bus_id = firstline.strip()

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

    return {bus_id: parsed}


def is_active(bus_id, status=None):
    if not status:
        status = get_status(bus_id)

    try:
        return status.get(bus_id).get('status') == 'active'
    except AttributeError:
        raise ValueError('Invalid status input: ' + status)


def is_offline(bus_id, status=None):
    if not status:
        status = get_status(bus_id)

    try:
        return status.get(bus_id).get('status') == 'offline'
    except AttributeError:
        raise ValueError('Invalid status input: ' + status)


def is_not_formatted(bus_id, status=None):
    if not status:
        status = get_status(bus_id)

    try:
        return status.get(bus_id).get('status') == 'n/f'
    except AttributeError:
        raise ValueError('Invalid status input: ' + status)


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
