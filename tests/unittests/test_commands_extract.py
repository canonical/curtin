# This file is part of curtin. See LICENSE file for copyright and license info.
import os

from .helpers import CiTestCase

from curtin import util
from curtin.commands.extract import (
    extract_source,
    _get_image_stack,
    )
from curtin.url_helper import UrlError


class Mount:
    def __init__(self, device, mountpoint, options, type):
        self.device = device
        self.mountpoint = mountpoint
        self.options = options
        self.type = type
        self.unmounted = False

    def __repr__(self):
        return "Mount({!r}, {!r}, {!r}, {!r})".format(
            self.device, self.mountpoint, self.options, self.type)


class MountTracker:

    def __init__(self):
        self.mounts = []

    def mount(self, device, mountpoint, options=None, type=None):
        if not os.path.isdir(mountpoint):
            raise AssertionError("%s is not a directory" % (mountpoint,))
        self.mounts.append(Mount(device, mountpoint, options, type))

    def unmount(self, mountpoint):
        for m in reversed(self.mounts):
            if m.mountpoint == mountpoint and not m.unmounted:
                m.unmounted = True
                return
        else:
            raise Exception("%s not mounted" % (mountpoint,))

    def check_unmounted(self):
        for mount in self.mounts:
            if not mount.unmounted:
                raise AssertionError("Mount %s was not unmounted" % (mount,))


class ExtractTestCase(CiTestCase):

    def _fake_download(self, url, path, retries=0):
        self.downloads.append(os.path.abspath(path))
        with open(path, "w") as fp:
            fp.write("fake content from " + url + "\n")

    def setUp(self):
        super(ExtractTestCase, self).setUp()
        self.downloads = []
        self.add_patch("curtin.commands.extract.url_helper.download",
                       "m_download", side_effect=self._fake_download)
        self.add_patch("curtin.commands.extract.copy_to_target",
                       "m_copy_to_target")

    def tearDown(self):
        super(ExtractTestCase, self).tearDown()
        # ensure the files got cleaned up.
        self.assertEqual([], [f for f in self.downloads if os.path.exists(f)])

    def track_mounts(self):
        tracker = MountTracker()
        self.add_patch('curtin.commands.extract.mount', new=tracker.mount)
        self.add_patch('curtin.commands.extract.unmount', new=tracker.unmount)

        self.addCleanup(tracker.check_unmounted)

        return tracker

    def assert_mounted_and_extracted(self, mount_tracker, fnames, target):
        # Assert that `fnames` (which should be ordered base to top
        # layer) were mounted in the correct order and extracted to
        # `target`.
        fname_to_mountpoint = {}
        other_mounts = []
        for mount in mount_tracker.mounts:
            if mount.device in fnames:
                fname_to_mountpoint[mount.device] = mount.mountpoint
            else:
                other_mounts.append(mount)

        if len(fnames) == 1:
            self.assertEqual(len(other_mounts), 0)
            self.m_copy_to_target.assert_called_once_with(
                mount_tracker.mounts[0].mountpoint, target)
            return

        expected_lowers = []
        for fname in fnames:
            if fname not in fname_to_mountpoint:
                self.fail("%s was not mounted" % (fname,))
            else:
                expected_lowers.append(fname_to_mountpoint[fname])
        expected_lowers.reverse()

        self.assertEqual(len(other_mounts), 1)
        final_mount = other_mounts[0]
        opts = final_mount.options.split(',')
        for opt in opts:
            if opt.startswith('lowerdir='):
                seen_lowers = opt[len('lowerdir='):].split(":")
                break
            else:
                self.fail("did not find expected lowerdir option")
                self.assertEqual(expected_lowers, seen_lowers)
        self.m_copy_to_target.assert_called_once_with(
            final_mount.mountpoint, target)

    def assert_downloaded_and_mounted_and_extracted(self, mount_tracker, urls,
                                                    target):
        # Assert that `urls` (which should be ordered base to top
        # layer) were downloaed and mounted in the correct order and
        # extracted to `target`.
        self.assertEqual(len(self.m_download.call_args_list), len(urls))
        url_to_fname = {}
        for call in self.m_download.call_args_list:
            url, path = call[0][:2]
            self.assertIn(url, urls)
            url_to_fname[url] = path
        fnames = []
        for url in urls:
            fnames.append(url_to_fname[url])
        self.assert_mounted_and_extracted(mount_tracker, fnames, target)


