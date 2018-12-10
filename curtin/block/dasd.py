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


def format(bus_id, blocksize=None, disk_layout=None, force=None, label=None,
           mode=None):
    """ Format dasd device specified by bus_id

    :param blocksize: integer value to configure disk block size in bytes.
        Must be one of 512, 1024, 2048, 4096; defaults to 4096.
    :param disk_layout: string specify disk layout format. Must be one of
        'cdl' (Compatible Disk Layout, default) or
        'ldl' (Linux Disk Layout).
    :param force: boolean set true to skip sanity checks, defaults to False
    :param label: string to write to the volume label for identification
    :param mode: string to control format mode.  Must be one of
        'full'   (Format the full disk, default; slow),
        'quick'  (Format the first two tracks),
        'expand' (Format unformatted tracks at device end).
    """
    pass
