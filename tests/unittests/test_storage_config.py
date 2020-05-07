# This file is part of curtin. See LICENSE file for copyright and license info.
import copy
import json
from .helpers import CiTestCase, skipUnlessJsonSchema
from curtin import storage_config
from curtin.storage_config import ProbertParser as baseparser
from curtin.storage_config import (BcacheParser, BlockdevParser, DasdParser,
                                   DmcryptParser, FilesystemParser, LvmParser,
                                   RaidParser, MountParser, ZfsParser)
from curtin.storage_config import ptable_uuid_to_flag_entry
from curtin import util


class TestStorageConfigSchema(CiTestCase):

    @skipUnlessJsonSchema()
    def test_storage_config_schema_is_valid_draft7(self):
        import jsonschema
        schema = storage_config.STORAGE_CONFIG_SCHEMA
        jsonschema.Draft4Validator.check_schema(schema)

    @skipUnlessJsonSchema()
    def test_disk_schema_accepts_nvme_eui(self):
        disk = {
            "id": "disk-nvme0n1",
            "path": "/dev/nvme0n1",
            "serial": "Samsung SSD 960 EVO 250GB_S3ESNX0JB35041V",
            "type": "disk",
            "wwn": "eui.0025385b71b1313e"
        }
        config = {'config': [disk], 'version': 1}
        storage_config.validate_config(config)

    @skipUnlessJsonSchema()
    def test_disk_schema_accepts_nvme_wwid(self):
        disk = {
            "id": "disk-nvme0n1",
            "path": "/dev/nvme0n1",
            "serial": "CT500P1SSD8_1925E20E7B65",
            "type": "disk",
            "wwn": ("nvme.c0a9-313932354532304537423030-"
                    "4354353030503153534438-00000001"),
        }
        config = {'config': [disk], 'version': 1}
        storage_config.validate_config(config)

    @skipUnlessJsonSchema()
    def test_disk_schema_accepts_missing_ptable(self):
        disk = {
            "id": "disk-vdc",
            "path": "/dev/vdc",
            "type": "disk",
        }
        config = {'config': [disk], 'version': 1}
        storage_config.validate_config(config)


class TestProbertParser(CiTestCase):

    invalid_inputs = [None, '', {}, [], set()]

    # XXX: Parameterize me
    def test_probert_parser_raises_valueerror(self):
        """ ProbertParser raises ValueError on none-ish input. """
        for invalid in self.invalid_inputs:
            with self.assertRaises(ValueError):
                storage_config.ProbertParser(invalid)

    def test_probert_parser_stores_probe_data(self):
        """ ProbertParser stores probe_data in instance. """
        probe_data = {'blockdev': {self.random_string(): {}}}
        self.assertDictEqual(probe_data, baseparser(probe_data).probe_data)

    def test_probert_parser_sets_probe_data_key_attr(self):
        """ ProbertParser sets probe_data_key attribute if in probe_data. """
        probe_data = {'blockdev': {self.random_string(): self.random_string()}}

        class bdparser(baseparser):
            probe_data_key = 'blockdev'

        bdp = bdparser(probe_data)
        self.assertTrue(hasattr(bdp, 'blockdev_data'))
        self.assertDictEqual(probe_data['blockdev'],
                             getattr(bdp, 'blockdev_data'))

    def test_probert_parser_handles_missing_required_probe_data_key(self):
        """ ProbertParser handles missing probe_data_key_data. """
        key = self.random_string()
        probe_data = {'blockdev': {self.random_string(): self.random_string()}}

        class bdparser(baseparser):
            probe_data_key = key

        self.assertIsNotNone(bdparser(probe_data))


def _get_data(datafile):
    data = util.load_file('tests/data/%s' % datafile)
    jdata = json.loads(data)
    return jdata.get('storage') if 'storage' in jdata else jdata


