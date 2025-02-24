# This file is part of curtin. See LICENSE file for copyright and license info.

_uuid_pattern = (
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_path_dev = r'^/dev/[^/]+(/[^/]+)*$'
_path_nondev = r'(^/$|^(/[^/]+)+$)'
_fstypes = ['btrfs', 'ext2', 'ext3', 'ext4', 'f2fs', 'fat', 'fat12', 'fat16',
            'fat32', 'iso9660', 'vfat', 'jfs', 'ntfs', 'reiserfs', 'swap',
            'xfs', 'zfsroot']
_ptable_unsupported = 'unsupported'
_ptables = ['dos', 'gpt', 'msdos', 'vtoc']
_ptables_valid = _ptables + [_ptable_unsupported]

definitions = {
    'id': {'type': 'string'},
    'ref_id': {'type': 'string'},
    'devices': {'type': 'array', 'items': {'$ref': '#/definitions/ref_id'}},
    'name': {'type': 'string'},
    'preserve': {'type': 'boolean'},
    'ptable': {'type': 'string', 'enum': _ptables_valid},
    'size': {'type': ['string', 'number'],
             'minimum': 1,
             'pattern': r'^([1-9]\d*(.\d+)?|\d+.\d+)(K|M|G|T)?B?'},
    'wipe': {
        'type': 'string',
        'enum': ['random', 'superblock', 'superblock-recursive', 'zero'],
    },
    'uuid': {
        'type': 'string',
        'pattern': _uuid_pattern,
    },
    'params': {
        'type': 'object',
        'patternProperties': {
            r'^.*$': {
                'oneOf': [
                    {'type': 'boolean'},
                    {'type': 'integer'},
                    {'type': 'null'},
                    {'type': 'string'},
                ],
            },
        },
    },
}

BCACHE = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-BCACHE',
    'title': 'curtin storage configuration for a bcache device.',
    'description': ('Declarative syntax for specifying bcache device.'),
    'definitions': definitions,
    'required': ['id', 'type'],
    'anyOf': [
        {'required': ['backing_device']},
        {'required': ['cache_device']}],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'backing_device': {'$ref': '#/definitions/ref_id'},
        'cache_device': {'$ref': '#/definitions/ref_id'},
        'name': {'$ref': '#/definitions/name'},
        'preserve': {'$ref': '#/definitions/preserve'},
        'type': {'const': 'bcache'},
        'cache_mode': {
            'type': ['string'],
            'enum': ['writethrough', 'writeback', 'writearound', 'none'],
        },
        'path': {'type': 'string', 'pattern': _path_dev},
    },
}
DASD = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-DASD',
    'title': 'curtin storage configuration for dasds',
    'description': (
        'Declarative syntax for specifying a dasd device.'),
    'definitions': definitions,
    'required': ['id', 'type', 'device_id'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'name': {'$ref': '#/definitions/name'},
        'preserve': {'$ref': '#/definitions/preserve'},
        'type': {'const': 'dasd'},
        'blocksize': {
            'type': ['integer', 'string'],
            'oneOf': [{'enum': [512, 1024, 2048, 4096]},
                      {'enum': ['512', '1024', '2048', '4096']}],
        },
        'device_id': {'type': 'string'},
        'label': {'type': 'string', 'maxLength': 6},
        'mode': {
            'type': ['string'],
            'enum': ['expand', 'full', 'quick'],
        },
        'disk_layout': {
            'type': ['string'],
            'enum': ['cdl', 'ldl', 'not-formatted'],
        },
    },
}
DISK = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-DISK',
    'title': 'curtin storage configuration for disks',
    'description': (
        'Declarative syntax for specifying disks and partition format.'),
    'definitions': definitions,
    'required': ['id', 'type'],
    'anyOf': [
        {'required': ['serial']},
        {'required': ['wwn']},
        {'required': ['path']}],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'name': {'$ref': '#/definitions/name'},
        'multipath': {'type': 'string'},
        'device_id': {'type': 'string'},
        'preserve': {'$ref': '#/definitions/preserve'},
        'wipe': {'$ref': '#/definitions/wipe'},
        'type': {'const': 'disk'},
        'ptable': {'$ref': '#/definitions/ptable'},
        'serial': {'type': 'string'},
        'path': {
            'type': 'string',
            'oneOf': [
                {'pattern': _path_dev},
                {'pattern': r'^iscsi:.*'}],
        },
        'model': {'type': 'string'},
        'wwn': {
            'type': 'string',
            'oneOf': [
                {'pattern': r'^0x(\d|[a-zA-Z])+'},
                {'pattern': r'^(nvme|eui|uuid)\.([-0-9a-zA-Z])+'}],
        },
        'grub_device': {
            'type': ['boolean', 'integer'],
            'minimum': 0,
            'maximum': 1
        },
        'nvme_controller': {'$ref': '#/definitions/ref_id'},
    },
}
DM_CRYPT = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-DMCRYPT',
    'title': 'curtin storage configuration for creating encrypted volumes',
    'description': ('Declarative syntax for specifying encrypted volumes.'),
    'definitions': definitions,
    'required': ['id', 'type', 'volume', 'dm_name'],
    'oneOf': [
        {'required': ['key']},
        {'required': ['keyfile']}],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'dm_name': {'$ref': '#/definitions/name'},
        'volume': {'$ref': '#/definitions/ref_id'},
        'key': {'$ref': '#/definitions/id'},
        'keyfile': {'$ref': '#/definitions/id'},
        'path': {'type': 'string', 'pattern': _path_dev},
        'preserve': {'$ref': '#/definitions/preserve'},
        'type': {'const': 'dm_crypt'},
    },
}
FORMAT = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-FORMAT',
    'title': 'curtin storage configuration for formatting filesystems',
    'description': ('Declarative syntax for specifying filesystem layout.'),
    'definitions': definitions,
    'required': ['id', 'type', 'volume', 'fstype'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'name': {'$ref': '#/definitions/name'},
        'preserve': {'$ref': '#/definitions/preserve'},
        'uuid': {'$ref': '#/definitions/uuid'},    # XXX: This is not used
        'type': {'const': 'format'},
        'fstype': {'type': 'string'},
        'label': {'type': 'string'},
        'volume': {'$ref': '#/definitions/ref_id'},
        'extra_options': {'type': 'array', 'items': {'type': 'string'}},
    },
    'anyOf': [
        # XXX: Accept vmtest values?
        {'properties': {'fstype': {'pattern': r'^__.*__$'}}},
        {'properties': {'fstype': {'enum': _fstypes}}},
        {
            'properties': {'preserve': {'enum': [True]}},
            'required': ['preserve']  # this looks redundant but isn't
        }
    ]
}
LVM_PARTITION = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-LVMPARTITION',
    'title': 'curtin storage configuration for formatting lvm logical vols',
    'description': ('Declarative syntax for specifying lvm logical vols.'),
    'definitions': definitions,
    'required': ['id', 'type', 'volgroup', 'name'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'name': {'$ref': '#/definitions/name'},
        'preserve': {'type': 'boolean'},
        'size': {'$ref': '#/definitions/size'},  # XXX: This is not used
        'type': {'const': 'lvm_partition'},
        'volgroup': {'$ref': '#/definitions/ref_id'},
        'path': {'type': 'string', 'pattern': _path_dev},
    },
}
LVM_VOLGROUP = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-LVMVOLGROUP',
    'title': 'curtin storage configuration for formatting lvm volume groups',
    'description': ('Declarative syntax for specifying lvm volgroup layout.'),
    'definitions': definitions,
    'required': ['id', 'type', 'devices', 'name'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'devices': {'$ref': '#/definitions/devices'},
        'name': {'$ref': '#/definitions/name'},
        'preserve': {'type': 'boolean'},
        'uuid': {'$ref': '#/definitions/uuid'},    # XXX: This is not used
        'type': {'const': 'lvm_volgroup'},
    },
}
MOUNT = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-MOUNT',
    'title': 'curtin storage configuration for mounts',
    'description': ('Declarative syntax for specifying devices mounts.'),
    'definitions': definitions,
    'required': ['id', 'type'],
    'anyOf': [
        {'required': ['path']},
        {'required': ['device']},
        {'required': ['spec']}],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'type': {'const': 'mount'},
        'path': {
            'type': 'string',
            'oneOf': [
                {'pattern': _path_nondev},
                {'enum': ['none']},
            ],
        },
        'device': {'$ref': '#/definitions/ref_id'},
        'fstype': {'type': 'string'},
        'options': {
            'type': 'string',
            'oneOf': [
                {'pattern': r'\S+(,\S+)*'},
                {'enum': ['']},
            ],
        },
        'spec': {'type': 'string'},  # XXX: Tighten this to fstab fs_spec
        'freq': {'type': ['integer', 'string'],
                 'pattern': r'[0-9]'},
        'passno': {'type': ['integer', 'string'],
                   'pattern': r'[0-9]'},
    },
}
NVME = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-NVME',
    'title': 'curtin storage configuration for NVMe controllers',
    'description': ('Declarative syntax for specifying NVMe controllers.'),
    'definitions': definitions,
    'required': ['id', 'type', 'transport'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'type': {'const': 'nvme_controller'},
        'transport': {'type': 'string'},
        'tcp_port': {'type': 'integer'},
        'tcp_addr': {'type': 'string'},
    },
}
PARTITION = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-PARTITION',
    'title': 'curtin storage configuration for partitions',
    'description': ('Declarative syntax for specifying partition layout.'),
    'definitions': definitions,
    'required': ['id', 'type', 'device', 'size'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'multipath': {'type': 'string'},
        # Permit path to device as output.
        # This value is ignored for input.
        'path': {'type': 'string', 'pattern': _path_dev},
        'name': {'$ref': '#/definitions/name'},
        'offset': {'$ref': '#/definitions/size'},  # XXX: This is not used
        'resize': {'type': 'boolean'},
        'preserve': {'$ref': '#/definitions/preserve'},
        'size': {'$ref': '#/definitions/size'},
        'uuid': {'$ref': '#/definitions/uuid'},    # XXX: This is not used
        'wipe': {'$ref': '#/definitions/wipe'},
        'type': {'const': 'partition'},
        'number': {'type': ['integer', 'string'],
                   'pattern': r'[1-9][0-9]*',
                   'minimum': 1},
        'device': {'$ref': '#/definitions/ref_id'},
        'flag': {'type': 'string',
                 'enum': ['bios_grub', 'boot', 'extended', 'home', 'linux',
                          'logical', 'lvm', 'mbr', 'msftres', 'prep', 'raid',
                          'swap', '']},
        'partition_type': {'type': 'string',
                           'oneOf': [
                               {'pattern': r'^0x[0-9a-fA-F]{1,2}$'},
                               {'$ref': '#/definitions/uuid'},
                               ]},
        'partition_name': {'$ref': '#/definitions/name'},
        'grub_device': {
            'type': ['boolean', 'integer'],
            'minimum': 0,
            'maximum': 1
        },
    }
}
RAID = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-RAID',
    'title': 'curtin storage configuration for a RAID.',
    'description': ('Declarative syntax for specifying RAID.'),
    'definitions': definitions,
    'required': ['id', 'type', 'name', 'raidlevel'],
    'type': 'object',
    'additionalProperties': False,
    'oneOf': [
        {'required': ['devices']},
        {'required': ['container']},
    ],
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'devices': {'$ref': '#/definitions/devices'},
        'name': {'$ref': '#/definitions/name'},
        'mdname': {'$ref': '#/definitions/name'},  # XXX: Docs need updating
        'metadata': {'type': ['string', 'number']},
        'path': {'type': 'string', 'pattern': _path_dev},
        'preserve': {'$ref': '#/definitions/preserve'},
        'ptable': {'$ref': '#/definitions/ptable'},
        'wipe': {'$ref': '#/definitions/wipe'},
        'spare_devices': {'$ref': '#/definitions/devices'},
        'container': {'$ref': '#/definitions/id'},
        'type': {'const': 'raid'},
        'raidlevel': {
            'type': ['integer', 'string'],
            'oneOf': [
                {'enum': [0, 1, 4, 5, 6, 10]},
                {'enum': ['container',
                          'raid0', 'linear', '0',
                          'raid1', 'mirror', 'stripe', '1',
                          'raid4', '4',
                          'raid5', '5',
                          'raid6', '6',
                          'raid10', '10']},  # XXX: Docs need updating
            ],
        },
    },
}
ZFS = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-ZFS',
    'title': 'curtin storage configuration for a ZFS dataset.',
    'description': ('Declarative syntax for specifying a ZFS dataset.'),
    'definitions': definitions,
    'required': ['id', 'type', 'pool', 'volume'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'pool': {'$ref': '#/definitions/ref_id'},
        'properties': {'$ref': '#/definitions/params'},
        'volume': {'$ref': '#/definitions/name'},
        'type': {'const': 'zfs'},
    },
}
ZPOOL = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'CURTIN-ZPOOL',
    'title': 'curtin storage configuration for a ZFS pool.',
    'description': ('Declarative syntax for specifying a ZFS pool.'),
    'definitions': definitions,
    'required': ['id', 'type', 'pool', 'vdevs'],
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'id': {'$ref': '#/definitions/id'},
        'vdevs': {'$ref': '#/definitions/devices'},
        'pool': {'$ref': '#/definitions/name'},
        'pool_properties': {'$ref': '#/definitions/params'},
        'fs_properties': {'$ref': '#/definitions/params'},
        'default_features': {'type': 'boolean'},
        'mountpoint': {
            'type': 'string',
            'oneOf': [
                {'pattern': _path_nondev},
                {'enum': ['none']},
            ],
        },
        'type': {'const': 'zpool'},
    },
}

# vi: ts=4 expandtab syntax=python
