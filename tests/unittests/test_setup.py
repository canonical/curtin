# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path

import setup

from .helpers import CiTestCase


class TestCurtinSetup(CiTestCase):
    def test_packages_list(self):
        expected = set(["curtin"])

        for path in Path("curtin").rglob("*"):
            if not path.is_dir():
                continue
            if path.name == "__pycache__":
                continue

            expected.add(str(path).replace("/", "."))

        self.assertEqual(expected, set(setup.packages))