class TestBcacheParser(CiTestCase):

    def setUp(self):
        super(TestBcacheParser, self).setUp()
        self.probe_data = {
            'bcache': {
                'backing': {
                    self.random_string(): {
                        'blockdev': self.random_string(),
                        'superblock': {},
                    },
                },
                'caching': {
                    self.random_string(): {
                        'blockdev': self.random_string(),
                        'superblock': {},
                    },
                },
            },
            'blockdev': {self.random_string(): {}},
        }

    def test_bcache_parse(self):
        """ BcacheParser initializes class_data, backing, caching attrs."""
        bcachep = BcacheParser(self.probe_data)
        self.assertDictEqual(self.probe_data, bcachep.probe_data)
        self.assertDictEqual(self.probe_data['bcache'],
                             bcachep.class_data)
        self.assertDictEqual(self.probe_data['bcache']['backing'],
                             bcachep.backing)
        self.assertDictEqual(self.probe_data['bcache']['caching'],
                             bcachep.caching)

    def test_bcache_parse_tolerates_missing_blockdev_data(self):
        """ BcacheParser  ValueError on missing 'blockdev' dict."""
        del(self.probe_data['blockdev'])
        b = BcacheParser(self.probe_data)
        (configs, errors) = b.parse()
        self.assertEqual([], configs)
        self.assertEqual([], errors)

    @skipUnlessJsonSchema()
    def test_bcache_parse_extracts_bcache(self):
        """ BcacheParser extracts bcache config from diglett.json data. """
        probe_data = _get_data('probert_storage_diglett.json')
        bcachep = BcacheParser(probe_data)
        (configs, errors) = bcachep.parse()
        self.assertEqual([], errors)
        self.assertEqual(1, len(configs))
        expected_config = {
            'type': 'bcache',
            'id': 'disk-bcache0',
            'name': 'bcache0',
            'backing_device': 'partition-sda3',
            'cache_device': 'partition-nvme0n1p1',
            'cache_mode': 'writeback',
        }
        self.assertDictEqual(expected_config, configs[0])

    @skipUnlessJsonSchema()
    def test_bcache_parse_extracts_bcache_backing_only(self):
        """ BcacheParser extracts bcache config w/ backing device only. """
        probe_data = _get_data('probert_storage_diglett.json')
        probe_data['bcache']['caching'] = {}
        bcachep = BcacheParser(probe_data)
        (configs, errors) = bcachep.parse()
        self.assertEqual([], errors)
        self.assertEqual(1, len(configs))
        expected_config = {
            'type': 'bcache',
            'id': 'disk-bcache0',
            'name': 'bcache0',
            'backing_device': 'partition-sda3',
            'cache_mode': 'writeback',
        }
        self.assertDictEqual(expected_config, configs[0])

    @skipUnlessJsonSchema()
    def test_bcache_parse_ignores_bcache_cache_only(self):
        """ BcacheParser ignores cache device only. """
        probe_data = _get_data('probert_storage_diglett.json')
        probe_data['bcache']['backing'] = {}
        bcachep = BcacheParser(probe_data)
        (configs, errors) = bcachep.parse()
        self.assertEqual([], errors)
        self.assertEqual(0, len(configs))


