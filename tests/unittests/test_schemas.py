# This file is part of curtin. See LICENSE file for copyright and license info.

import glob
import unittest

from parameterized import parameterized

from curtin.commands.schema_validate import schema_validate_storage


class TestSchemaValidation(unittest.TestCase):
    @parameterized.expand(glob.glob("tests/unittests/schema/storage/good/*"))
    def test_storage_good(self, filename):
        self.assertEqual(0, schema_validate_storage(filename))

    @parameterized.expand(glob.glob("tests/unittests/schema/storage/bad/*"))
    def test_storage_bad(self, filename):
        self.assertEqual(1, schema_validate_storage(filename))