class TestExtractSourceCp(ExtractTestCase):
    """Test extract_source with cp sources."""

    def test_cp_uri(self):
        mount_tracker = self.track_mounts()
        path = self.random_string()
        target = self.random_string()

        extract_source({'uri': 'cp://' + path}, target)

        self.assertEqual(0, self.m_download.call_count)
        self.assertEqual(0, len(mount_tracker.mounts))
        self.m_copy_to_target.assert_called_once_with(path, target)


class TestExtractSourceFsImageUrl(ExtractTestCase):
    """Test extract_source with fsimage sources."""

    def tmp_path_with_random_content(self, name=None):
        if name is None:
            name = self.random_string()
        tdir = self.tmp_dir()
        path = os.path.join(tdir, self.random_string())
        util.write_file(path, self.random_string())
        return path

    def test_abspath(self):
        mount_tracker = self.track_mounts()
        path = self.tmp_path_with_random_content()
        target = self.random_string()

        extract_source({'type': 'fsimage', 'uri': path}, target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, [path], target)

    def test_abspath_dots(self):
        mount_tracker = self.track_mounts()
        path = self.tmp_path_with_random_content(name='a.b.c')
        target = self.random_string()

        extract_source({'type': 'fsimage', 'uri': path}, target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, [path], target)

    def test_relpath(self):
        mount_tracker = self.track_mounts()
        path = self.tmp_path_with_random_content()
        target = self.random_string()

        startdir = os.getcwd()
        try:
            os.chdir(os.path.dirname(path))
            extract_source(
                {'type': 'fsimage', 'uri': os.path.basename(path)},
                target)
        finally:
            os.chdir(startdir)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(
            mount_tracker, [os.path.basename(path)], target)

    def test_abs_fileurl(self):
        mount_tracker = self.track_mounts()
        path = self.tmp_path_with_random_content()
        target = self.random_string()

        extract_source(
            {'type': 'fsimage', 'uri': 'file://' + path},
            target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, [path], target)

    def test_rel_fileurl(self):
        mount_tracker = self.track_mounts()
        path = self.tmp_path_with_random_content()
        target = self.random_string()

        startdir = os.getcwd()
        try:
            os.chdir(os.path.dirname(path))
            extract_source(
                {'type': 'fsimage', 'uri': 'file://' + os.path.basename(path)},
                target)
        finally:
            os.chdir(startdir)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(
            mount_tracker, [os.path.basename(path)], target)

    def test_http_url(self):
        """extract_root_fsimage_url supports http:// urls."""
        mount_tracker = self.track_mounts()
        uri = 'http://' + self.random_string()
        target = self.random_string()

        extract_source({'type': 'fsimage', 'uri': uri}, target)

        self.assert_downloaded_and_mounted_and_extracted(
            mount_tracker, [uri], target)


