import mock

from curtin import swap
from curtin import util
from .helpers import CiTestCase


class TestSwap(CiTestCase):
    def _valid_swap_contents(self):
        """Yields (pagesize, content) of things that should be considered
           valid swap."""
        # 4k and 64k page size
        for pagesize in [4096, 65536]:
            for magic in [b'SWAPSPACE2', b'SWAP-SPACE']:
                # yield content of 2 pages to trigger/avoid fence-post errors
                yield (pagesize,
                       ((pagesize - len(magic)) * b'\0' +
                        magic + pagesize * b'\0'))

    @mock.patch('curtin.swap.resource.getpagesize')
    def test_is_swap_device_read_offsets(self, mock_getpagesize):
        """swap.is_swap_device() correctly identifies swap content."""
        tmpd = self.tmp_dir()
        for num, (pagesize, content) in enumerate(self._valid_swap_contents()):
            path = self.tmp_path("swap-file-%02d" % num, tmpd)
            util.write_file(path, content, omode="wb")
            mock_getpagesize.return_value = pagesize
            self.assertTrue(swap.is_swap_device(path))

    @mock.patch('curtin.swap.resource.getpagesize', return_value=4096)
    def test_identify_swap_false_if_tiny(self, mock_getpagesize):
        """small files do not trip up is_swap_device()."""
        path = self.tmp_path("tiny")
        util.write_file(path, b'tinystuff', omode='wb')
        self.assertFalse(swap.is_swap_device(path))

    @mock.patch('curtin.swap.resource.getpagesize', return_value=4096)
    def test_identify_zeros_are_swap(self, mock_getpagesize):
        """swap.is_swap_device() returns false on all zeros"""
        pagesize = mock_getpagesize()
        path = self.tmp_path("notswap0")
        util.write_file(path, pagesize * 2 * b'\0', omode="wb")
        self.assertFalse(swap.is_swap_device(path))

    @mock.patch('curtin.swap.resource.getpagesize', return_value=65536)
    def test_identify_swap_false(self, mock_getpagesize):
        """swap.is_swap_device() returns false on non swap content"""
        pagesize = mock_getpagesize()
        path = self.tmp_path("notswap1")
        # this is just arbitrary content that is not swap content.
        blob = b'\x00\x00c\x05\x00\x00\x11\x19'
        util.write_file(path, int(pagesize * 2 / len(blob)) * blob, omode="wb")
        self.assertFalse(swap.is_swap_device(path))
