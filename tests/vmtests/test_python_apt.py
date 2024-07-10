# This file is part of curtin. See LICENSE file for copyright and license info.

from aptsources.sourceslist import SourceEntry

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestPythonApt(VMBaseClass):
    """TestPythonApt - apt sources manipulation with python{,3}-apt"""
    test_type = 'config'
    conf_file = "examples/tests/apt_source_custom.yaml"

    def test_python_apt(self):
        """test_python_apt - Ensure the python-apt package is available"""

        line = 'deb http://us.archive.ubuntu.com/ubuntu/ hirsute main'

        self.assertEqual(line, str(SourceEntry(line)))


class XenialTestPythonApt(relbase.xenial, TestPythonApt):
    __test__ = True


class BionicTestPythonApt(relbase.bionic, TestPythonApt):
    __test__ = True


class FocalTestPythonApt(relbase.focal, TestPythonApt):
    __test__ = True


class HirsuteTestPythonApt(relbase.hirsute, TestPythonApt):
    __test__ = True


class ImpishTestPythonApt(relbase.impish, TestPythonApt):
    __test__ = True


class JammyTestPythonApt(relbase.jammy, TestPythonApt):
    __test__ = True


# vi: ts=4 expandtab syntax=python
