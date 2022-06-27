# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_tox_environ
verify that systems running tests contain the environmental packages expected
"""

from aptsources.sourceslist import SourceEntry
from .helpers import CiTestCase


class TestPythonPackages(CiTestCase):
    def test_python_apt(self):
        """test_python_apt - Ensure the python-apt package is available"""

        line = 'deb http://us.archive.ubuntu.com/ubuntu/ hirsute main'

        self.assertEqual(line, str(SourceEntry(line)))
