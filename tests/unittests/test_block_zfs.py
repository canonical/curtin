from curtin.block import zfs
from .helpers import CiTestCase


class TestBlockZfsJoinFlags(CiTestCase):
    def test_zfs_join_flags_bad_optflags(self):
        """ zfs._join_flags raises ValueError if invalid optflag paramter """
        with self.assertRaises(ValueError):
            zfs._join_flags(None, {'a': 1})

        with self.assertRaises(ValueError):
            zfs._join_flags(23, {'a': 1})

    def test_zfs_join_flags_count_optflag(self):
        """ zfs._join_flags has correct number of optflags in output """
        oflag = '-o'
        params = {'a': 1}
        result = zfs._join_flags(oflag, params)
        self.assertEqual(result.count(oflag), len(params))

        params = {}
        result = zfs._join_flags(oflag, params)
        self.assertEqual(result.count(oflag), len(params))

    def test_zfs_join_flags_bad_params(self):
        """ zfs._join_flags raises ValueError if invalid params """
        with self.assertRaises(ValueError):
            zfs._join_flags('-o', None)

        with self.assertRaises(ValueError):
            zfs._join_flags('-p', [1, 2, 3])

        with self.assertRaises(ValueError):
            zfs._join_flags('-p', 'foobar')

    def test_zfs_join_flags_empty_params_ok(self):
        """ zfs._join_flags returns empty list with empty params """
        self.assertEqual([], zfs._join_flags('-o', {}))

    def test_zfs_join_flags_in_key_equal_value(self):
        """ zfs._join_flags converts dict to key=value """
        oflag = '-o'
        params = {'a': 1}
        result = zfs._join_flags(oflag, params)
        self.assertEqual([oflag, "a=1"], result)

    def test_zfs_join_flags_converts_booleans(self):
        """ zfs._join_flags converts True -> on, False -> off """
        params = {'setfoo': False, 'setwark': True}
        result = zfs._join_flags('-o', params)
        self.assertEqual(sorted(["-o", "setfoo=off", "-o", "setwark=on"]),
                         sorted(result))


class TestBlockZfsJoinPoolVolume(CiTestCase):

    def test_zfs_join_pool_volume(self):
        """ zfs._join_pool_volume combines poolname and volume """
        pool = 'mypool'
        volume = '/myvolume'
        self.assertEqual('mypool/myvolume',
                         zfs._join_pool_volume(pool, volume))

    def test_zfs_join_pool_volume_extra_slash(self):
        """ zfs._join_pool_volume removes extra slashes """
        pool = 'wark'
        volume = '//myvol/fs//foobar'
        self.assertEqual('wark/myvol/fs/foobar',
                         zfs._join_pool_volume(pool, volume))

    def test_zfs_join_pool_volume_no_slash(self):
        """ zfs._join_pool_volume handles no slash """
        pool = 'rpool'
        volume = 'ROOT'
        self.assertEqual('rpool/ROOT', zfs._join_pool_volume(pool, volume))

    def test_zfs_join_pool_volume_invalid_pool(self):
        """ zfs._join_pool_volume raises ValueError on invalid pool """
        with self.assertRaises(ValueError):
            zfs._join_pool_volume(None, 'myvol')

    def test_zfs_join_pool_volume_invalid_volume(self):
        """ zfs._join_pool_volume raises ValueError on invalid volume """
        with self.assertRaises(ValueError):
            zfs._join_pool_volume('rpool', None)

    def test_zfs_join_pool_volume_empty_params(self):
        """ zfs._join_pool_volume raises ValueError on invalid volume """
        with self.assertRaises(ValueError):
            zfs._join_pool_volume('', '')


