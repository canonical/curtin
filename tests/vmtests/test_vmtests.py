"""
This just tests the vmtest harness.  Useful for quickly running
multiple tests that can pass or fail.
"""
from . import (PsuedoVMBaseClass)

from unittest import TestCase


class PsuedoTestAllPass(PsuedoVMBaseClass, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "trusty"
    arch = "amd64"

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
