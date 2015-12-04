"""
This just tests the vmtest harness.  Useful for quickly running
multiple tests that can pass or fail.

To see these tests fail, run:
  CURTIN_VMTEST_DEBUG_ALLOW_FAIL=1 nosetest3 tests/vmtests/test_vmtests.py
"""

from . import (PsuedoVMBaseClass)

from unittest import TestCase


class PsuedoTestAllPass(PsuedoVMBaseClass, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "trusty"
    arch = "amd64"
    # These boot_results would cause first_boot failure
    # boot_results = {
    #   'install': {'timeout': 0, 'exit': 0},
    #   'first_boot': {'timeout': 0, 'exit': 1},
    # }

    def test_pass(self):
        pass

    def test_pass2(self):
        pass


class PsuedoTestMixedPassAndFail(PsuedoVMBaseClass, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"

    def test_pass(self):
        pass

    def test_fail(self):
        self._maybe_raise(Exception("This failed."))

    def test_fail2(self):
        self._maybe_raise(Exception("This second test failed."))
