# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.distro import DISTROS


def network_config_required_packages(network_config, mapping=None):

    if network_config is None:
        network_config = {}

    if not isinstance(network_config, dict):
        raise ValueError('Invalid network configuration.  Must be a dict')

    if mapping is None:
        mapping = {}

    if not isinstance(mapping, dict):
        raise ValueError('Invalid network mapping.  Must be a dict')

    # allow top-level 'network' key
    if 'network' in network_config:
        network_config = network_config.get('network')

    # v1 has 'config' key and uses type: devtype elements
    if 'config' in network_config:
        dev_configs = set(device['type']
                          for device in network_config['config'])
    else:
        # v2 has no config key
        dev_configs = set(cfgtype for (cfgtype, cfg) in
                          network_config.items() if cfgtype not in ['version'])

    needed_packages = []
    for dev_type in dev_configs:
        if dev_type in mapping:
            needed_packages.extend(mapping[dev_type])

    return needed_packages


def detect_required_packages_mapping(osfamily=DISTROS.debian):
    """Return a dictionary providing a versioned configuration which maps
       network configuration elements to the packages which are required
       for functionality.
    """
    # keys ending with 's' are v2 values
    distro_mapping = {
        DISTROS.debian: {
            'bond': ['ifenslave'],
            'bonds': ['ifenslave'],
            'bridge': ['bridge-utils'],
            'bridges': ['bridge-utils'],
            'vlan': ['vlan'],
            'vlans': ['vlan']},
        DISTROS.redhat: {
            'bond': [],
            'bonds': [],
            'bridge': [],
            'bridges': [],
            'vlan': [],
            'vlans': []},
    }
    if osfamily not in distro_mapping:
        raise ValueError('No net package mapping for distro: %s' % osfamily)

    return {1: {'handler': network_config_required_packages,
                'mapping': distro_mapping.get(osfamily)},
            2: {'handler': network_config_required_packages,
                'mapping': distro_mapping.get(osfamily)}}


# vi: ts=4 expandtab syntax=python
