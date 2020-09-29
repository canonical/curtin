# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, check_install_log
from .releases import base_vm_classes as relbase


class TestInstallPanic(VMBaseClass):
    """ Test that a kernel panic exits the install mode immediately. """
    expected_failure = True
    collect_scripts = []
    conf_file = "examples/tests/panic.yaml"
    interactive = False

    def test_install_log_finds_kernel_panic_error(self):
        with open(self.install_log, 'rb') as lfh:
            install_log = lfh.read().decode('utf-8', errors='replace')
        errmsg, errors = check_install_log(install_log)
        found_panic = False
        print("errors: %s" % (len(errors)))
        for idx, err in enumerate(errors):
            print("%s:\n%s" % (idx, err))
            if 'Kernel panic -' in err:
                found_panic = True
                break
        self.assertTrue(found_panic)


class FocalTestInstallPanic(relbase.focal, TestInstallPanic):
    __test__ = True


class GroovyTestInstallPanic(relbase.groovy, TestInstallPanic):
    __test__ = True


# vi: ts=4 expandtab syntax=python
