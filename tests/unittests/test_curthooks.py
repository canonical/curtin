import unittest
from curtin.commands import curthooks


class TestDetectRequiredPackages(unittest.TestCase):
    storage_configs = {
        'bcache':  {
            'type': 'bcache', 'name': 'bcache0', 'id': 'cache0',
            'backing_device': 'sda3', 'cache_device': 'sdb'},
        'lvm_partition': {
            'id': 'lvol1', 'name': 'lv1', 'volgroup': 'vg1',
            'type': 'lvm_partition'},
        'lvm_volgroup': {
            'id': 'vol1', 'name': 'vg1', 'devices': ['sda', 'sdb'],
            'type': 'lvm_volgroup'},
        'raid': {
            'id': 'mddevice', 'name': 'md0', 'type': 'raid', 'raidlevel': 5,
            'devices': ['sda1', 'sdb1', 'sdc1']},
        'ext2': {'id': 'format0', 'fstype': 'ext2', 'type': 'format'},
        'ext3': {'id': 'format1', 'fstype': 'ext3', 'type': 'format'},
        'ext4': {'id': 'format2', 'fstype': 'ext4', 'type': 'format'},
        'btrfs': {'id': 'format3', 'fstype': 'btrfs', 'type': 'format'},
        'xfs': {'id': 'format4', 'fstype': 'xfs', 'type': 'format'},
    }
    network_configs = {
        'bond': {
            'name': 'bond0', 'type': 'bond',
            'bond_interfaces': ['interface0', 'interface1'],
            'params': {'bond-mode': 'active-backup'},
            'subnets': [{'type': 'static', 'address': '10.23.23.2/24'},
                        {'type': 'static', 'address': '10.23.24.2/24'}]},
        'vlan': {
            'id': 'interface1.2667', 'mtu': 1500, 'name': 'interface1.2667',
            'type': 'vlan', 'vlan_id': 2667, 'vlan_link': 'interface1',
            'subnets': [{'address': '10.245.184.2/24', 'dns_nameservers': [],
                         'type': 'static'}]},
        'bridge': {
            'name': 'br0', 'bridge_interfaces': ['eth0', 'eth1'],
            'type': 'bridge', 'params': {'bridge_stp': 'off', 'bridge_fd': 0,
                                         'bridge_maxwait': 0},
            'subnets': [{'type': 'static', 'address': '192.168.14.2/24'},
                        {'type': 'static', 'address': '2001:1::1/64'}]},
    }

    def _test_req_mappings(self, req_mappings):
        for ((storage_items, net_items), expected_reqs) in req_mappings:
            cfg = {
                'storage': {
                    'config': [self.storage_configs[i] for i in storage_items],
                    'version': 1},
                'network': {
                    'config': [self.network_configs[i] for i in net_items],
                    'version': 1},
            }
            actual_reqs = curthooks.detect_required_packages(cfg)
            self.assertEqual(set(actual_reqs), set(expected_reqs),
                             'failed for cfg items: {}'.format(req_mappings))

    def test_storage_v1_detect(self):
        self._test_req_mappings((
            ((('lvm_partition', 'lvm_volgroup', 'btrfs', 'xfs'), ()),
             ('lvm2', 'xfsprogs', 'btrfs-tools')),
            ((('raid', 'bcache', 'ext3', 'xfs'), ()),
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'xfsprogs')),
            ((('raid', 'lvm_volgroup', 'lvm_partition', 'ext3', 'ext4'), ()),
             ('lvm2', 'mdadm', 'e2fsprogs')),
            ((('bcache', 'lvm_volgroup', 'lvm_partition', 'ext2'), ()),
             ('bcache-tools', 'lvm2', 'e2fsprogs')),
        ))

    def test_network_v1_detect(self):
        self._test_req_mappings((
            (((), ('bridge',)), ('bridge-utils',)),
            (((), ('vlan', 'bond')), ('vlan', 'ifenslave')),
            (((), ('bond', 'bridge')), ('ifenslave', 'bridge-utils')),
            (((), ('vlan', 'bridge')), ('bridge-utils', 'vlan')),
        ))