class TestBlockdevParser(CiTestCase):

    def setUp(self):
        super(TestBlockdevParser, self).setUp()
        self.probe_data = _get_data('probert_storage_diglett.json')
        self.bdevp = BlockdevParser(self.probe_data)

    def test_blockdev_parse(self):
        """ BlockdevParser 'blockdev_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['blockdev'],
                             self.bdevp.blockdev_data)

    # XXX: Parameterize me
    def test_blockdev_ptable_uuid_flag(self):
        """ BlockdevParser maps ptable UUIDs to boot flags. """
        boot_guids = ['C12A7328-F81F-11D2-BA4B-00A0C93EC93B',
                      'c12a7328-f81f-11d2-ba4b-00a0c93ec93b']
        expected_tuple = ('boot', 'EF00')
        for guid in boot_guids:
            self.assertEqual(expected_tuple,
                             ptable_uuid_to_flag_entry(guid))

    # XXX: Parameterize me
    def test_blockdev_ptable_uuid_flag_invalid(self):
        """ BlockdevParser returns (None, None) for invalid uuids. """
        for invalid in [None, '', {}, []]:
            self.assertEqual((None, None),
                             ptable_uuid_to_flag_entry(invalid))

    # XXX: Parameterize me
    def test_blockdev_ptable_uuid_flag_unknown_uuid(self):
        """ BlockdevParser returns (None, None) for unknown uuids. """
        for unknown in [self.random_string(), self.random_string()]:
            self.assertEqual((None, None),
                             ptable_uuid_to_flag_entry(unknown))

    def test_get_unique_ids(self):
        """ BlockdevParser extracts uniq udev ID_ values. """
        expected_ids = {'wwn': '0x3001438034e549a0',
                        'serial': '33001438034e549a0'}
        blockdev = self.bdevp.blockdev_data['/dev/sda1']
        self.assertDictEqual(expected_ids,
                             self.bdevp.get_unique_ids(blockdev))

    def test_get_unique_ids_ignores_empty_wwn_values(self):
        """ BlockdevParser skips invalid ID_WWN_* values. """
        self.bdevp.blockdev_data['/dev/sda'] = {
            'DEVTYPE': 'disk',
            'DEVNAME': 'sda',
            'ID_SERIAL': 'Corsair_Force_GS_1785234921906',
            'ID_SERIAL_SHORT': '1785234921906',
            'ID_WWN': '0x0000000000000000',
            'ID_WWN_WITH_EXTENSION': '0x0000000000000000',
        }
        blockdev = self.bdevp.blockdev_data['/dev/sda']
        expected_ids = {'serial': 'Corsair_Force_GS_1785234921906'}
        self.assertEqual(expected_ids,
                         self.bdevp.get_unique_ids(blockdev))

    def test_get_unique_ids_ignores_empty_serial_values(self):
        """ BlockdevParser skips invalid ID_SERIAL_* values. """
        self.bdevp.blockdev_data['/dev/sda'] = {
            'DEVTYPE': 'disk',
            'DEVNAME': 'sda',
            'ID_SERIAL': '                      ',
            'ID_SERIAL_SHORT': 'My Serial is My PassPort',
        }
        blockdev = self.bdevp.blockdev_data['/dev/sda']
        expected_ids = {'serial': 'My Serial is My PassPort'}
        self.assertEqual(expected_ids,
                         self.bdevp.get_unique_ids(blockdev))

    def test_partition_parent_devname(self):
        """ BlockdevParser calculate partition parent name. """
        expected_parent = '/dev/sda'
        blockdev = self.bdevp.blockdev_data['/dev/sda1']
        self.assertEqual(expected_parent,
                         self.bdevp.partition_parent_devname(blockdev))

    def test_partition_parent_devname_exception_non_partition(self):
        """ BlockdevParser raises ValueError if DEVTYPE is not partition."""
        blockdev = self.bdevp.blockdev_data['/dev/bcache0']
        with self.assertRaises(ValueError):
            self.bdevp.partition_parent_devname(blockdev)

    def test_blockdev_asdict_disk(self):
        """ BlockdevParser creates dictionary of DEVTYPE=disk. """

        blockdev = self.bdevp.blockdev_data['/dev/sda']
        expected_dict = {
            'id': 'disk-sda',
            'type': 'disk',
            'wwn': '0x3001438034e549a0',
            'serial': '33001438034e549a0',
            'path': '/dev/sda',
            'ptable': 'gpt',
        }
        self.assertDictEqual(expected_dict,
                             self.bdevp.asdict(blockdev))

    def test_blockdev_asdict_partition(self):
        """ BlockdevParser creates dictionary of DEVTYPE=partition. """

        blockdev = self.bdevp.blockdev_data['/dev/sda1']
        expected_dict = {
            'id': 'partition-sda1',
            'type': 'partition',
            'device': 'disk-sda',
            'number': 1,
            'offset': 1048576,
            'size': 499122176,
            'flag': 'linux',
        }
        self.assertDictEqual(expected_dict,
                             self.bdevp.asdict(blockdev))

    # XXX: Parameterize me
    def test_blockdev_asdict_not_disk_or_partition(self):
        """ BlockdevParser ignores DEVTYPE not in 'disk, partition'. """
        test_value = {'DEVTYPE': self.random_string()}
        self.assertEqual(None, self.bdevp.asdict(test_value))

    # XXX: Parameterize me
    def test_blockdev_asdict_ignores_floppy(self):
        """ BlockdevParser ignores MAJOR=2 Floppy. """
        test_value = {'DEVTYPE': 'disk', 'MAJOR': '2'}
        self.assertEqual(None, self.bdevp.asdict(test_value))

    # XXX: Parameterize me
    def test_blockdev_asdict_ignores_cdrom(self):
        """ BlockdevParser ignores MAJOR=11 CDROM. """
        test_value = {'DEVTYPE': 'disk', 'MAJOR': '11'}
        self.assertEqual(None, self.bdevp.asdict(test_value))

    def test_blockdev_asdict_ignores_zero_start_value(self):
        """ BlockdevParser ignores partition with zero start value."""
        self.bdevp.blockdev_data['/dev/vda'] = {
            'DEVTYPE': 'disk',
            'DEVNAME': 'vda',
        }
        test_value = {
            'DEVTYPE': 'partition',
            'MAJOR': "252",
            'DEVNAME': 'vda1',
            "DEVPATH":
                "/devices/pci0000:00/0000:00:04.0/virtio0/block/vda/vda1",
            "ID_PART_ENTRY_TYPE": "0x0",
            'attrs': {'partition': "1", 'size': "784334848", 'start': "0"}}

        expected_dict = {
            'id': 'partition-vda1',
            'type': 'partition',
            'device': 'disk-vda',
            'number': 1,
            'size': 784334848,
        }
        self.assertDictEqual(expected_dict, self.bdevp.asdict(test_value))

    # XXX: Parameterize me
    def test_blockdev_to_id_raises_valueerror_on_empty_name(self):
        test_value = {'DEVTYPE': 'disk', 'DEVNAME': '', 'DEVPATH': 'foobar'}
        with self.assertRaises(ValueError):
            self.bdevp.blockdev_to_id(test_value)

    # XXX: Parameterize me
    def test_blockdev_to_id_raises_valueerror_on_empty_devtype(self):
        test_value = {'DEVTYPE': '', 'DEVNAME': 'bar', 'DEVPATH': 'foobar'}
        with self.assertRaises(ValueError):
            self.bdevp.blockdev_to_id(test_value)

    # XXX: Parameterize me
    def test_blockdev_to_id_raises_valueerror_on_missing_name(self):
        test_value = {'DEVTYPE': 'disk', 'DEVPATH': 'foobar'}
        with self.assertRaises(ValueError):
            self.bdevp.blockdev_to_id(test_value)

    # XXX: Parameterize me
    def test_blockdev_to_id_raises_valueerror_on_missing_devtype(self):
        test_value = {'DEVNAME': 'bar', 'DEVPATH': 'foobar'}
        with self.assertRaises(ValueError):
            self.bdevp.blockdev_to_id(test_value)

    # XXX: Parameterize me
    def test_blockdev_detects_extended_partitions(self):
        self.probe_data = _get_data('probert_storage_lvm.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/vda2']
        expected_dict = {
            'id': 'partition-vda2',
            'type': 'partition',
            'device': 'disk-vda',
            'number': 2,
            'offset': 3222274048,
            'size': 5370806272,
            'flag': 'extended',
        }
        for ext_part_entry in ['0xf', '0x5', '0x85', '0xc5']:
            blockdev['ID_PART_ENTRY_TYPE'] = ext_part_entry
            self.assertDictEqual(expected_dict,
                                 self.bdevp.asdict(blockdev))

    def test_blockdev_detects_logical_partitions(self):
        self.probe_data = _get_data('probert_storage_lvm.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/vda5']
        expected_dict = {
            'id': 'partition-vda5',
            'type': 'partition',
            'device': 'disk-vda',
            'number': 5,
            'offset': 3223322624,
            'size': 2147483648,
            'flag': 'logical',
        }
        self.assertDictEqual(expected_dict,
                             self.bdevp.asdict(blockdev))

    def test_blockdev_asdict_disk_omits_ptable_if_none_present(self):
        blockdev = self.bdevp.blockdev_data['/dev/sda']
        del blockdev['ID_PART_TABLE_TYPE']
        expected_dict = {
            'id': 'disk-sda',
            'type': 'disk',
            'wwn': '0x3001438034e549a0',
            'serial': '33001438034e549a0',
            'path': '/dev/sda',
        }
        self.assertDictEqual(expected_dict,
                             self.bdevp.asdict(blockdev))

    def test_blockdev_asdict_disk_marks_unknown_ptable_as_unspported(self):
        blockdev = self.bdevp.blockdev_data['/dev/sda']
        expected_dict = {
            'id': 'disk-sda',
            'type': 'disk',
            'wwn': '0x3001438034e549a0',
            'serial': '33001438034e549a0',
            'ptable': 'unsupported',
            'path': '/dev/sda',
        }
        for invalid in ['mac', 'PMBR']:
            blockdev['ID_PART_TABLE_TYPE'] = invalid
            self.assertDictEqual(expected_dict,
                                 self.bdevp.asdict(blockdev))

    def test_blockdev_detects_multipath(self):
        self.probe_data = _get_data('probert_storage_multipath.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/sda2']
        expected_dict = {
            'flag': 'linux',
            'id': 'partition-sda2',
            'offset': 2097152,
            'multipath': 'mpatha',
            'size': 10734272512,
            'type': 'partition',
            'device': 'disk-sda',
            'number': 2}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))

    def test_blockdev_skips_multipath_entry_if_no_multipath_data(self):
        self.probe_data = _get_data('probert_storage_multipath.json')
        del self.probe_data['multipath']
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/sda2']
        expected_dict = {
            'flag': 'linux',
            'id': 'partition-sda2',
            'offset': 2097152,
            'size': 10734272512,
            'type': 'partition',
            'device': 'disk-sda',
            'number': 2}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))

    def test_blockdev_skips_multipath_entry_if_bad_multipath_data(self):
        self.probe_data = _get_data('probert_storage_multipath.json')
        for path in self.probe_data['multipath']['paths']:
            path['multipath'] = ''
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/sda2']
        expected_dict = {
            'flag': 'linux',
            'id': 'partition-sda2',
            'offset': 2097152,
            'size': 10734272512,
            'type': 'partition',
            'device': 'disk-sda',
            'number': 2}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))

    def test_blockdev_skips_multipath_entry_if_no_mp_paths(self):
        self.probe_data = _get_data('probert_storage_multipath.json')
        del self.probe_data['multipath']['paths']
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/sda2']
        expected_dict = {
            'flag': 'linux',
            'id': 'partition-sda2',
            'offset': 2097152,
            'size': 10734272512,
            'type': 'partition',
            'device': 'disk-sda',
            'number': 2}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))

    def test_blockdev_finds_multipath_id_from_dm_uuid(self):
        self.probe_data = _get_data('probert_storage_zlp6.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/dm-2']
        result = self.bdevp.blockdev_to_id(blockdev)
        self.assertEqual('disk-sda', result)

    def test_blockdev_find_mpath_members_checks_dm_name(self):
        """ BlockdevParser find_mpath_members uses dm_name if present."""
        dm14 = {
            "DEVTYPE": "disk",
            "DEVLINKS": "/dev/disk/by-id/dm-name-mpathb",
            "DEVNAME": "/dev/dm-14",
            "DEVTYPE": "disk",
            "DM_NAME": "mpathb",
            "DM_UUID": "mpath-360050768028211d8b000000000000062",
            "DM_WWN": "0x60050768028211d8b000000000000062",
            "MPATH_DEVICE_READY": "1",
            "MPATH_SBIN_PATH": "/sbin",
        }
        multipath = {
            "maps": [
                {
                    "multipath": "360050768028211d8b000000000000061",
                    "sysfs": "dm-11",
                    "paths": "4"
                },
                {
                    "multipath": "360050768028211d8b000000000000062",
                    "sysfs": "dm-14",
                    "paths": "4"
                },
                {
                    "multipath": "360050768028211d8b000000000000063",
                    "sysfs": "dm-15",
                    "paths": "4"
                }],
            "paths": [
                {
                    "device": "sdej",
                    "serial": "0200a084762cXX00",
                    "multipath": "mpatha",
                    "host_wwnn": "0x20000024ff9127de",
                    "target_wwnn": "0x5005076802065e38",
                    "host_wwpn": "0x21000024ff9127de",
                    "target_wwpn": "0x5005076802165e38",
                    "host_adapter": "[undef]"
                },
                {
                    "device": "sdel",
                    "serial": "0200a084762cXX00",
                    "multipath": "mpathb",
                    "host_wwnn": "0x20000024ff9127de",
                    "target_wwnn": "0x5005076802065e38",
                    "host_wwpn": "0x21000024ff9127de",
                    "target_wwpn": "0x5005076802165e38",
                    "host_adapter": "[undef]"
                },
                {
                    "device": "sdet",
                    "serial": "0200a084762cXX00",
                    "multipath": "mpatha",
                    "host_wwnn": "0x20000024ff9127de",
                    "target_wwnn": "0x5005076802065e37",
                    "host_wwpn": "0x21000024ff9127de",
                    "target_wwpn": "0x5005076802165e37",
                    "host_adapter": "[undef]"
                },
                {
                    "device": "sdev",
                    "serial": "0200a084762cXX00",
                    "multipath": "mpathb",
                    "host_wwnn": "0x20000024ff9127de",
                    "target_wwnn": "0x5005076802065e37",
                    "host_wwpn": "0x21000024ff9127de",
                    "target_wwpn": "0x5005076802165e37",
                    "host_adapter": "[undef]"
                }],
        }
        self.bdevp.blockdev_data['/dev/dm-14'] = dm14
        self.probe_data['multipath'] = multipath
        self.assertEqual('disk-sdel', self.bdevp.blockdev_to_id(dm14))

    def test_blockdev_detects_dasd_device_id_and_vtoc_ptable(self):
        self.probe_data = _get_data('probert_storage_dasd.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/dasdd']
        expected_dict = {
            'device_id': '0.0.1544',
            'id': 'disk-dasdd',
            'path': '/dev/dasdd',
            'ptable': 'vtoc',
            'serial': '0X1544',
            'type': 'disk'}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))

    def test_blockdev_detects_dasd_device_id_and_unformatted_no_ptable(self):
        self.probe_data = _get_data('probert_storage_dasd.json')
        self.bdevp = BlockdevParser(self.probe_data)
        blockdev = self.bdevp.blockdev_data['/dev/dasde']
        expected_dict = {
            'device_id': '0.0.2520',
            'id': 'disk-dasde',
            'path': '/dev/dasde',
            'type': 'disk'}
        self.assertDictEqual(expected_dict, self.bdevp.asdict(blockdev))


class TestFilesystemParser(CiTestCase):

    def setUp(self):
        super(TestFilesystemParser, self).setUp()
        self.probe_data = _get_data('probert_storage_diglett.json')
        self.fsp = FilesystemParser(self.probe_data)

    def test_filesystem_parser(self):
        """ FilesystemParser 'class_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['filesystem'],
                             self.fsp.class_data)

    def test_filesystem_parser_blockdev_data(self):
        """ FilesystemParser has blockdev_data attr matches input. """
        self.assertDictEqual(self.probe_data['blockdev'],
                             self.fsp.blockdev_data)

    @skipUnlessJsonSchema()
    def test_filesystem_parser_ignores_fs_without_blockdev(self):
        """ FilesystemParser ignores fsdata from unknown block devices."""
        # add filesystem data for a device not in blockdev_data
        blockdev = self.random_string()
        fs = {'TYPE': 'ext4', 'USAGE': 'filesystem'}
        self.fsp.class_data = {blockdev: fs}
        self.assertNotIn(blockdev, self.fsp.blockdev_data)
        expected_error = (
            "No probe data found for blockdev %s for fs: %s" % (blockdev, fs))
        self.assertEqual(([], [expected_error]), self.fsp.parse())

    def test_filesystem_parser_asdict(self):
        """ FilesystemParse returns expected dictionary for probe data."""
        blockdev = '/dev/bcache0'
        expected_dict = {
            'id': 'format-bcache0',
            'type': 'format',
            'volume': 'bcache0',
            'uuid': '45354276-e0c0-4bf6-9083-f130b89411cc',
            'fstype': 'ext4',
        }
        fs_data = self.fsp.class_data[blockdev]

        self.assertIn(blockdev, self.fsp.blockdev_data)
        self.assertIn(blockdev, self.fsp.class_data)
        self.assertDictEqual(expected_dict,
                             self.fsp.asdict('bcache0', fs_data))


