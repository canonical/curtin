import mock

from curtin import swap
from .helpers import CiTestCase


class TestSwap(CiTestCase):
    @mock.patch('curtin.swap.resource')
    @mock.patch('curtin.swap.util')
    def test_is_swap_device_read_offsets(self, mock_util, mock_resource):
        """swap.is_swap_device() checks offsets based on system pagesize"""
        path = '/mydev/dummydisk'
        # 4k and 64k page size
        for pagesize in [4096, 65536]:
            magic_offset = pagesize - 10
            mock_resource.getpagesize.return_value = pagesize
            swap.is_swap_device(path)
            mock_util.load_file.assert_called_with(path, read_len=10,
                                                   offset=magic_offset,
                                                   decode=False)

    @mock.patch('curtin.swap.resource')
    @mock.patch('curtin.swap.util')
    def test_identify_swap_false(self, mock_util, mock_resource):
        """swap.is_swap_device() returns false on non swap magic"""
        mock_util.load_file.return_value = (
            b'\x00\x00c\x05\x00\x00\x11\x00\x19\x00')
        is_swap = swap.is_swap_device('ignored')
        self.assertFalse(is_swap)

    @mock.patch('curtin.swap.resource')
    @mock.patch('curtin.swap.util')
    def test_identify_swap_true(self, mock_util, mock_resource):
        """swap.is_swap_device() returns true on swap magic strings"""
        path = '/mydev/dummydisk'
        for magic in [b'SWAPSPACE2', b'SWAP-SPACE']:
            mock_util.load_file.return_value = magic
            is_swap = swap.is_swap_device(path)
            self.assertTrue(is_swap)
