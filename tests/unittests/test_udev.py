# This file is part of curtin. See LICENSE file for copyright and license info.

import mock

from curtin import udev
from curtin import util
from .helpers import CiTestCase


UDEVADM_INFO_QUERY = """\
DEVLINKS='/dev/disk/by-id/nvme-eui.0025388b710116a1'
DEVNAME='/dev/nvme0n1'
DEVPATH='/devices/pci0000:00/0000:00:1c.4/0000:05:00.0/nvme/nvme0/nvme0n1'
DEVTYPE='disk'
ID_PART_TABLE_TYPE='gpt'
ID_PART_TABLE_UUID='ea0b9ddc-a114-4e01-b257-750d86e3a944'
ID_SERIAL='SAMSUNG MZVLB1T0HALR-000L7_S3TPNY0JB00151'
ID_SERIAL_SHORT='S3TPNY0JB00151'
MAJOR='259'
MINOR='0'
SUBSYSTEM='block'
TAGS=':systemd:'
USEC_INITIALIZED='2026691'
"""

INFO_DICT = {
    'DEVLINKS': ['/dev/disk/by-id/nvme-eui.0025388b710116a1'],
    'DEVNAME': '/dev/nvme0n1',
    'DEVPATH':
        '/devices/pci0000:00/0000:00:1c.4/0000:05:00.0/nvme/nvme0/nvme0n1',
    'DEVTYPE': 'disk',
    'ID_PART_TABLE_TYPE': 'gpt',
    'ID_PART_TABLE_UUID': 'ea0b9ddc-a114-4e01-b257-750d86e3a944',
    'ID_SERIAL': 'SAMSUNG MZVLB1T0HALR-000L7_S3TPNY0JB00151',
    'ID_SERIAL_SHORT': 'S3TPNY0JB00151',
    'MAJOR': '259',
    'MINOR': '0',
    'SUBSYSTEM': 'block',
    'TAGS': ':systemd:',
    'USEC_INITIALIZED': '2026691'
}


class TestUdevInfo(CiTestCase):

    @mock.patch('curtin.util.subp')
    def test_udevadm_info(self, m_subp):
        """ udevadm_info returns dictionary for specified device """
        mypath = '/dev/nvme0n1'
        m_subp.return_value = (UDEVADM_INFO_QUERY, "")
        info = udev.udevadm_info(mypath)
        m_subp.assert_called_with(
            ['udevadm', 'info', '--query=property', '--export', mypath],
            capture=True)
        self.assertEqual(sorted(INFO_DICT), sorted(info))

    def test_udevadm_info_no_path(self):
        """ udevadm_info raises ValueError for invalid path value"""
        mypath = None
        with self.assertRaises(ValueError):
            udev.udevadm_info(mypath)

    @mock.patch('curtin.util.subp')
    def test_udevadm_info_path_not_exists(self, m_subp):
        """ udevadm_info raises ProcessExecutionError for invalid path value"""
        mypath = self.random_string()
        m_subp.side_effect = util.ProcessExecutionError()
        with self.assertRaises(util.ProcessExecutionError):
            udev.udevadm_info(mypath)