class TestExtractSourceLayeredFsImageUrl(ExtractTestCase):
    """Test extract_source with fsimage-layered sources."""

    def tmp_paths_with_random_content(self, names):
        tdir = self.tmp_dir()
        paths = []
        longest = ''
        for name in names:
            path = os.path.join(tdir, name)
            util.write_file(path, self.random_string())
            if len(path) > len(longest):
                longest = path
            paths.append(path)
        return paths, longest

    def test_absolute_file_path_single(self):
        mount_tracker = self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(['base.ext'])
        target = self.random_string()

        extract_source(
            {'type': 'fsimage-layered', 'uri': longest},
            target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, paths, target)

    def test_relative_file_path_single(self):
        mount_tracker = self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(['base.ext'])
        target = self.random_string()

        startdir = os.getcwd()
        try:
            os.chdir(os.path.dirname(longest))
            extract_source(
                {'type': 'fsimage-layered', 'uri': os.path.basename(longest)},
                target)
        finally:
            os.chdir(startdir)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(
            mount_tracker, [os.path.basename(path) for path in paths], target)

    def test_absolute_file_url_single(self):
        mount_tracker = self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(['base.ext'])
        target = self.random_string()

        extract_source(
            {'type': 'fsimage-layered', 'uri': 'file://' + longest},
            target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, paths, target)

    def test_relative_file_url_single(self):
        mount_tracker = self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(['base.ext'])
        target = self.random_string()

        startdir = os.getcwd()
        try:
            os.chdir(os.path.dirname(longest))
            extract_source(
                {
                    'type': 'fsimage-layered',
                    'uri': 'file://' + os.path.basename(longest),
                },
                target)
        finally:
            os.chdir(startdir)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(
            mount_tracker, [os.path.basename(path) for path in paths], target)

    def test_local_file_path_multiple(self):
        mount_tracker = self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(
            ['base.ext', 'base.overlay.ext', 'base.overlay.other.ext'])
        target = self.random_string()

        extract_source(
            {'type': 'fsimage-layered', 'uri': longest},
            target)

        self.assertEqual(0, self.m_download.call_count)
        self.assert_mounted_and_extracted(mount_tracker, paths, target)

    def test_local_file_path_multiple_one_missing(self):
        self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(
            ['base.ext', 'base.overlay.other.ext'])
        target = self.random_string()

        self.assertRaises(
            ValueError, extract_source,
            {'type': 'fsimage-layered', 'uri': longest},
            target)

    def test_local_file_path_multiple_one_empty(self):
        self.track_mounts()
        paths, longest = self.tmp_paths_with_random_content(
            ['base.ext', 'base.overlay.ext', 'base.overlay.other.ext'])
        target = self.random_string()
        util.write_file(paths[1], '')

        self.assertRaises(
            ValueError, extract_source,
            {'type': 'fsimage-layered', 'uri': longest},
            target)

    def test_remote_file_single(self):
        mount_tracker = self.track_mounts()
        target = self.random_string()
        myurl = "http://example.io/minimal.squashfs"

        extract_source(
            {'type': 'fsimage-layered', 'uri': myurl},
            target)

        self.assert_downloaded_and_mounted_and_extracted(
            mount_tracker, ["http://example.io/minimal.squashfs"], target)

    def test_remote_file_multiple(self):
        mount_tracker = self.track_mounts()
        target = self.random_string()
        myurl = "http://example.io/minimal.standard.debug.squashfs"

        extract_source(
            {'type': 'fsimage-layered', 'uri': myurl},
            target)

        urls = [
            "http://example.io/minimal.squashfs",
            "http://example.io/minimal.standard.squashfs",
            "http://example.io/minimal.standard.debug.squashfs",
            ]
        self.assert_downloaded_and_mounted_and_extracted(
            mount_tracker, urls, target)

    def test_remote_file_multiple_one_missing(self):
        self.track_mounts()
        target = self.random_string()
        myurl = "http://example.io/minimal.standard.debug.squashfs"

        def fail_download_minimal_standard(url, path, retries=0):
            if url == "http://example.io/minimal.standard.squashfs":
                raise UrlError(url, 404, "Couldn't download",
                               None, None)
            return self._fake_download(url, path, retries)
        self.m_download.side_effect = fail_download_minimal_standard

        self.assertRaises(
            UrlError, extract_source,
            {'type': 'fsimage-layered', 'uri': myurl},
            target)
        self.assertEqual(0, self.m_copy_to_target.call_count)

    def test_remote_file_multiple_one_empty(self):
        self.track_mounts()
        target = self.random_string()
        myurl = "http://example.io/minimal.standard.debug.squashfs"

        def empty_download_minimal_standard(url, path, retries=0):
            if url == "http://example.io/minimal.standard.squashfs":
                self.downloads.append(os.path.abspath(path))
                with open(path, "w") as fp:
                    fp.write("")
                return
            return self._fake_download(url, path, retries)
        self.m_download.side_effect = empty_download_minimal_standard

        self.assertRaises(
            ValueError, extract_source,
            {'type': 'fsimage-layered', 'uri': myurl},
            target)
        self.assertEqual(0, self.m_copy_to_target.call_count)
        self.assertEqual(3, self.m_download.call_count)
        for i, image_url in enumerate(["minimal.squashfs",
                                       "minimal.standard.squashfs",
                                       "minimal.standard.debug.squashfs"]):
            self.assertEqual("http://example.io/" + image_url,
                             self.m_download.call_args_list[i][0][0])


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

    def test_get_image_stack_relative_file_urls(self):
        self.assertEqual(
            ['file://aa.fs',
             'file://aa.bbb.fs',
             'file://aa.bbb.cccc.fs'],
            _get_image_stack("file://aa.bbb.cccc.fs"))

# vi: ts=4 expandtab syntax=python
