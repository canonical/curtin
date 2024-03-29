from unittest import mock

from curtin import swap
from curtin import util
from .helpers import CiTestCase

from parameterized import parameterized


def gigify(val):
    return int(val * (2 ** 30))


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

    def test_swapfile_nonefs(self):
        self.assertFalse(swap.can_use_swapfile(None, None))

    def test_swapfile_ext4(self):
        self.assertTrue(swap.can_use_swapfile(None, 'ext4'))

    def test_swapfile_zfs(self):
        self.assertFalse(swap.can_use_swapfile(None, 'zfs'))

    @mock.patch('curtin.swap.get_target_kernel_version')
    def test_swapfile_btrfs_oldkernel(self, mock_gtkv):
        mock_gtkv.return_value = dict(major=4)
        self.assertFalse(swap.can_use_swapfile(None, 'btrfs'))

    @mock.patch('curtin.swap.get_target_kernel_version')
    def test_swapfile_btrfs_ok(self, mock_gtkv):
        mock_gtkv.return_value = dict(major=5)
        self.assertTrue(swap.can_use_swapfile(None, 'btrfs'))

    @parameterized.expand([
        [2, 1],
        [2, 1.9],
        [2, 2],
        [2.1, 2.1],
        [3.9, 3.9],
        [4, 4],
        [4, 4.1],
        [4, 15.9],
        [4, 16],
        # above 16GB memsize hits suggested max
        [8, 16.1],
        [8, 64],
    ])
    def test_swapsize(self, expected, memsize):
        expected = gigify(expected)
        memsize = gigify(memsize)
        self.assertEqual(expected, swap.suggested_swapsize(memsize=memsize))

    @parameterized.expand([
        [4, 16, 16],
        [4, 16, 24],
        [4, 16, 32],
        [4, 16.1, 16],
        [6, 16.1, 24],
        [8, 16.1, 32],
        [8, 16.1, 64],
    ])
    def test_swapsize_with_avail(self, expected, memsize, avail):
        expected = gigify(expected)
        memsize = gigify(memsize)
        avail = gigify(avail)
        actual = swap.suggested_swapsize(memsize=memsize, avail=avail)
        self.assertEqual(expected, actual)

    @parameterized.expand([
        [16, 16],
        [24, 24],
        [32, 32],
        [32, 64],
    ])
    def test_swapsize_with_larger_max(self, expected, maxsize):
        expected = gigify(expected)
        memsize = gigify(64)
        maxsize = gigify(maxsize)
        actual = swap.suggested_swapsize(memsize=memsize, maxsize=maxsize)
        self.assertEqual(expected, actual)
