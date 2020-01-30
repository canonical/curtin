# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.distro import DISTROS
from curtin.block import iscsi


def storage_config_required_packages(storage_config, mapping):
    """Read storage configuration dictionary and determine
       which packages are required for the supplied configuration
       to function.  Return a list of packaged to install.
    """

    if not storage_config or not isinstance(storage_config, dict):
        raise ValueError('Invalid storage configuration.  '
                         'Must be a dict:\n %s' % storage_config)

    if not mapping or not isinstance(mapping, dict):
        raise ValueError('Invalid storage mapping.  Must be a dict')

    if 'storage' in storage_config:
        storage_config = storage_config.get('storage')

    needed_packages = []

    # get reqs by device operation type
    dev_configs = set(operation['type']
                      for operation in storage_config['config'])

    for dev_type in dev_configs:
        if dev_type in mapping:
            needed_packages.extend(mapping[dev_type])

    # for disks with path: iscsi: we need iscsi tools
    iscsi_vols = iscsi.get_iscsi_volumes_from_config(storage_config)
    if len(iscsi_vols) > 0:
        needed_packages.extend(mapping['iscsi'])

    # for any format operations, check the fstype and
    # determine if we need any mkfs tools as well.
    format_configs = set([operation['fstype']
                         for operation in storage_config['config']
                         if operation['type'] == 'format'])
    for format_type in format_configs:
        if format_type in mapping:
            needed_packages.extend(mapping[format_type])

    return needed_packages


def detect_required_packages_mapping(osfamily=DISTROS.debian):
    """Return a dictionary providing a versioned configuration which maps
       storage configuration elements to the packages which are required
       for functionality.

       The mapping key is either a config type value, or an fstype value.

    """
    distro_mapping = {
        DISTROS.debian: {
            'bcache': ['bcache-tools'],
            'btrfs': ['^btrfs-(progs|tools)$'],
            'ext2': ['e2fsprogs'],
            'ext3': ['e2fsprogs'],
            'ext4': ['e2fsprogs'],
            'jfs': ['jfsutils'],
            'iscsi': ['open-iscsi'],
            'lvm_partition': ['lvm2'],
            'lvm_volgroup': ['lvm2'],
            'ntfs': ['ntfs-3g'],
            'raid': ['mdadm'],
            'reiserfs': ['reiserfsprogs'],
            'xfs': ['xfsprogs'],
            'zfsroot': ['zfsutils-linux', 'zfs-initramfs'],
            'zfs': ['zfsutils-linux', 'zfs-initramfs'],
            'zpool': ['zfsutils-linux', 'zfs-initramfs'],
        },
        DISTROS.redhat: {
            'bcache': [],
            'btrfs': ['btrfs-progs'],
            'ext2': ['e2fsprogs'],
            'ext3': ['e2fsprogs'],
            'ext4': ['e2fsprogs'],
            'jfs': [],
            'iscsi': ['iscsi-initiator-utils'],
            'lvm_partition': ['lvm2'],
            'lvm_volgroup': ['lvm2'],
            'ntfs': [],
            'raid': ['mdadm'],
            'reiserfs': [],
            'xfs': ['xfsprogs'],
            'zfsroot': [],
            'zfs': [],
            'zpool': [],
        },
    }
    if osfamily not in distro_mapping:
        raise ValueError('No block package mapping for distro: %s' % osfamily)

    return {1: {'handler': storage_config_required_packages,
                'mapping': distro_mapping.get(osfamily)}}


# vi: ts=4 expandtab syntax=python
