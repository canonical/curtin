# This file is part of curtin. See LICENSE file for copyright and license info.
import os

from .helpers import CiTestCase

from curtin import util
from curtin.commands.extract import (extract_root_fsimage_url,
                                     extract_root_layered_fsimage_url,
                                     _get_image_stack)
from curtin.url_helper import UrlError


class TestExtractRootFsImageUrl(CiTestCase):
    """Test extract_root_fsimage_url."""
    def _fake_download(self, url, path, retries=0):
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
        extract_root_fsimage_url("file:///" + fpath, target)
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


class TestExtractRootLayeredFsImageUrl(CiTestCase):
    """Test extract_root_layared_fsimage_url."""
    def _fake_download(self, url, path, retries=0):
        self.downloads.append(os.path.abspath(path))
        with open(path, "w") as fp:
            fp.write("fake content from " + url + "\n")

    def setUp(self):
        super(TestExtractRootLayeredFsImageUrl, self).setUp()
        self.downloads = []
        self.add_patch("curtin.commands.extract.url_helper.download",
                       "m_download", side_effect=self._fake_download)
        self.add_patch("curtin.commands.extract._extract_root_layered_fsimage",
                       "m__extract_root_layered_fsimage")

    def test_relative_local_file_single(self):
        """extract_root_layered_fsimage_url supports relative file:// uris."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        startdir = os.getcwd()
        fname = "my.img"
        try:
            os.chdir(tmpd)
            util.write_file(fname, fname + " data\n")
            extract_root_layered_fsimage_url("file://" + fname, target)
        finally:
            os.chdir(startdir)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_absolute_local_file_single(self):
        """extract_root_layered_fsimage_url supports absolute file:/// uris."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        fpath = self.tmp_path("my.img", tmpd)
        util.write_file(fpath, fpath + " data\n")
        extract_root_layered_fsimage_url("file:///" + fpath, target)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_local_file_path_single(self):
        """extract_root_layered_fsimage_url supports normal file path without
           file:"""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        fpath = self.tmp_path("my.img", tmpd)
        util.write_file(fpath, fpath + " data\n")
        extract_root_layered_fsimage_url(os.path.abspath(fpath), target)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_local_file_path_multiple(self):
        """extract_root_layered_fsimage_url supports normal hierarchy file
           path"""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        arg = os.path.abspath(self.tmp_path("minimal.standard.debug.squashfs",
                                            tmpd))
        for f in ["minimal.squashfs",
                  "minimal.standard.squashfs",
                  "minimal.standard.debug.squashfs"]:
            fpath = self.tmp_path(f, tmpd)
            util.write_file(fpath, fpath + " data\n")
        extract_root_layered_fsimage_url(arg, target)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_local_file_path_multiple_one_missing(self):
        """extract_root_layered_fsimage_url supports normal hierarchy file
           path but intermediate layer missing"""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        arg = os.path.abspath(self.tmp_path("minimal.standard.debug.squashfs",
                                            tmpd))
        for f in ["minimal.squashfs",
                  "minimal.standard.debug.squashfs"]:
            fpath = self.tmp_path(f, tmpd)
            util.write_file(fpath, fpath + " data\n")
        self.assertRaises(ValueError, extract_root_layered_fsimage_url, arg,
                          target)
        self.assertEqual(0, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_local_file_path_multiple_one_empty(self):
        """extract_root_layered_fsimage_url supports normal hierarchy file
           path but intermediate layer empty"""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        arg = os.path.abspath(self.tmp_path("minimal.standard.debug.squashfs",
                                            tmpd))
        for f in ["minimal.squashfs",
                  "minimal.standard.squashfs"
                  "minimal.standard.debug.squashfs"]:
            fpath = self.tmp_path(f, tmpd)
            if f == "minimal.standard.squashfs":
                util.write_file(fpath, "")
            else:
                util.write_file(fpath, fpath + " data\n")
        self.assertRaises(ValueError, extract_root_layered_fsimage_url, arg,
                          target)
        self.assertEqual(0, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(0, self.m_download.call_count)

    def test_remote_file_single(self):
        """extract_root_layered_fsimage_url supports http:// urls."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        myurl = "http://example.io/minimal.squashfs"
        extract_root_layered_fsimage_url(myurl, target)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(1, self.m_download.call_count)
        self.assertEqual("http://example.io/minimal.squashfs",
                         self.m_download.call_args_list[0][0][0])
        # ensure the file got cleaned up.
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])

    def test_remote_file_multiple(self):
        """extract_root_layered_fsimage_url supports normal hierarchy from
           http:// urls."""
        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        myurl = "http://example.io/minimal.standard.debug.squashfs"
        extract_root_layered_fsimage_url(myurl, target)
        self.assertEqual(1, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(3, self.m_download.call_count)
        for i, image_url in enumerate(["minimal.squashfs",
                                       "minimal.standard.squashfs",
                                       "minimal.standard.debug.squashfs"]):
            self.assertEqual("http://example.io/" + image_url,
                             self.m_download.call_args_list[i][0][0])
        # ensure the file got cleaned up.
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])

    def test_remote_file_multiple_one_missing(self):
        """extract_root_layered_fsimage_url supports normal hierarchy from
           http:// urls with one layer missing."""

        def fail_download_minimal_standard(url, path, retries=0):
            if url == "http://example.io/minimal.standard.squashfs":
                raise UrlError(url, 404, "Couldn't download",
                               None, None)
            return self._fake_download(url, path, retries)
        self.m_download.side_effect = fail_download_minimal_standard

        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        myurl = "http://example.io/minimal.standard.debug.squashfs"
        self.assertRaises(UrlError, extract_root_layered_fsimage_url,
                          myurl, target)
        self.assertEqual(0, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(2, self.m_download.call_count)
        for i, image_url in enumerate(["minimal.squashfs",
                                       "minimal.standard.squashfs"]):
            self.assertEqual("http://example.io/" + image_url,
                             self.m_download.call_args_list[i][0][0])
        # ensure the file got cleaned up.
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])

    def test_remote_file_multiple_one_empty(self):
        """extract_root_layered_fsimage_url supports normal hierarchy from
           http:// urls with one layer empty."""

        def empty_download_minimal_standard(url, path, retries=0):
            if url == "http://example.io/minimal.standard.squashfs":
                self.downloads.append(os.path.abspath(path))
                with open(path, "w") as fp:
                    fp.write("")
                return
            return self._fake_download(url, path, retries)
        self.m_download.side_effect = empty_download_minimal_standard

        tmpd = self.tmp_dir()
        target = self.tmp_path("target_d", tmpd)
        myurl = "http://example.io/minimal.standard.debug.squashfs"
        self.assertRaises(ValueError, extract_root_layered_fsimage_url,
                          myurl, target)
        self.assertEqual(0, self.m__extract_root_layered_fsimage.call_count)
        self.assertEqual(3, self.m_download.call_count)
        for i, image_url in enumerate(["minimal.squashfs",
                                       "minimal.standard.squashfs",
                                       "minimal.standard.debug.squashfs"]):
            self.assertEqual("http://example.io/" + image_url,
                             self.m_download.call_args_list[i][0][0])
        # ensure the file got cleaned up.
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])