class TestLvmParser(CiTestCase):

    def setUp(self):
        super(TestLvmParser, self).setUp()
        self.probe_data = _get_data('probert_storage_lvm.json')
        self.lvmp = LvmParser(self.probe_data)

    def test_lvm_parser(self):
        """ LvmParser 'class_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['lvm'],
                             self.lvmp.class_data)

    def test_lvm_parser_blockdev_data(self):
        """ LvmParser has blockdev_data attr matches input. """
        self.assertDictEqual(self.probe_data['blockdev'],
                             self.lvmp.blockdev_data)

    def test_lvm_parser_lvm_partition_asdict(self):
        """ LvmParser returns expected dict for known lvm partition."""
        lv_name = "ubuntu-vg/my-storage"
        lv_config = self.lvmp.class_data['logical_volumes'][lv_name]
        expected_dict = {
            'type': 'lvm_partition',
            'name': 'my-storage',
            'id': 'lvm-partition-my-storage',
            'size': '1073741824B',
            'volgroup': 'lvm-volgroup-ubuntu-vg',
        }
        self.assertDictEqual(
            expected_dict, self.lvmp.lvm_partition_asdict(lv_name, lv_config))

    def test_lvm_parser_lvm_volgroup_asdict(self):
        """ LvmParser returns expected dict for known lvm volgroup."""
        vg_name = "vg1"
        lv_config = self.lvmp.class_data['volume_groups'][vg_name]
        expected_dict = {
            'type': 'lvm_volgroup',
            'name': 'vg1',
            'id': 'lvm-volgroup-vg1',
            'devices': ['partition-vda5', 'partition-vda6'],
        }
        self.assertDictEqual(
            expected_dict, self.lvmp.lvm_volgroup_asdict(vg_name, lv_config))

    @skipUnlessJsonSchema()
    def test_lvm_parser_parses_all_lvs_vgs(self):
        """ LvmParser returns expected dicts for known lvm probe data."""
        configs, errors = self.lvmp.parse()
        self.assertEqual(5, len(configs))
        self.assertEqual(0, len(errors))


class TestRaidParser(CiTestCase):

    def setUp(self):
        super(TestRaidParser, self).setUp()
        self.probe_data = _get_data('probert_storage_mdadm_bcache.json')
        self.raidp = RaidParser(self.probe_data)

    def test_raid_parser(self):
        """ RaidParser 'class_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['raid'],
                             self.raidp.class_data)

    def test_raid_asdict(self):
        """ RaidParser converts known raid_data to expected dict. """
        devname = "/dev/md0"
        expected_dict = {
            'type': 'raid',
            'id': 'raid-md0',
            'name': 'md0',
            'raidlevel': 'raid5',
            'devices': ['disk-vde', 'disk-vdf', 'disk-vdg'],
            'spare_devices': [],
        }
        raid_data = self.raidp.class_data[devname]
        self.assertDictEqual(expected_dict, self.raidp.asdict(raid_data))

    @skipUnlessJsonSchema()
    def test_raid_parser_parses_all_lvs_vgs(self):
        """ RaidParser returns expected dicts for known raid probe data."""
        configs, errors = self.raidp.parse()
        self.assertEqual(1, len(configs))
        self.assertEqual(0, len(errors))


