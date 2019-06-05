import mock

from curtin.block import multipath
from .helpers import CiTestCase, raise_pexec_error


class TestMultipath(CiTestCase):

    def setUp(self):
        super(TestMultipath, self).setUp()
        self.add_patch('curtin.block.multipath.util.subp', 'm_subp')
        self.add_patch('curtin.block.multipath.udev', 'm_udev')

        self.m_subp.return_value = ("", "")

    def test_show_paths(self):
        self.m_subp.return_value = ("foo=bar wark=2", "")
        expected = ['multipathd', 'show', 'paths', 'raw', 'format',
                    multipath.SHOW_PATHS_FMT]
        self.assertEqual([{'foo': 'bar', 'wark': '2'}],
                         multipath.show_paths())
        self.m_subp.assert_called_with(expected, capture=True)

    def test_show_maps(self):
        self.m_subp.return_value = ("foo=bar wark=2", "")
        expected = ['multipathd', 'show', 'maps', 'raw', 'format',
                    multipath.SHOW_MAPS_FMT]
        self.assertEqual([{'foo': 'bar', 'wark': '2'}],
                         multipath.show_maps())
        self.m_subp.assert_called_with(expected, capture=True)

    def test_is_mpath_device_true(self):
        self.m_udev.udevadm_info.return_value = {'DM_UUID': 'mpath-mpatha-foo'}
        self.assertTrue(multipath.is_mpath_device(self.random_string()))

    def test_is_mpath_device_false(self):
        self.m_udev.udevadm_info.return_value = {'DM_UUID': 'lvm-vg-foo-lv1'}
        self.assertFalse(multipath.is_mpath_device(self.random_string()))

    def test_is_mpath_member_true(self):
        self.assertTrue(multipath.is_mpath_member(self.random_string()))

    def test_is_mpath_member_false(self):
        self.m_subp.side_effect = raise_pexec_error
        self.assertFalse(multipath.is_mpath_member(self.random_string()))

    def test_is_mpath_partition_true(self):
        dm_device = "/dev/dm-" + self.random_string()
        self.m_udev.udevadm_info.return_value = {'DM_PART': '1'}
        self.assertTrue(multipath.is_mpath_partition(dm_device))

    def test_is_mpath_partition_false(self):
        self.assertFalse(multipath.is_mpath_partition(self.random_string()))

    def test_mpath_partition_to_mpath_id(self):
        dev = self.random_string()
        mpath_id = self.random_string()
        self.m_udev.udevadm_info.return_value = {'DM_MPATH': mpath_id}
        self.assertEqual(mpath_id,
                         multipath.mpath_partition_to_mpath_id(dev))

    def test_mpath_partition_to_mpath_id_none(self):
        dev = self.random_string()
        self.m_udev.udevadm_info.return_value = {}
        self.assertEqual(None,
                         multipath.mpath_partition_to_mpath_id(dev))

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_partition(self, m_wait, m_exists):
        devpath = self.random_string()
        m_exists.side_effect = iter([True, True, False])
        multipath.remove_partition(devpath)
        expected = mock.call(['dmsetup', 'remove', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        m_wait.assert_not_called()
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_partition_waits(self, m_wait, m_exists):
        devpath = self.random_string()
        m_exists.side_effect = iter([True, True, True])
        multipath.remove_partition(devpath, retries=3)
        expected = mock.call(['dmsetup', 'remove', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)
        self.assertEqual(1, m_wait.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_map(self, m_wait, m_exists):
        map_id = self.random_string()
        devpath = '/dev/mapper/%s' % map_id
        m_exists.side_effect = iter([True, True, False])
        multipath.remove_map(devpath)
        expected = mock.call(['multipath', '-f', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        m_wait.assert_not_called()
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)

    @mock.patch('curtin.block.multipath.os.path.exists')
    @mock.patch('curtin.block.multipath.util.wait_for_removal')
    def test_remove_map_wait(self, m_wait, m_exists):
        map_id = self.random_string()
        devpath = '/dev/mapper/%s' % map_id
        m_exists.side_effect = iter([True, True, True])
        multipath.remove_map(devpath, retries=3)
        expected = mock.call(['multipath', '-f', devpath], rcs=[0, 1])
        self.m_subp.assert_has_calls([expected] * 3)
        self.assertEqual(3, self.m_udev.udevadm_settle.call_count)
        self.assertEqual(1, m_wait.call_count)

    def test_find_mpath_members(self):
        mp_id = 'mpatha'
        paths = ['device=bar multipath=mpatha',
                 'device=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertEqual(sorted(['/dev/bar', '/dev/wark']),
                         sorted(multipath.find_mpath_members(mp_id)))

    def test_find_mpath_members_empty(self):
        mp_id = self.random_string()
        paths = ['device=bar multipath=mpatha',
                 'device=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(paths), "")
        self.assertEqual([], multipath.find_mpath_members(mp_id))

    def test_find_mpath_id(self):
        mp_id = 'mpatha'
        maps = ['sysfs=bar multipath=mpatha',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual(mp_id, multipath.find_mpath_id('/dev/bar'))

    def test_find_mpath_id_name(self):
        maps = ['sysfs=bar multipath=mpatha name=friendly',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual('friendly', multipath.find_mpath_id('/dev/bar'))

    def test_find_mpath_id_none(self):
        maps = ['sysfs=bar multipath=mpatha',
                'sysfs=wark multipath=mpatha']
        self.m_subp.return_value = ("\n".join(maps), "")
        self.assertEqual(None, multipath.find_mpath_id('/dev/foo'))


# vi: ts=4 expandtab syntax=python