class TestBlockZfsZpoolCreate(CiTestCase):

    def setUp(self):
        super(TestBlockZfsZpoolCreate, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')

    def test_zpool_create_raises_value_errors(self):
        """ zfs.zpool_create raises ValueError/TypeError for invalid inputs """

        # poolname
        for val in [None, '', {'a': 1}]:
            with self.assertRaises(ValueError):
                zfs.zpool_create(val, [])

        # vdevs
        for val in [None, '', {'a': 1}, 'mydev']:
            with self.assertRaises(TypeError):
                # All the assert methods (except assertRaises(),
                # assertRaisesRegexp()) accept a msg argument that,
                # if specified, is used as the error message on failure
                print('vdev value: %s' % val)
                zfs.zpool_create('mypool', val)

    def test_zpool_create_default_pool_properties(self):
        """ zpool_create uses default pool properties if none provided """
        zfs.zpool_create('mypool', ['/dev/disk/by-id/virtio-abcfoo1'])
        zpool_params = ["%s=%s" % (k, v) for k, v in
                        zfs.ZPOOL_DEFAULT_PROPERTIES.items()]
        args, _ = self.mock_subp.call_args
        self.assertTrue(set(zpool_params).issubset(set(args[0])))

    def test_zpool_create_pool_iterable(self):
        """ zpool_create accepts vdev iterables besides list """
        zfs.zpool_create('mypool', ('/dev/virtio-disk1', '/dev/virtio-disk2'))
        args, _ = self.mock_subp.call_args
        self.assertIn("/dev/virtio-disk1", args[0])
        self.assertIn("/dev/virtio-disk2", args[0])

    def test_zpool_create_default_zfs_properties(self):
        """ zpool_create uses default zfs properties if none provided """
        zfs.zpool_create('mypool', ['/dev/disk/by-id/virtio-abcfoo1'])
        zfs_params = ["%s=%s" % (k, v) for k, v in
                      zfs.ZFS_DEFAULT_PROPERTIES.items()]
        args, _ = self.mock_subp.call_args
        self.assertTrue(set(zfs_params).issubset(set(args[0])))

    def test_zpool_create_use_passed_properties(self):
        """ zpool_create uses provided properties """
        zpool_props = {'prop1': 'val1'}
        zfs_props = {'fsprop1': 'val2'}
        zfs.zpool_create('mypool', ['/dev/disk/by-id/virtio-abcfoo1'],
                         pool_properties=zpool_props, zfs_properties=zfs_props)
        all_props = zpool_props.copy()
        all_props.update(zfs_props)
        params = ["%s=%s" % (k, v) for k, v in all_props.items()]
        args, _ = self.mock_subp.call_args
        self.assertTrue(set(params).issubset(set(args[0])))

    def test_zpool_create_set_mountpoint(self):
        """ zpool_create uses mountpoint """
        mountpoint = '/srv'
        zfs.zpool_create('mypool', ['/dev/disk/by-id/virtio-abcfoo1'],
                         mountpoint=mountpoint)
        args, _ = self.mock_subp.call_args
        self.assertIn("mountpoint=%s" % mountpoint, args[0])

    def test_zpool_create_set_altroot(self):
        """ zpool_create uses altroot """
        altroot = '/var/tmp/mytarget'
        zfs.zpool_create('mypool', ['/dev/disk/by-id/virtio-abcfoo1'],
                         altroot=altroot)
        args, _ = self.mock_subp.call_args
        self.assertIn('-R', args[0])
        self.assertIn(altroot, args[0])

    def test_zpool_create_zfsroot(self):
        """ zpool_create sets up root command correctly """
        pool = 'rpool'
        mountpoint = '/'
        altroot = '/var/tmp/mytarget'
        vdev = '/dev/disk/by-id/virtio-abcfoo1'
        zfs.zpool_create('rpool', [vdev], mountpoint=mountpoint,
                         altroot=altroot)
        # the dictionary ordering is not guaranteed which means the
        # pairs of parameters may shift; this does not harm the function
        # of the call, but is harder to test; instead we will compare
        # the arg list sorted
        args, kwargs = self.mock_subp.call_args
        print(args[0])
        print(kwargs)
        expected_args = (
            ['zpool', 'create', '-o', 'ashift=12', '-O', 'normalization=formD',
             '-O', 'canmount=off', '-O', 'atime=off', '-O', 'compression=lz4',
             '-O', 'mountpoint=%s' % mountpoint, '-R', altroot, pool,
             vdev])
        expected_kwargs = {'capture': True}
        self.assertEqual(sorted(expected_args), sorted(args[0]))
        self.assertEqual(expected_kwargs, kwargs)


class TestBlockZfsZfsCreate(CiTestCase):

    def setUp(self):
        super(TestBlockZfsZfsCreate, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')

    def test_zfs_create_raises_value_errors(self):
        """ zfs.zfs_create raises ValueError for invalid inputs """

        # poolname
        for val in [None, '', {'a': 1}]:
            with self.assertRaises(ValueError):
                zfs.zfs_create(val, [])

        # volume
        for val in [None, '', {'a': 1}]:
            with self.assertRaises(ValueError):
                zfs.zfs_create('pool1', val)

        # properties
        for val in [12, ['a', 1]]:
            with self.assertRaises(ValueError):
                zfs.zfs_create('pool1', 'vol1', zfs_properties=val)

    def test_zfs_create_sets_zfs_properties(self):
        """ zfs.zfs_create uses zfs_properties parameters """
        zfs_props = {'fsprop1': 'val2'}
        zfs.zfs_create('mypool', 'myvol', zfs_properties=zfs_props)
        params = ["%s=%s" % (k, v) for k, v in zfs_props.items()]
        args, _ = self.mock_subp.call_args
        self.assertTrue(set(params).issubset(set(args[0])))

    def test_zfs_create_no_options(self):
        """ zfs.zfs_create passes no options by default """
        pool = 'rpool'
        volume = 'ROOT'
        zfs.zfs_create(pool, volume)
        self.mock_subp.assert_called_with(['zfs', 'create', 'rpool/ROOT'],
                                          capture=True)

    def test_zfs_create_calls_mount_if_canmount_is_noauto(self):
        """ zfs.zfs_create calls zfs mount if canmount=noauto """
        pool = 'rpool'
        volume = 'ROOT'
        props = {'canmount': 'noauto'}
        zfs.zfs_create(pool, volume, zfs_properties=props)
        self.mock_subp.assert_called_with(['zfs', 'mount',
                                           "%s/%s" % (pool, volume)],
                                          capture=True)


class TestBlockZfsZfsMount(CiTestCase):

    def setUp(self):
        super(TestBlockZfsZfsMount, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')

    def test_zfs_mount_raises_value_errors(self):
        """ zfs.zfs_mount raises ValueError for invalid inputs """

        # poolname
        for pool in [None, '', {'a': 1}, 'rpool']:
            for vol in [None, '', {'a': 1}, 'vol1']:
                if pool == "rpool" and vol == "vol1":
                    continue
                with self.assertRaises(ValueError):
                    zfs.zfs_mount(pool, vol)

    def test_zfs_mount(self):
        """ zfs.zfs_mount calls zfs mount command with pool and volume """
        pool = 'rpool'
        volume = 'home'
        zfs.zfs_mount(pool, volume)
        self.mock_subp.assert_called_with(['zfs', 'mount',
                                           '%s/%s' % (pool, volume)],
                                          capture=True)


class TestBlockZfsZpoolList(CiTestCase):

    def setUp(self):
        super(TestBlockZfsZpoolList, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')

    def test_zpool_list(self):
        """zpool list output returns list of pools"""
        pools = ['fake_pool', 'wark', 'nodata']
        stdout = "\n".join(pools)
        self.mock_subp.return_value = (stdout, "")

        found_pools = zfs.zpool_list()
        self.assertEqual(sorted(pools), sorted(found_pools))

    def test_zpool_list_empty(self):
        """zpool list returns empty list with no pools"""
        pools = []
        self.mock_subp.return_value = ("", "")
        found_pools = zfs.zpool_list()
        self.assertEqual(sorted(pools), sorted(found_pools))


class TestBlockZfsZpoolExport(CiTestCase):

    def setUp(self):
        super(TestBlockZfsZpoolExport, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')

    def test_zpool_export_no_poolname(self):
        """zpool_export raises ValueError on invalid poolname"""
        # poolname
        for val in [None, '', {'a': 1}]:
            with self.assertRaises(ValueError):
                zfs.zpool_export(val)

    def test_zpool_export(self):
        """zpool export calls zpool export <poolname>"""
        poolname = 'fake_pool'
        zfs.zpool_export(poolname)
        self.mock_subp.assert_called_with(['zpool', 'export', poolname])


class TestBlockZfsDeviceToPoolname(CiTestCase):

    def setUp(self):
        super(TestBlockZfsDeviceToPoolname, self).setUp()
        self.add_patch('curtin.block.zfs.util.subp', 'mock_subp')
        self.add_patch('curtin.block.zfs.blkid', 'mock_blkid')

    def test_device_to_poolname_invalid_devname(self):
        """device_to_poolname raises ValueError on invalid devname"""
        # devname
        for val in [None, '', {'a': 1}]:
            with self.assertRaises(ValueError):
                zfs.device_to_poolname(val)

    def test_device_to_poolname_finds_poolname(self):
        """find_poolname extracts 'LABEL' from zfs_member device"""
        devname = '/dev/wark'
        poolname = 'fake_pool'
        self.mock_blkid.return_value = {
            devname: {'LABEL': poolname,
                      'PARTUUID': '52dff41a-49be-44b3-a36a-1b499e570e69',
                      'TYPE': 'zfs_member',
                      'UUID': '12590398935543668673',
                      'UUID_SUB': '7809435738165038086'}}

        found_poolname = zfs.device_to_poolname(devname)
        self.assertEqual(poolname, found_poolname)
        self.mock_blkid.assert_called_with(devs=[devname])

    def test_device_to_poolname_no_match(self):
        """device_to_poolname returns None if devname not in blkid results"""
        devname = '/dev/wark'
        self.mock_blkid.return_value = {'/dev/foobar': {}}
        found_poolname = zfs.device_to_poolname(devname)
        self.assertEqual(None, found_poolname)
        self.mock_blkid.assert_called_with(devs=[devname])

    def test_device_to_poolname_no_zfs_member(self):
        """device_to_poolname returns None when device is not zfs_member"""
        devname = '/dev/wark'
        self.mock_blkid.return_value = {devname: {'TYPE': 'foobar'}}
        found_poolname = zfs.device_to_poolname(devname)
        self.assertEqual(None, found_poolname)
        self.mock_blkid.assert_called_with(devs=[devname])


# vi: ts=4 expandtab syntax=python