class TestDasdParser(CiTestCase):

    def setUp(self):
        super(TestDasdParser, self).setUp()
        self.probe_data = _get_data('probert_storage_dasd.json')
        self.dasd = DasdParser(self.probe_data)

    def test_dasd_parser(self):
        """ DasdParser 'class_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['dasd'],
                             self.dasd.class_data)

    def test_dasd_asdict(self):
        """ DasdParser converts known dasd_data to expected dict. """
        devname = "/dev/dasda"
        expected_dict = {
            'type': 'dasd',
            'id': 'dasd-dasda',
            'device_id': '0.0.1522',
            'blocksize': 4096,
            'mode': 'quick',
            'disk_layout': 'cdl',
        }
        dasd_data = self.dasd.class_data[devname]
        self.assertDictEqual(expected_dict, self.dasd.asdict(dasd_data))

    @skipUnlessJsonSchema()
    def test_dasd_parser_parses_all_dasd_devs(self):
        """ DasdParser returns expected dicts for known dasd probe data."""
        configs, errors = self.dasd.parse()
        self.assertEqual(5, len(configs))
        self.assertEqual(0, len(errors))


class TestDmCryptParser(CiTestCase):

    def setUp(self):
        super(TestDmCryptParser, self).setUp()
        self.probe_data = _get_data('probert_storage_dmcrypt.json')
        self.dmcrypt = DmcryptParser(self.probe_data)

    def test_dmcrypt_parser(self):
        """ DmcryptParser 'class_data' on instance matches input. """
        self.assertDictEqual(self.probe_data['dmcrypt'],
                             self.dmcrypt.class_data)

    def test_dmcrypt_asdict(self):
        """ DmcryptParser converts known dmcrypt_data to expected dict. """
        devname = "dmcrypt0"
        expected_dict = {
            'type': 'dm_crypt',
            'id': 'dmcrypt-dmcrypt0',
            'dm_name': devname,
            'key': '',
            'volume': 'lvm-partition-lv3',
        }
        dmcrypt_data = self.dmcrypt.class_data[devname]
        self.assertDictEqual(expected_dict, self.dmcrypt.asdict(dmcrypt_data))

    @skipUnlessJsonSchema()
    def test_dmcrypt_parser_parses_all_crypt_devs(self):
        """ DmcryptParser returns expected dicts for known crypt probe data."""
        configs, errors = self.dmcrypt.parse()
        self.assertEqual(1, len(configs))
        self.assertEqual(0, len(errors))


class TestMountParser(CiTestCase):

    def setUp(self):
        super(TestMountParser, self).setUp()
        self.probe_data = _get_data('probert_storage_diglett.json')
        self.mountp = MountParser(self.probe_data)

    def test_mount_parser(self):
        """ MountParser 'class_data' on instance matches input. """
        self.assertEqual(self.probe_data['mount'],
                         self.mountp.class_data)

    def test_mount_asdict(self):
        source_mount = {
            'fstype': 'ext4',
            'options': 'rw,relatime',
            'source': '/dev/bcache0',
            'target': '/'
        }
        expected_dict = {
            'type': 'mount',
            'id': 'mount-disk-bcache0',
            'path': '/',
            'device': 'format-disk-bcache0'
        }
        self.assertDictEqual(expected_dict, self.mountp.asdict(source_mount))

    @skipUnlessJsonSchema()
    def test_mount_parser_parses_all_blockdev_mounts(self):
        """ MountParser returns expected dicts for known mount probe data."""
        configs, errors = self.mountp.parse()
        self.assertEqual(4, len(configs))
        self.assertEqual(0, len(errors))


class TestZfsParser(CiTestCase):

    def setUp(self):
        super(TestZfsParser, self).setUp()
        self.probe_data = _get_data('probert_storage_zfs.json')
        self.zfsp = ZfsParser(self.probe_data)

    def test_zfs_parser(self):
        """ ZfsParser 'class_data' on instance matches input. """
        self.assertEqual(self.probe_data['zfs'],
                         self.zfsp.class_data)

    def test_zfs_get_local_ds_properties(self):
        """ ZfsParser extracts non-default properties from zfs datasets. """
        zpool = 'rpool'
        dataset = 'rpool'
        expected_properties = {
            'atime': 'off',
            'canmount': 'off',
            'mountpoint': '/',
        }

        zpool_data = self.zfsp.class_data['zpools'][zpool]['datasets'][dataset]
        print(zpool_data)
        self.assertDictEqual(expected_properties,
                             self.zfsp.get_local_ds_properties(zpool_data))

    def test_zfs_zpool_asdict(self):
        """ ZfsParser extracts expected dict from zpool data. """
        zpool = 'rpool'
        expected_zpool = {
            'type': 'zpool',
            'id': 'zpool-partition-vda1-rpool',
            'pool': 'rpool',
            'vdevs': ['partition-vda1'],
        }

        zpool_data = self.zfsp.class_data['zpools'][zpool]
        self.assertDictEqual(expected_zpool,
                             self.zfsp.zpool_asdict(zpool, zpool_data))

    def test_zfs_zfs_asdict(self):
        """ ZfsParser extracts expected dict from zfs dataset data. """
        dataset = 'rpool/ROOT/zfsroot'
        zpool_entry = {
            'type': 'zpool',
            'id': 'zpool-partition-vda1-rpool',
            'pool': 'rpool',
            'vdevs': ['partition-vda1'],
        }
        ds_props = {
                'canmount': 'noauto',
                'mountpoint': '/',
        }
        expected_zfs = {
            'type': 'zfs',
            'id': 'zfs-rpool-ROOT-zfsroot',
            'pool': 'zpool-partition-vda1-rpool',
            'volume': '/ROOT/zfsroot',
            'properties': ds_props,
        }
        self.assertDictEqual(
            expected_zfs, self.zfsp.zfs_asdict(dataset, ds_props, zpool_entry))

    @skipUnlessJsonSchema()
    def test_zfs_parser_parses_all_blockdev_mounts(self):
        """ ZfsParser returns expected dicts for known zfs probe data."""
        configs, errors = self.zfsp.parse()
        self.assertEqual(5, len(configs))
        self.assertEqual(0, len(errors))
        zpools = [cfg for cfg in configs if cfg['type'] == 'zpool']
        zfs = [cfg for cfg in configs if cfg['type'] == 'zfs']
        self.assertEqual(1, len(zpools))
        self.assertEqual(4, len(zfs))


class TestExtractStorageConfig(CiTestCase):

    def setUp(self):
        super(TestExtractStorageConfig, self).setUp()
        self.probe_data = _get_data('live-iso.json')

    @skipUnlessJsonSchema()
    def test_live_iso(self):
        """ verify live-iso extracted storage-config finds target disk. """
        extracted = storage_config.extract_storage_config(self.probe_data)
        self.assertEqual(
            {'storage': {'version': 1,
                         'config': [{'id': 'disk-sda', 'path': '/dev/sda',
                                     'serial': 'QEMU_HARDDISK_QM00001',
                                     'type': 'disk'}]}}, extracted)

    @skipUnlessJsonSchema()
    def test_probe_handles_missing_keys(self):
        """ verify extract handles missing probe_data keys """
        for missing_key in self.probe_data.keys():
            probe_data = copy.deepcopy(self.probe_data)
            del probe_data[missing_key]
            extracted = storage_config.extract_storage_config(probe_data)
            if missing_key != 'blockdev':
                self.assertEqual(
                    {'storage':
                        {'version': 1,
                         'config': [{'id': 'disk-sda', 'path': '/dev/sda',
                                     'serial': 'QEMU_HARDDISK_QM00001',
                                     'type': 'disk'}]}}, extracted)
            else:
                # empty config without blockdev data
                self.assertEqual({'storage': {'config': [], 'version': 1}},
                                 extracted)

    @skipUnlessJsonSchema()
    def test_find_all_multipath(self):
        """ verify probed multipath paths are included in config. """
        self.probe_data = _get_data('probert_storage_multipath.json')
        extracted = storage_config.extract_storage_config(self.probe_data)
        config = extracted['storage']['config']
        blockdev = self.probe_data['blockdev']

        for mpmap in self.probe_data['multipath']['maps']:
            nr_disks = int(mpmap['paths'])
            mp_name = blockdev['/dev/%s' % mpmap['sysfs']]['DM_NAME']
            matched_disks = [cfg for cfg in config
                             if cfg['type'] == 'disk' and
                             cfg.get('multipath', '') == mp_name]
            self.assertEqual(nr_disks, len(matched_disks))

    @skipUnlessJsonSchema()
    def test_find_raid_partition(self):
        """ verify probed raid partitions are found. """
        self.probe_data = _get_data('probert_storage_raid1_partitions.json')
        extracted = storage_config.extract_storage_config(self.probe_data)
        config = extracted['storage']['config']
        raids = [cfg for cfg in config if cfg['type'] == 'raid']
        raid_partitions = [cfg for cfg in config
                           if cfg['type'] == 'partition' and
                           cfg['id'].startswith('raid')]
        self.assertEqual(1, len(raids))
        self.assertEqual(1, len(raid_partitions))
        self.assertEqual({'id': 'raid-md1', 'type': 'raid',
                          'raidlevel': 'raid1', 'name': 'md1',
                          'devices': ['partition-vdb1', 'partition-vdc1'],
                          'spare_devices': []}, raids[0])
        self.assertEqual({'id': 'raid-md1p1', 'type': 'partition',
                          'size': 4285530112, 'flag': 'linux', 'number': 1,
                          'device': 'raid-md1', 'offset': 1048576},
                         raid_partitions[0])

    @skipUnlessJsonSchema()
    def test_find_extended_partition(self):
        """ finds extended partition and set flag in config """
        self.probe_data = _get_data('probert_storage_msdos_mbr_extended.json')
        extracted = storage_config.extract_storage_config(self.probe_data)
        config = extracted['storage']['config']
        partitions = [cfg for cfg in config if cfg['type'] == 'partition']
        extended = [part for part in partitions if part['flag'] == 'extended']
        self.assertEqual(1, len(extended))

    @skipUnlessJsonSchema()
    def test_blockdev_detects_nvme_multipath_devices(self):
        self.probe_data = _get_data('probert_storage_nvme_multipath.json')
        extracted = storage_config.extract_storage_config(self.probe_data)
        config = extracted['storage']['config']
        disks = [cfg for cfg in config if cfg['type'] == 'disk']
        expected_dict = {
            'id': 'disk-nvme0n1',
            'path': '/dev/nvme0n1',
            'ptable': 'gpt',
            'serial': 'SAMSUNG MZPLL3T2HAJQ-00005_S4CCNE0M300015',
            'type': 'disk',
            'wwn': 'eui.344343304d3000150025384500000004',
        }
        self.assertEqual(1, len(disks))
        self.assertEqual(expected_dict, disks[0])

    @skipUnlessJsonSchema()
    def test_blockdev_skips_invalid_wwn(self):
        self.probe_data = _get_data('probert_storage_bogus_wwn.json')
        extracted = storage_config.extract_storage_config(self.probe_data)
        config = extracted['storage']['config']
        disks = [cfg for cfg in config
                 if cfg['type'] == 'disk' and cfg['path'] == '/dev/sda']
        expected_dict = {
            'id': 'disk-sda',
            'path': '/dev/sda',
            'ptable': 'gpt',
            'serial': 'Corsair_Force_GS_13207907000097410026',
            'type': 'disk',
        }
        self.assertEqual(1, len(disks))
        self.assertEqual(expected_dict, disks[0])


# vi: ts=4 expandtab syntax=python
