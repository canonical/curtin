import mock

from curtin.block import multipath
from .helpers import CiTestCase, raise_pexec_error


# dmsetup uses tabs as separators
DMSETUP_LS_BLKDEV_OUTPUT = '''\
mpatha	(dm-0)
mpatha-part1	(dm-1)
1gb zero	(dm-2)
'''


class TestMultipath(CiTestCase):

    def setUp(self):
        super(TestMultipath, self).setUp()
        self.add_patch('curtin.block.multipath.util.subp', 'm_subp')
        self.add_patch('curtin.block.multipath.udev', 'm_udev')

        self.m_subp.return_value = ("", "")

    def test_show_paths(self):
        """verify show_paths extracts mulitpath path data correctly."""
        self.m_subp.return_value = ("foo=bar wark=2", "")
        expected = ['multipathd', 'show', 'paths', 'raw', 'format',
                    multipath.SHOW_PATHS_FMT]
        self.assertEqual([{'foo': 'bar', 'wark': '2'}],
                         multipath.show_paths())
        self.m_subp.assert_called_with(expected, capture=True)

    def test_show_maps(self):
        """verify show_maps extracts mulitpath map data correctly."""
        self.m_subp.return_value = ("foo=bar wark=2", "")
        expected = ['multipathd', 'show', 'maps', 'raw', 'format',
                    multipath.SHOW_MAPS_FMT]
        self.assertEqual([{'foo': 'bar', 'wark': '2'}],
                         multipath.show_maps())
        self.m_subp.assert_called_with(expected, capture=True)

    def test_is_mpath_device_true(self):
        """is_mpath_device returns true if dev DM_UUID starts with mpath-"""
        self.m_udev.udevadm_info.return_value = {'DM_UUID': 'mpath-mpatha-foo'}
        self.assertTrue(multipath.is_mpath_device(self.random_string()))

    def test_is_mpath_device_false(self):
        """is_mpath_device returns false when DM_UUID doesnt start w/ mpath-"""
        self.m_udev.udevadm_info.return_value = {'DM_UUID': 'lvm-vg-foo-lv1'}
        self.assertFalse(multipath.is_mpath_device(self.random_string()))

    def test_is_mpath_member_true(self):
        """is_mpath_device returns false when DM_UUID doesnt start w/ mpath-"""
        self.assertTrue(multipath.is_mpath_member(self.random_string()))

    def test_is_mpath_member_false(self):
        """is_mpath_member returns false if 'multipath -c <dev>' exits err."""
        self.m_subp.side_effect = raise_pexec_error
        self.assertFalse(multipath.is_mpath_member(self.random_string()))

    def test_is_mpath_partition_true(self):
        """is_mpath_member returns true if 'multipath -c <dev>' exits 0."""
        dm_device = "/dev/dm-" + self.random_string()
        self.m_udev.udevadm_info.return_value = {'DM_PART': '1'}
        self.assertTrue(multipath.is_mpath_partition(dm_device))

    def test_is_mpath_partition_false(self):
        """is_mpath_member returns false if DM_PART is not present for dev."""
        self.assertFalse(multipath.is_mpath_partition(self.random_string()))

    def test_mpath_partition_to_mpath_id(self):
        """mpath_part_to_mpath_id extracts MD_MPATH value from mp partition."""
        dev = self.random_string()
        mpath_id = self.random_string()
        self.m_udev.udevadm_info.return_value = {'DM_MPATH': mpath_id}
        self.assertEqual(mpath_id,
                         multipath.mpath_partition_to_mpath_id(dev))

    def test_mpath_partition_to_mpath_id_none(self):
        """mpath_part_to_mpath_id returns none if DM_MPATH missing."""
        dev = self.random_string()
        self.m_udev.udevadm_info.return_value = {}
        self.assertIsNone(multipath.mpath_partition_to_mpath_id(dev))

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_partition(self, m_wait, m_exists):
        """multipath.remove_partition runs dmsetup skips wait if dev gone."""
        devpath = self.random_string()
        m_exists.side_effect = iter([True, True, False])
        multipath.remove_partition(devpath)
        expected = mock.call(
            ['dmsetup', 'remove', '--force', '--retry', devpath])
        self.m_subp.assert_has_calls([expected] * 3)
        m_wait.assert_not_called()
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_partition_waits(self, m_wait, m_exists):
        """multipath.remove_partition runs dmsetup waits if dev still there."""
        devpath = self.random_string()
        m_exists.side_effect = iter([True, True, True])
        multipath.remove_partition(devpath, retries=3)
        expected = mock.call(
            ['dmsetup', 'remove', '--force', '--retry', devpath])
        self.m_subp.assert_has_calls([expected] * 3)
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)
        self.assertEqual(1, m_wait.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_map(self, m_wait, m_exists):
        """multipath.remove_map runs multipath -f skips wait if map gone."""
        map_id = self.random_string()
        devpath = '/dev/mapper/%s' % map_id
        m_exists.side_effect = iter([True, True, False])
        multipath.remove_map(devpath)
        expected = mock.call(
            ['multipath', '-v3', '-R3', '-f', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        m_wait.assert_not_called()
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_map_wait(self, m_wait, m_exists):
        """multipath.remove_map runs multipath -f  wait if map remains."""
        map_id = self.random_string()
        devpath = '/dev/mapper/%s' % map_id
        m_exists.side_effect = iter([True, True, True])
        multipath.remove_map(devpath, retries=3)
        expected = mock.call(
            ['multipath', '-v3', '-R3', '-f', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)
        self.assertEqual(1, m_wait.call_count)

    def test_find_mpath_members(self):
        """find_mpath_members enumerates kernel block devs of a mpath_id."""
        mp_id = 'mpatha'
        paths = ['device=bar multipath=mpatha',
                 'device=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertEqual(sorted(['/dev/bar', '/dev/wark']),
                         sorted(multipath.find_mpath_members(mp_id)))

    def test_find_mpath_members_empty(self):
        """find_mpath_members returns empty list if mpath_id not found."""
        mp_id = self.random_string()
        paths = ['device=bar multipath=mpatha',
                 'device=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertEqual([], multipath.find_mpath_members(mp_id))

    def test_find_mpath_id(self):
        """find_mpath_id returns mpath_id if device is part of mpath group."""
        mp_id = 'mpatha'
        maps = ['sysfs=bar multipath=mpatha',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual(mp_id, multipath.find_mpath_id('/dev/bar'))

    def test_find_mpath_id_name(self):
        """find_mpath_id_name returns the name if present in maps on match."""
        maps = ['sysfs=bar multipath=mpatha name=friendly',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual('friendly', multipath.find_mpath_id('/dev/bar'))

    def test_find_mpath_id_none(self):
        """find_mpath_id_name returns none when device is not part of maps."""
        maps = ['sysfs=bar multipath=mpatha',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual(None, multipath.find_mpath_id('/dev/foo'))

    def test_dmname_to_blkdev_mapping(self):
        """dmname_to_blkdev_mapping returns dmname to blkdevice dictionary."""
        self.m_subp.return_value = (DMSETUP_LS_BLKDEV_OUTPUT, "")
        expected_mapping = {
            'mpatha': '/dev/dm-0',
            'mpatha-part1': '/dev/dm-1',
            '1gb zero': '/dev/dm-2',
        }
        self.assertEqual(expected_mapping,
                         multipath.dmname_to_blkdev_mapping())

    def test_dmname_to_blkdev_mapping_empty(self):
        """dmname_to_blkdev_mapping returns empty dict when dmsetup is empty.
        """
        self.m_subp.return_value = ("No devices found", "")
        expected_mapping = {}
        self.assertEqual(expected_mapping,
                         multipath.dmname_to_blkdev_mapping())

    @mock.patch('curtin.block.multipath.dmname_to_blkdev_mapping')
    def test_find_mpath_id_by_parent(self, m_dmmap):
        """find_mpath_id_by_parent returns device mapper blk for given DM_NAME.
        """
        m_dmmap.return_value = {
            'mpatha': '/dev/dm-0', 'mpatha-part1': '/dev/dm-1'}
        mpath_id = 'mpatha'
        expected_result = ('mpatha-part1', '/dev/dm-1')
        self.assertEqual(
            expected_result,
            multipath.find_mpath_id_by_parent(mpath_id, partnum=1))

    def test_find_mpath_id_by_path(self):
        """find_mpath_id_by_path returns the mp_id if specified device is
           member.
        """
        mp_id = 'mpatha'
        paths = ['device=bar multipath=mpatha',
                 'device=wark multipath=mpathb']
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertEqual(mp_id, multipath.find_mpath_id_by_path('/dev/bar'))

    def test_find_mpath_id_by_path_returns_none_not_found(self):
        """find_mpath_id_by_path returns None if specified device is not a
           member.
        """
        mp_id = 'mpatha'
        paths = ['device=bar multipath=%s' % mp_id,
                 'device=wark multipath=%s' % mp_id]
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertIsNone(multipath.find_mpath_id_by_path('/dev/xxx'))


# vi: ts=4 expandtab syntax=python