class TestGetImageStack(CiTestCase):
    """Test _get_image_stack."""

    def test_get_image_stack(self):
        """_get_image_paths returns a tuple of depending fsimages
           with same extension"""
        self.assertEqual(
            ['/path/to/aa.fs',
             '/path/to/aa.bbb.fs',
             '/path/to/aa.bbb.cccc.fs'],
            _get_image_stack("/path/to/aa.bbb.cccc.fs"))

    def test_get_image_stack_none(self):
        """_get_image_paths returns an empty tuple with no entry"""
        self.assertEqual(
            [],
            _get_image_stack(""))

    def test_get_image_stack_no_dependency(self):
        """_get_image_paths returns a tuple a single element when fsimage
           has no dependency"""
        self.assertEqual(
            ['/path/to/aa.fs'],
            _get_image_stack("/path/to/aa.fs"))

    def test_get_image_stack_with_urls(self):
        """_get_image_paths returns a tuple of depending fsimages
           with same extension and same urls"""
        self.assertEqual(
            ['https://path.com/to/aa.fs',
             'https://path.com/to/aa.bbb.fs',
             'https://path.com/to/aa.bbb.cccc.fs'],
            _get_image_stack("https://path.com/to/aa.bbb.cccc.fs"))

# vi: ts=4 expandtab syntax=python
