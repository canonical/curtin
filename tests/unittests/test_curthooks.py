import unittest
from curtin.commands import curthooks


class TestDetectRequiredPackages(unittest.TestCase):
    config = {
        'storage': {
            1: {
                'bcache': {
                    'type': 'bcache', 'name': 'bcache0', 'id': 'cache0',
                    'backing_device': 'sda3', 'cache_device': 'sdb'},
                'lvm_partition': {
                    'id': 'lvol1', 'name': 'lv1', 'volgroup': 'vg1',
                    'type': 'lvm_partition'},
                'lvm_volgroup': {
                    'id': 'vol1', 'name': 'vg1', 'devices': ['sda', 'sdb'],
                    'type': 'lvm_volgroup'},
                'raid': {
                    'id': 'mddevice', 'name': 'md0', 'type': 'raid',
                    'raidlevel': 5, 'devices': ['sda1', 'sdb1', 'sdc1']},
                'ext2': {
                    'id': 'format0', 'fstype': 'ext2', 'type': 'format'},
                'ext3': {
                    'id': 'format1', 'fstype': 'ext3', 'type': 'format'},
                'ext4': {
                    'id': 'format2', 'fstype': 'ext4', 'type': 'format'},
                'btrfs': {
                    'id': 'format3', 'fstype': 'btrfs', 'type': 'format'},
                'xfs': {
                    'id': 'format4', 'fstype': 'xfs', 'type': 'format'}}
        },
        'network': {
            1: {
                'bond': {
                    'name': 'bond0', 'type': 'bond',
                    'bond_interfaces': ['interface0', 'interface1'],
                    'params': {'bond-mode': 'active-backup'},
                    'subnets': [
                        {'type': 'static', 'address': '10.23.23.2/24'},
                        {'type': 'static', 'address': '10.23.24.2/24'}]},
                'vlan': {
                    'id': 'interface1.2667', 'mtu': 1500, 'name':
                    'interface1.2667', 'type': 'vlan', 'vlan_id': 2667,
                    'vlan_link': 'interface1',
                    'subnets': [{'address': '10.245.184.2/24',
                                 'dns_nameservers': [], 'type': 'static'}]},
                'bridge': {
                    'name': 'br0', 'bridge_interfaces': ['eth0', 'eth1'],
                    'type': 'bridge', 'params': {
                        'bridge_stp': 'off', 'bridge_fd': 0,
                        'bridge_maxwait': 0},
                    'subnets': [
                        {'type': 'static', 'address': '192.168.14.2/24'},
                        {'type': 'static', 'address': '2001:1::1/64'}]}},
            2: {
                'vlan': {
                    'vlans': {
                        'en-intra': {'id': 1, 'link': 'eno1', 'dhcp4': 'yes'},
                        'en-vpn': {'id': 2, 'link': 'eno1'}}},
                'bridge': {
                    'bridges': {
                        'br0': {
                            'interfaces': ['wlp1s0', 'switchports'],
                            'dhcp4': True}}}}
        },
    }

    def _fmt_config(self, config_items):
        res = {}
        for item, item_confs in config_items.items():
            version = item_confs['version']
            res[item] = {'version': version}
            if version == 1:
                res[item]['config'] = [self.config[item][version][i]
                                       for i in item_confs['items']]
            elif version == 2 and item == 'network':
                for cfg_item in item_confs['items']:
                    res[item].update(self.config[item][version][cfg_item])
            else:
                raise NotImplementedError
        return res

    def _test_req_mappings(self, req_mappings):
        for (config_items, expected_reqs) in req_mappings:
            config = self._fmt_config(config_items)
            actual_reqs = curthooks.detect_required_packages(config)
            self.assertEqual(set(actual_reqs), set(expected_reqs),
                             'failed for config: {}'.format(config_items))

    def test_storage_v1_detect(self):
        self._test_req_mappings((
            ({'storage': {
                'version': 1,
                'items': ('lvm_partition', 'lvm_volgroup', 'btrfs', 'xfs')}},
             ('lvm2', 'xfsprogs', 'btrfs-tools')),
            ({'storage': {
                'version': 1,
                'items': ('raid', 'bcache', 'ext3', 'xfs')}},
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'xfsprogs')),
            ({'storage': {
                'version': 1,
                'items': ('raid', 'lvm_volgroup', 'lvm_partition', 'ext3',
                          'ext4', 'btrfs')}},
             ('lvm2', 'mdadm', 'e2fsprogs', 'btrfs-tools')),
            ({'storage': {
                'version': 1,
                'items': ('bcache', 'lvm_volgroup', 'lvm_partition', 'ext2')}},
             ('bcache-tools', 'lvm2', 'e2fsprogs')),
        ))

    def test_network_v1_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 1,
                'items': ('bridge',)}},
             ('bridge-utils',)),
            ({'network': {
                'version': 1,
                'items': ('vlan', 'bond')}},
             ('vlan', 'ifenslave')),
            ({'network': {
                'version': 1,
                'items': ('bond', 'bridge')}},
             ('ifenslave', 'bridge-utils')),
            ({'network': {
                'version': 1,
                'items': ('vlan', 'bridge', 'bond')}},
             ('ifenslave', 'bridge-utils', 'vlan')),
        ))

    def test_mixed_v1_detect(self):
        self._test_req_mappings((
            ({'storage': {
                'version': 1,
                'items': ('raid', 'bcache', 'ext4')},
              'network': {
                  'version': 1,
                  'items': ('vlan',)}},
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'vlan')),
            ({'storage': {
                'version': 1,
                'items': ('lvm_partition', 'lvm_volgroup', 'xfs')},
              'network': {
                  'version': 1,
                  'items': ('bridge', 'bond')}},
             ('lvm2', 'xfsprogs', 'bridge-utils', 'ifenslave')),
            ({'storage': {
                'version': 1,
                'items': ('ext3', 'ext4', 'btrfs')},
              'network': {
                  'version': 1,
                  'items': ('bond', 'vlan')}},
             ('e2fsprogs', 'btrfs-tools', 'vlan', 'ifenslave')),
        ))

    def test_network_v2_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 2,
                'items': ('bridge',)}},
             ('bridge-utils',)),
            ({'network': {
                'version': 2,
                'items': ('vlan',)}},
             ('vlan',)),
            ({'network': {
                'version': 2,
                'items': ('vlan', 'bridge')}},
             ('vlan', 'bridge-utils')),
        ))

    def test_mixed_storage_v1_network_v2_detect(self):
        self._test_req_mappings((
            ({'network': {
                'version': 2,
                'items': ('bridge', 'vlan')},
             'storage': {
                 'version': 1,
                 'items': ('raid', 'bcache', 'ext4')}},
             ('vlan', 'bridge-utils', 'mdadm', 'bcache-tools', 'e2fsprogs')),
        ))
