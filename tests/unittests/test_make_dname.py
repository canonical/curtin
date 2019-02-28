# This file is part of curtin. See LICENSE file for copyright and license info.

import mock

import textwrap
import uuid

from curtin.commands import block_meta
from .helpers import CiTestCase


class TestMakeDname(CiTestCase):
    state = {'scratch': '/tmp/null'}
    rules_d = '/tmp/null/rules.d'
    rule_file = '/tmp/null/rules.d/{}.rules'
    disk_serial = 'abcdefg'
    disk_wwn = '0x1234567890'
    storage_config = {
        'disk1': {'type': 'disk', 'id': 'disk1', 'name': 'main_disk',
                  'serial': disk_serial},
        'disk_noid': {'type': 'disk', 'id': 'disk_noid', 'name': 'main_disk'},
        'disk1p1': {'type': 'partition', 'id': 'disk1p1', 'device': 'disk1'},
        'disk1p2': {'type': 'partition', 'id': 'disk1p2', 'device': 'disk1',
                    'name': 'custom-partname'},
        'disk2': {'type': 'disk', 'id': 'disk2', 'wwn': disk_wwn,
                  'name': 'in_valid/name!@#$% &*(+disk'},
        'disk2p1': {'type': 'partition', 'id': 'disk2p1', 'device': 'disk2'},
        'md_id': {'type': 'raid', 'id': 'md_id', 'name': 'mdadm_name'},
        'md_id2': {'type': 'raid', 'id': 'md_id2', 'name': 'mdadm/name'},
        'lvol_id': {'type': 'lvm_volgroup', 'id': 'lvol_id', 'name': 'vg1'},
        'lpart_id': {'type': 'lvm_partition', 'id': 'lpart_id',
                     'name': 'lpartition1', 'volgroup': 'lvol_id'},
        'lpart2_id': {'type': 'lvm_partition', 'id': 'lpart2_id',
                      'name': 'lvm part/2', 'volgroup': 'lvol_id'},
        'bcache1_id': {'type': 'bcache', 'id': 'bcache1_id',
                       'name': 'my-cached-data'},
        'iscsi1': {'type': 'disk', 'id': 'iscsi1', 'name': 'iscsi_disk1'}
    }
    bcache_super_show = {
        'sb.version': '1 [backing device]',
        'dev.uuid': 'f36394c0-3cc0-4423-8d6f-ffac130f171a',
    }
    disk_blkid = textwrap.dedent("""
        DEVNAME=/dev/sda
        PTUUID={}
        PTTYPE=dos""")
    part_blkid = textwrap.dedent("""
        DEVNAME=/dev/sda1
        UUID=f3e6efc2-d586-4b35-a681-dffb987c66fd
        TYPE=ext2
        PARTUUID={}""")
    trusty_blkid = ""

    def _make_mock_subp_blkid(self, ident, blkid_out):

        def subp_blkid(cmd, capture=False, rcs=None, retries=None):
            return (blkid_out.format(ident), None)

        return subp_blkid

    def _formatted_rule(self, identifiers, target):
        rule = ['SUBSYSTEM=="block"', 'ACTION=="add|change"']
        rule.extend(['ENV{%s}=="%s"' % ident for ident in identifiers])
        rule.append('SYMLINK+="disk/by-dname/{}"\n'.format(target))
        return ', '.join(rule)

    def _content(self, rules=[]):
        return "\n".join(['# Written by curtin'] + rules)

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_disk(self, mock_util, mock_get_path, mock_log,
                             mock_udev):
        disk_ptuuid = str(uuid.uuid1())
        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            disk_ptuuid, self.disk_blkid)
        mock_util.load_command_environment.return_value = self.state

        rule_identifiers = [('ID_PART_TABLE_UUID', disk_ptuuid)]
        id_rule_identifiers = [('ID_SERIAL', self.disk_serial)]
        wwn_rule_identifiers = [('ID_WWN_WITH_EXTENSION', self.disk_wwn)]

        def _drule(devtype, match):
            return [('DEVTYPE', devtype)] + [m for m in match]

        def drule(match):
            return _drule('disk', match)

        def prule(match):
            return _drule('partition', match)

        # simple run
        mock_udev.side_effect = (
            [{'DEVTYPE': 'disk', 'ID_SERIAL': self.disk_serial},
             {'DEVTYPE': 'disk', 'ID_WWN_WITH_EXTENSION': self.disk_wwn}])
        res_dname = 'main_disk'
        block_meta.make_dname('disk1', self.storage_config)
        mock_util.ensure_dir.assert_called_with(self.rules_d)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(drule(rule_identifiers),
                                      res_dname),
                 self._formatted_rule(drule(id_rule_identifiers),
                                      res_dname),
                 self._formatted_rule(prule(id_rule_identifiers),
                                      "%s-part%%n" % res_dname)]))

        # run invalid dname
        res_dname = 'in_valid-name----------disk'
        block_meta.make_dname('disk2', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(drule(rule_identifiers),
                                      res_dname),
                 self._formatted_rule(drule(wwn_rule_identifiers),
                                      res_dname),
                 self._formatted_rule(prule(wwn_rule_identifiers),
                                      "%s-part%%n" % res_dname)]))

        # iscsi disk with no config, but info returns serial and wwn
        mock_udev.side_effect = (
            [{'DEVTYPE': 'disk', 'ID_SERIAL': self.disk_serial,
              'DEVTYPE': 'disk', 'ID_WWN_WITH_EXTENSION': self.disk_wwn}])
        res_dname = 'iscsi_disk1'
        block_meta.make_dname('iscsi1', self.storage_config)
        mock_util.ensure_dir.assert_called_with(self.rules_d)
        self.assertTrue(mock_log.debug.called)
        both_rules = (wwn_rule_identifiers + id_rule_identifiers)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(drule(rule_identifiers), res_dname),
                 self._formatted_rule(drule(both_rules), res_dname),
                 self._formatted_rule(prule(both_rules),
                                      "%s-part%%n" % res_dname)]))

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_failures(self, mock_util, mock_get_path, mock_log,
                                 mock_udev):
        mock_udev.side_effect = ([{'DEVTYPE': 'disk'}, {'DEVTYPE': 'disk'}])

        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            '', self.trusty_blkid)
        mock_util.load_command_environment.return_value = self.state

        warning_msg = "Can't find a uuid for volume: {}. Skipping dname."

        # disk with no PT_UUID
        disk = 'disk_noid'
        block_meta.make_dname(disk, self.storage_config)
        mock_log.warning.assert_called_with(warning_msg.format(disk))
        self.assertFalse(mock_util.write_file.called)

        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            '', self.trusty_blkid)
        # partition with no PART_UUID
        block_meta.make_dname('disk1p1', self.storage_config)
        mock_log.warning.assert_called_with(warning_msg.format('disk1p1'))
        self.assertFalse(mock_util.write_file.called)

    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_partition(self, mock_util, mock_get_path, mock_log):
        part_uuid = str(uuid.uuid1())
        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            part_uuid, self.part_blkid)
        mock_util.load_command_environment.return_value = self.state

        rule_identifiers = [
            ('DEVTYPE', 'partition'),
            ('ID_PART_ENTRY_UUID', part_uuid),
        ]

        # simple run
        res_dname = 'custom-partname'
        block_meta.make_dname('disk1p2', self.storage_config)
        mock_util.ensure_dir.assert_called_with(self.rules_d)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

    @mock.patch('curtin.commands.block_meta.mdadm')
    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_raid(self, mock_util, mock_get_path, mock_log,
                             mock_mdadm):
        md_uuid = str(uuid.uuid1())
        mock_mdadm.mdadm_query_detail.return_value = {'MD_UUID': md_uuid}
        mock_util.load_command_environment.return_value = self.state
        rule_identifiers = [('MD_UUID', md_uuid)]

        # simple
        res_dname = 'mdadm_name'
        block_meta.make_dname('md_id', self.storage_config)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

        # invalid name
        res_dname = 'mdadm-name'
        block_meta.make_dname('md_id2', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_lvm_partition(self, mock_util, mock_get_path,
                                      mock_log):
        mock_util.load_command_environment.return_value = self.state

        # simple
        res_dname = 'vg1-lpartition1'
        rule_identifiers = [('DM_NAME', res_dname)]
        block_meta.make_dname('lpart_id', self.storage_config)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

        # with invalid name
        res_dname = 'vg1-lvm-part-2'
        rule_identifiers = [('DM_NAME', 'vg1-lvm part/2')]
        block_meta.make_dname('lpart2_id', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.bcache')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_bcache(self, mock_util, mock_get_path, mock_bcache,
                               mock_log):
        """ check bcache dname uses backing device uuid to link dname """
        mock_get_path.return_value = '/my/dev/huge-storage'
        mock_bcache.superblock_asdict.return_value = self.bcache_super_show
        mock_util.load_command_environment.return_value = self.state

        res_dname = 'my-cached-data'
        backing_uuid = 'f36394c0-3cc0-4423-8d6f-ffac130f171a'
        rule_identifiers = [('CACHED_UUID', backing_uuid)]
        block_meta.make_dname('bcache1_id', self.storage_config)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._content(
                [self._formatted_rule(rule_identifiers, res_dname)]))

    def test_sanitize_dname(self):
        unsanitized_to_sanitized = [
            ('main_disk', 'main_disk'),
            ('main-disk', 'main-disk'),
            ('main/disk', 'main-disk'),
            ('main disk', 'main-disk'),
            ('m.a/i*n#  d~i+sk', 'm-a-i-n---d-i-sk'),
        ]
        for (unsanitized, sanitized) in unsanitized_to_sanitized:
            self.assertEqual(block_meta.sanitize_dname(unsanitized), sanitized)


