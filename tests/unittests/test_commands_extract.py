# This file is part of curtin. See LICENSE file for copyright and license info.
import os

from .helpers import CiTestCase

from curtin import util
from curtin.commands.extract import extract_root_fsimage_url


class TestExtractRootFsImageUrl(CiTestCase):
    """Test extract_root_fsimage_url."""
    def _fake_download(self, url, path):
        self.downloads.append(os.path.abspath(path))
        with open(path, "w") as fp:
            fp.write("fake content from " + url + "\n")

    def setUp(self):
        super(TestExtractRootFsImageUrl, self).setUp()
        self.downloads = []
        self.add_patch("curtin.commands.extract.url_helper.download",
                       "m_download", side_effect=self._fake_download)
        self.add_patch("curtin.commands.extract._extract_root_fsimage",
                       "m__extract_root_fsimage")

    def test_relative_file_url(self):
        """extract_root_fsimage_url supports relative file:// urls."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        startdir = os.getcwd()
        fname = "my.img"
        try:
            os.chdir(tmpd)
            util.write_file(fname, fname + " data\n")
            extract_root_fsimage_url("file://" + fname, target)
        finally:
            os.chdir(startdir)
        self.assertEqual(1, self.m__extract_root_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_absolute_file_url(self):
        """extract_root_fsimage_url supports absolute file:/// urls."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        fpath = self.tmp_path("my.img", tmpd)
        util.write_file(fpath, fpath + " data\n")
        extract_root_fsimage_url("file://" + fpath, target)
        self.assertEqual(1, self.m__extract_root_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_http_url(self):
        """extract_root_fsimage_url supports http:// urls."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        myurl = "http://bogus.example.com/my.img"
        extract_root_fsimage_url(myurl, target)
        self.assertEqual(1, self.m__extract_root_fsimage.call_count)
        self.assertEqual(1, self.m_download.call_count)
        # ensure the file got cleaned up.
        self.assertEqual(1, len(self.downloads))
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])

    def test_file_path_not_url(self):
        """extract_root_fsimage_url supports normal file path without file:."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        fpath = self.tmp_path("my.img", tmpd)
        util.write_file(fpath, fpath + " data\n")
        extract_root_fsimage_url(os.path.abspath(fpath), target)
        self.assertEqual(1, self.m__extract_root_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)


# vi: ts=4 expandtab syntax=python
