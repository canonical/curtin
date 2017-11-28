from . import VMBaseClass
from .releases import base_vm_classes as relbase

import textwrap


class TestBasicIscsiAbs(VMBaseClass):
    interactive = False
    iscsi_disks = [
        {'size': '3G'},
        {'size': '4G', 'auth': 'user:passw0rd'},
        {'size': '5G', 'auth': 'user:passw0rd', 'iauth': 'iuser:ipassw0rd'},
        {'size': '6G', 'iauth': 'iuser:ipassw0rd'}]
    conf_file = "examples/tests/basic_iscsi.yaml"
    nr_testfiles = 4

    collect_scripts = [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname/ > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        bash -c \
        'for f in /mnt/iscsi*; do cat $f/testfile > testfile${f: -1}; done'
        """)]

    def test_fstab_has_netdev_option(self):
        self.output_files_exist(["fstab"])
        fstab = self.load_collect_file("fstab").strip()
        self.assertTrue(any(["_netdev" in line
                             for line in fstab.splitlines()]))

    def test_iscsi_testfiles(self):
        # add check by SN or UUID that the iSCSI disks are attached?
        testfiles = ["testfile%s" % t for t in range(1, self.nr_testfiles + 1)]

        # make sure all required files are present:
        print('Expecting testfiles: %s' % testfiles)
        self.output_files_exist(testfiles)

        for testfile in testfiles:
            print('checking file content: %s' % testfile)
            expected_content = "test%s" % testfile[-1]
            content = self.load_collect_file(testfile).strip()
            self.assertEqual(expected_content, content,
                             "Checking %s, expected:\n%s\nfound:\n%s" %
                             (testfile, expected_content, content))


class TrustyTestIscsiBasic(relbase.trusty, TestBasicIscsiAbs):
    __test__ = True


class XenialTestIscsiBasic(relbase.xenial, TestBasicIscsiAbs):
    __test__ = True


class ZestyTestIscsiBasic(relbase.zesty, TestBasicIscsiAbs):
    __test__ = True


class ArtfulTestIscsiBasic(relbase.artful, TestBasicIscsiAbs):
    __test__ = True


class BionicTestIscsiBasic(relbase.bionic, TestBasicIscsiAbs):
    __test__ = True