class TestMakeDnameById(CiTestCase):

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    def test_bad_path(self, m_udev):
        """test dname_byid raises ValueError on invalid path."""
        mypath = None
        with self.assertRaises(ValueError):
            block_meta.make_dname_byid(mypath)

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    def test_non_disk(self, m_udev):
        """test dname_byid raises ValueError on DEVTYPE != 'disk'"""
        mypath = "/dev/" + self.random_string()
        m_udev.return_value = {'DEVTYPE': 'not_a_disk'}
        with self.assertRaises(ValueError):
            block_meta.make_dname_byid(mypath)

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    def test_disk_with_no_id_wwn(self, m_udev):
        """test dname_byid raises RuntimeError on device without ID or WWN."""
        mypath = "/dev/" + self.random_string()
        m_udev.return_value = {'DEVTYPE': 'disk'}
        self.assertEqual([], block_meta.make_dname_byid(mypath))

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    def test_udevinfo_not_called_if_info_provided(self, m_udev):
        """dname_byid does not invoke udevadm_info if using info dict"""
        myserial = self.random_string()
        self.assertEqual(
            [['ENV{ID_SERIAL}=="%s"' % myserial]],
            block_meta.make_dname_byid(
                self.random_string(),
                info={'DEVTYPE': 'disk', 'ID_SERIAL': myserial}))
        self.assertEqual(0, m_udev.call_count)

    @mock.patch('curtin.commands.block_meta.udevadm_info')
    def test_udevinfo_called_if_info_not_provided(self, m_udev):
        """dname_byid should call udevadm_info if no data given."""
        myserial = self.random_string()
        mypath = "/dev/" + self.random_string()
        m_udev.return_value = {
            'DEVTYPE': 'disk', 'ID_SERIAL': myserial, 'DEVNAME': mypath}
        self.assertEqual(
            [['ENV{ID_SERIAL}=="%s"' % myserial]],
            block_meta.make_dname_byid(mypath))
        self.assertEqual(
            [mock.call(path=mypath)], m_udev.call_args_list)

    def test_disk_with_only_serial(self):
        """test dname_byid returns rules for ID_SERIAL"""
        mypath = "/dev/" + self.random_string()
        myserial = self.random_string()
        info = {'DEVTYPE': 'disk', 'DEVNAME': mypath, 'ID_SERIAL': myserial}
        self.assertEqual(
            [['ENV{ID_SERIAL}=="%s"' % myserial]],
            block_meta.make_dname_byid(mypath, info=info))

    def test_disk_with_only_wwn(self):
        """test dname_byid returns rules for ID_WWN_WITH_EXTENSION"""
        mypath = "/dev/" + self.random_string()
        mywwn = self.random_string()
        info = {'DEVTYPE': 'disk', 'DEVNAME': mypath,
                'ID_WWN_WITH_EXTENSION': mywwn}
        self.assertEqual(
            [['ENV{ID_WWN_WITH_EXTENSION}=="%s"' % mywwn]],
            block_meta.make_dname_byid(mypath, info=info))

    def test_disk_with_both_id_wwn(self):
        """test dname_byid returns rules with both ID_WWN_* and ID_SERIAL"""
        mypath = "/dev/" + self.random_string()
        myserial = self.random_string()
        mywwn = self.random_string()
        info = {'DEVTYPE': 'disk', 'ID_SERIAL': myserial,
                'ID_WWN_WITH_EXTENSION': mywwn,
                'DEVNAME': mypath}
        self.assertEqual(
            [[
                'ENV{ID_WWN_WITH_EXTENSION}=="%s"' % mywwn,
                'ENV{ID_SERIAL}=="%s"' % myserial,
            ]],
            block_meta.make_dname_byid(mypath, info=info))

    def test_disk_with_short_ids(self):
        """test dname_byid returns rules w/ both ID_WWN and ID_SERIAL_SHORT."""
        mypath = "/dev/" + self.random_string()
        myserial = self.random_string()
        mywwn = self.random_string()
        info = {'DEVTYPE': 'disk', 'ID_SERIAL_SHORT': myserial,
                'ID_WWN': mywwn,
                'DEVNAME': mypath}
        self.assertEqual(
            [[
                'ENV{ID_WWN}=="%s"' % mywwn,
                'ENV{ID_SERIAL_SHORT}=="%s"' % myserial,
            ]],
            block_meta.make_dname_byid(mypath, info=info))

    def test_disk_with_all_ids(self):
        """test dname_byid returns rules w/ all WWN and SERIAL values."""
        mypath = "/dev/" + self.random_string()
        myserial_short = self.random_string()
        myserial = myserial_short + "_" + myserial_short
        mywwn = self.random_string()
        mywwn_ext = mywwn + "_" + mywwn
        info = {'DEVTYPE': 'disk', 'ID_SERIAL_SHORT': myserial_short,
                'ID_SERIAL': myserial,
                'ID_WWN': mywwn,
                'ID_WWN_WITH_EXTENSION': mywwn_ext,
                'DEVNAME': mypath}
        self.assertEqual(
            [[
                'ENV{ID_WWN_WITH_EXTENSION}=="%s"' % mywwn_ext,
                'ENV{ID_WWN}=="%s"' % mywwn,
                'ENV{ID_SERIAL}=="%s"' % myserial,
                'ENV{ID_SERIAL_SHORT}=="%s"' % myserial_short,
            ]],
            block_meta.make_dname_byid(mypath, info=info))

# vi: ts=4 expandtab syntax=python
