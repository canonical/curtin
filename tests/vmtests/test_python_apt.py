# This file is part of curtin. See LICENSE file for copyright and license info.

from aptsources.sourceslist import SourceEntry

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase


class TestPythonApt(VMBaseClass):
    """TestPythonApt - apt sources manipulation with python{,3}-apt"""
    test_type = 'config'
    conf_file = "examples/tests/apt_source_custom.yaml"

    @skip_if_flag('expected_failure')
    def test_python_apt(self):
        """test_python_apt - Ensure the python-apt package is available"""

        line = 'deb http://us.archive.ubuntu.com/ubuntu/ hirsute main'

        self.assertEqual(line, str(SourceEntry(line)))


class XenialTestPythonApt(relbase.xenial, TestPythonApt):
    __test__ = True


class BionicTestPythonApt(relbase.bionic, TestPythonApt):
    __test__ = True


class FocalTestPythonApt(relbase.focal, TestPythonApt):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestPythonApt(relbase.jammy, TestPythonApt):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
