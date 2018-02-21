# This file is part of curtin. See LICENSE file for copyright and license info.

import filecmp

from curtin import url_helper

from .helpers import CiTestCase


class TestDownload(CiTestCase):
    def test_download_file_url(self):
        """Download a file to another file."""
        tmpd = self.tmp_dir()
        src_file = self.tmp_path("my-source", tmpd)
        target_file = self.tmp_path("my-target", tmpd)

        # Make sure we have > 8192 bytes in the file (buflen of UrlReader)
        with open(src_file, "wb") as fp:
            for line in range(0, 1024):
                fp.write(b'Who are the people in your neighborhood.\n')

        url_helper.download("file://" + src_file, target_file)
        self.assertTrue(filecmp.cmp(src_file, target_file),
                        "Downloaded file differed from source file.")
