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
    storage_config = {
        'disk1': {'type': 'disk', 'id': 'disk1', 'name': 'main_disk'},
        'disk1p1': {'type': 'partition', 'id': 'disk1p1', 'device': 'disk1'},
        'disk2': {'type': 'disk', 'id': 'disk2',
                  'name': 'in_valid/name!@#$% &*(+disk'},
        'disk2p1': {'type': 'partition', 'id': 'disk2p1', 'device': 'disk2'},
        'md_id': {'type': 'raid', 'id': 'md_id', 'name': 'mdadm_name'},
        'md_id2': {'type': 'raid', 'id': 'md_id2', 'name': 'mdadm/name'},
        'lvol_id': {'type': 'lvm_volgroup', 'id': 'lvol_id', 'name': 'vg1'},
        'lpart_id': {'type': 'lvm_partition', 'id': 'lpart_id',
                     'name': 'lpartition1', 'volgroup': 'lvol_id'},
        'lpart2_id': {'type': 'lvm_partition', 'id': 'lpart2_id',
                      'name': 'lvm part/2', 'volgroup': 'lvol_id'},
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
        rule.append('SYMLINK+="disk/by-dname/{}"'.format(target))
        return ', '.join(rule)

    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_disk(self, mock_util, mock_get_path, mock_log):
        disk_ptuuid = str(uuid.uuid1())
        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            disk_ptuuid, self.disk_blkid)
        mock_util.load_command_environment.return_value = self.state
        rule_identifiers = [
            ('DEVTYPE', 'disk'),
            ('ID_PART_TABLE_UUID', disk_ptuuid)
        ]

        # simple run
        res_dname = 'main_disk'
        block_meta.make_dname('disk1', self.storage_config)
        mock_util.ensure_dir.assert_called_with(self.rules_d)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

        # run invalid dname
        res_dname = 'in_valid-name----------disk'
        block_meta.make_dname('disk2', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

    @mock.patch('curtin.commands.block_meta.LOG')
    @mock.patch('curtin.commands.block_meta.get_path_to_storage_volume')
    @mock.patch('curtin.commands.block_meta.util')
    def test_make_dname_failures(self, mock_util, mock_get_path, mock_log):
        mock_util.subp.side_effect = self._make_mock_subp_blkid(
            '', self.trusty_blkid)
        mock_util.load_command_environment.return_value = self.state

        warning_msg = "Can't find a uuid for volume: {}. Skipping dname."

        # disk with no PT_UUID
        block_meta.make_dname('disk1', self.storage_config)
        mock_log.warning.assert_called_with(warning_msg.format('disk1'))
        self.assertFalse(mock_util.write_file.called)

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
        res_dname = 'main_disk-part1'
        block_meta.make_dname('disk1p1', self.storage_config)
        mock_util.ensure_dir.assert_called_with(self.rules_d)
        self.assertTrue(mock_log.debug.called)
        self.assertFalse(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

        # run invalid dname
        res_dname = 'in_valid-name----------disk-part1'
        block_meta.make_dname('disk2p1', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

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
            self._formatted_rule(rule_identifiers, res_dname))

        # invalid name
        res_dname = 'mdadm-name'
        block_meta.make_dname('md_id2', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

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
            self._formatted_rule(rule_identifiers, res_dname))

        # with invalid name
        res_dname = 'vg1-lvm-part-2'
        rule_identifiers = [('DM_NAME', 'vg1-lvm part/2')]
        block_meta.make_dname('lpart2_id', self.storage_config)
        self.assertTrue(mock_log.warning.called)
        mock_util.write_file.assert_called_with(
            self.rule_file.format(res_dname),
            self._formatted_rule(rule_identifiers, res_dname))

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

# vi: ts=4 expandtab syntax=python
