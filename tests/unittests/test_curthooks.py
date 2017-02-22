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

    def test_storage_v1_detect(self):
        req_mappings = (
            (('lvm_partition', 'lvm_volgroup', 'btrfs', 'xfs'),
             ('lvm2', 'xfsprogs', 'btrfs-tools')),
            (('raid', 'bcache', 'ext3', 'xfs'),
             ('mdadm', 'bcache-tools', 'e2fsprogs', 'xfsprogs')),
            (('raid', 'lvm_volgroup', 'lvm_partition', 'ext3', 'ext4'),
             ('lvm2', 'mdadm', 'e2fsprogs')),
            (('bcache', 'lvm_volgroup', 'lvm_partition', 'btrfs', 'ext2'),
             ('bcache-tools', 'lvm2', 'btrfs-tools', 'e2fsprogs')),
        )

        for (cfg_items, expected_reqs) in req_mappings:
            cfg = {
                'storage': {
                    'config': [self.storage_configs[i] for i in cfg_items],
                    'version': 1
                }
            }
            actual_reqs = curthooks.detect_required_packages(cfg)
            self.assertEqual(set(actual_reqs), set(expected_reqs),
                             'failed for cfg items: {}'.format(cfg_items))
