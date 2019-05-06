# This file is part of curtin. See LICENSE file for copyright and license info.

"""
This just tests the vmtest harness.  Useful for quickly running
multiple tests that can pass or fail.

To see these tests fail, run:
  CURTIN_VMTEST_DEBUG_ALLOW_FAIL=1 nosetests3 tests/vmtests/test_vmtests.py
"""

from . import (PsuedoVMBaseClass)
from .releases import base_vm_classes as relbase


class PsuedoBase(PsuedoVMBaseClass):
    # Just present to show structure used in other tests
    pass


class PsuedoTestAllPass(relbase.bionic, PsuedoBase):
    __test__ = True
    # These boot_results would cause first_boot failure
    # boot_results = {
    #   'install': {'timeout': 0, 'exit': 0},
    #   'first_boot': {'timeout': 0, 'exit': 1},
    # }

    def test_pass(self):
        pass

    def test_pass2(self):
        pass


class PsuedoTestMixedPassAndFail(relbase.xenial, PsuedoBase):
    __test__ = True

    def test_pass(self):
        pass

    def test_fail(self):
        self._maybe_raise(Exception("This failed."))

    def test_fail2(self):
        self._maybe_raise(Exception("This second test failed."))

# vi: ts=4 expandtab syntax=python
