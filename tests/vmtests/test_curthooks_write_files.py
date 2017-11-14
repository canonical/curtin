from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestCurthooksWriteFiles(VMBaseClass):
    """ Test curthooks.write_files() legacy call works """
    conf_file = "examples/tests/curthooks_writefiles.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp /etc/network/interfaces interfaces
        if [ -f /var/log/cloud-init-output.log ]; then
           cp /var/log/cloud-init-output.log .
        fi
        cp /var/log/cloud-init.log .
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["interfaces", "cloud-init.log"])

    def test_curthooks_write_files(self):
        self.output_files_exist(["root/testfile1"])
        content = self.load_collect_file("root/testfile1")
        self.assertEqual("This is testfile1", content.strip())


class XenialTestCurthooksWriteFiles(relbase.xenial, TestCurthooksWriteFiles):
    __test__ = True


class ArtfulTestCurthooksWriteFiles(relbase.artful, TestCurthooksWriteFiles):
    __test__ = True
