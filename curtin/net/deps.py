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
        netconf = network_config['config']
        dev_configs = set() if netconf == 'disabled' else set(
            device['type'] for device in netconf)

    else:
        # v2 has no config key
        dev_configs = set()
        for cfgtype, cfg in network_config.items():
            if cfgtype == 'version':
                continue
            dev_configs.add(cfgtype)
            # subkeys under the type may trigger package adds
            for entry, entry_cfg in cfg.items():
                if entry_cfg.get('renderer'):
                    dev_configs.add(entry_cfg.get('renderer'))
                else:
                    for sub_entry, sub_cfg in entry_cfg.items():
                        dev_configs.add(sub_entry)

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
            'openvswitch': ['openvswitch-switch'],
            'networkd': ['systemd'],
            'NetworkManager': ['network-manager'],
            'vlan': ['vlan'],
            'vlans': ['vlan']},
        DISTROS.redhat: {
            'bond': [],
            'bonds': [],
            'bridge': [],
            'bridges': [],
            'openvswitch': ['openvswitch-switch'],
            'vlan': [],
            'vlans': []},
        DISTROS.suse: {
            'bond': [],
            'bonds': [],
            'bridge': ['bridge-utils'],
            'bridges': ['bridge-utils'],
            'openvswitch': ['openvswitch-switch'],
            'vlan': ['vlan'],
            'vlans': ['vlan']},
    }
    if osfamily not in distro_mapping:
        raise ValueError('No net package mapping for distro: %s' % osfamily)

    return {1: {'handler': network_config_required_packages,
                'mapping': distro_mapping.get(osfamily)},
            2: {'handler': network_config_required_packages,
                'mapping': distro_mapping.get(osfamily)}}


# vi: ts=4 expandtab syntax=python
