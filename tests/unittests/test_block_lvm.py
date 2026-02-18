# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.block import lvm

from .helpers import CiTestCase
from unittest import mock


class TestBlockLvm(CiTestCase):
    vg_name = 'ubuntu-volgroup'

    @mock.patch('curtin.block.lvm.util')
    def test_query_lvmreport(self, mock_util):
        """make sure lvm._filter_lvm_info filters properly"""
        match_name = "vg_name"
        query_results = [{"lv_name": "lv_1"}, {"lv_name": "lv_2"}]
        lvtool_name = 'lvs'
        fields = ['lv_name']
        mock_util.subp.return_value = (
            """
            {
                "report": [
                    {
                        "lv": [
                            {"lv_name": "lv_1", "vg_name": "ubuntu-volgroup"},
                            {"lv_name": "lv_2", "vg_name": "ubuntu-volgroup"},
                            {"lv_name": "lv_3", "vg_name": "ubuntu-vg-2"},
                            {"lv_name": "lv_4", "vg_name": "ubuntu-vg-2"}
                        ]
                    }
                ]
            }
            """, "")
        result_list = lvm._query_lvmreport(
                lvtool_name, filters={match_name: self.vg_name}, fields=fields,
                report_subtype="lv", reportidx=0)
        self.assertEqual(len(result_list), 2)
        mock_util.subp.assert_called_with(
            [
                lvtool_name, '--reportformat=json', '--units=B',
                "--options", "lv_name,vg_name",
            ], capture=True)
        self.assertEqual(result_list, query_results)
        # make sure _query_lvmreport can fail gracefully if no match
        result_list = lvm._query_lvmreport(
                lvtool_name, filters={match_name: 'inexistent'}, fields=fields,
                report_subtype="lv", reportidx=0)
        self.assertEqual(len(result_list), 0)

    @mock.patch('curtin.block.lvm._query_lvmreport')
    def test_get_lvm_info(self, mock_query_lvm_report):
        """
        make sure that the get lvm info functions make the right calls to
        lvm._filter_lvm_info
        """
        lvm.get_pvols_in_volgroup(self.vg_name)
        mock_query_lvm_report.assert_called_with(
            'pvs',
            fields=['pv_name'],
            filters={'vg_name': self.vg_name},
            report_subtype='pv', reportidx=0)
        lvm.get_lvols_in_volgroup(self.vg_name)
        mock_query_lvm_report.assert_called_with(
            'lvs', fields=['lv_name'],
            filters={'vg_name': self.vg_name},
            report_subtype='lv', reportidx=0)

    @mock.patch('curtin.block.lvm.util')
    def test_split_lvm_name(self, mock_util):
        """
        make sure that split_lvm_name makes the right call to dmsetup splitname
        """
        lv_name = 'root_lvol'
        full_name = '{}-{}'.format(self.vg_name, lv_name)
        mock_util.subp.return_value = (
            '  {vg_name}{sep}{lv_name} '.format(
                vg_name=self.vg_name, lv_name=lv_name, sep=lvm._SEP), '')
        (res_vg_name, res_lv_name) = lvm.split_lvm_name(full_name)
        self.assertEqual(res_vg_name, self.vg_name)
        self.assertEqual(res_lv_name, lv_name)
        mock_util.subp.assert_called_with(
            ['dmsetup', 'splitname', full_name, '-c', '--noheadings',
             '--separator', lvm._SEP, '-o', 'vg_name,lv_name'], capture=True)

    @mock.patch('curtin.block.lvm.lvmetad_running')
    @mock.patch('curtin.block.lvm.util')
    @mock.patch('curtin.block.lvm.distro')
    def test_lvm_scan(self, mock_distro, mock_util, mock_lvmetad):
        """check that lvm_scan formats commands correctly for each release"""
        for (count, (codename, lvmetad_status, use_cache)) in enumerate(
                [('precise', False, False),
                 ('trusty', False, False),
                 ('xenial', False, False), ('xenial', True, True),
                 (None, True, True), (None, False, False)]):
            cmds = [['pvscan'], ['vgscan']]
            mock_distro.lsb_release.return_value = {'codename': codename}
            mock_lvmetad.return_value = lvmetad_status
            lvm.lvm_scan()
            expected = [cmd for cmd in cmds]
            for cmd in expected:
                if lvmetad_status:
                    cmd.append('--cache')

            calls = [mock.call(cmd, capture=True) for cmd in expected]
            self.assertEqual(len(expected), len(mock_util.subp.call_args_list))
            mock_util.subp.assert_has_calls(calls)
            mock_util.subp.reset_mock()

    @mock.patch('curtin.block.lvm.lvmetad_running')
    @mock.patch('curtin.block.lvm.util')
    @mock.patch('curtin.block.lvm.distro')
    def test_lvm_scan_multipath(self, mock_distro, mock_util, mock_lvmetad):
        """check that lvm_scan formats commands correctly for multipath."""
        cmds = [['pvscan'], ['vgscan']]
        mock_distro.lsb_release.return_value = {'codename': 'focal'}
        mock_lvmetad.return_value = False
        lvm.lvm_scan(multipath=True)
        cmd_filter = [
            '--config',
            'devices{ filter = [ "a|%s|", "a|%s|", "r|.*|" ] }' % (
                '/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*')
        ]
        expected = [cmd + cmd_filter for cmd in cmds]
        calls = [mock.call(cmd, capture=True) for cmd in expected]
        self.assertEqual(len(expected), len(mock_util.subp.call_args_list))
        mock_util.subp.assert_has_calls(calls)


class TestBlockLvmMultipathFilter(CiTestCase):

    def test_generate_multipath_dev_mapper_filter(self):
        expected = 'filter = [ "a|%s|", "a|%s|", "r|.*|" ]' % (
            '/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*')
        self.assertEqual(expected, lvm.generate_multipath_dev_mapper_filter())

    def test_generate_multipath_dm_uuid_filter(self):
        expected = (
            'filter = [ "a|%s|", "a|%s|", "r|.*|" ]' % (
                '/dev/disk/by-id/dm-uuid-.*mpath-.*',
                '/dev/disk/by-id/.*dm_crypt-.*'))
        self.assertEqual(expected, lvm.generate_multipath_dm_uuid_filter())


# vi: ts=4 expandtab syntax=python
