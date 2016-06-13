from unittest import TestCase
from curtin.block import clear_holders


class TestClearHolders(TestCase):

    def test_split_vg_lv_name(self):
        """Ensure that split_vg_lv_name works for all possible lvm names"""
        names = ['volgroup-lvol', 'vol--group-lvol', 'test--one-test--two',
                 'test--one--two-lvname']
        split_names = [('volgroup', 'lvol'), ('vol-group', 'lvol'),
                       ('test-one', 'test-two'), ('test-one-two', 'lvname')]
        for name, split in zip(names, split_names):
            self.assertEqual(clear_holders.split_vg_lv_name(name), split)

        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('test')
        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('-test')
        with self.assertRaises(ValueError):
            clear_holders.split_vg_lv_name('test-')
