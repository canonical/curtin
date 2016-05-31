""" test_apt_source
    Collection of tests for the apt_source configuration features
"""
import textwrap

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestAptSrcAbs(VMBaseClass):
    """ TestAptSrcAbs
        Basic test class to test apt_sources features of curtin
    """
    conf_file = "examples/tests/apt_source.yaml"
    interactive = False
    # disk for early data collection at install stage
    extra_disks = ['1G']
    fstab_expected = {}
    disk_to_check = []
    # copy over the early collected data to the "normal" place of output data
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        mkdir -p /mnt/earlyoutput
        mount LABEL=earlyoutput /mnt/earlyoutput
        cp /mnt/earlyoutput/* .
        """)]

    def test_output_files_exist(self):
        "Check if all output files exist"
        self.output_files_exist(
            ["fstab", "ignorecount", "keyid-F430BBA5", "keylongid-F470A0AC",
             "keyraw-8280B242", "keyppa-03683F77", "aptconf",
             "byobu-ppa.list", "my-repo2.list", "my-repo4.list"])

    def test_keys_imported(self):
        "Check if all keys that should be imported are there"
        self.check_file_regex("keyid-F430BBA5",
                              r"Launchpad PPA for Ubuntu Screen Profile")
        self.check_file_regex("keylongid-F470A0AC",
                              r"Ryan Harper")
        self.check_file_regex("keyppa-03683F77",
                              r"Launchpad PPA for Scott Moser")
        self.check_file_regex("keyraw-8280B242",
                              r"Christian Ehrhardt")

    def test_source_files(self):
        "Check if the generated source.list files have the right content"
        # hard coded deb lines
        self.check_file_strippedline("byobu-ppa.list",
                                     ("deb http://ppa.launchpad.net/byobu/"
                                      "ppa/ubuntu xenial main"))
        self.check_file_strippedline("my-repo4.list",
                                     ("deb http://ppa.launchpad.net/alestic/"
                                      "ppa/ubuntu xenial main"))
        # mirror and release replacement in deb line
        self.check_file_strippedline("my-repo2.list", "deb %s %s multiverse" %
                                     ("http://us.archive.ubuntu.com/ubuntu/",
                                      self.release))
        # auto creation by apt-add-repository
        self.check_file_strippedline("smoser-ubuntu-ppa-%s.list" %
                                     self.release,
                                     ("deb http://ppa.launchpad.net/smoser/"
                                      "ppa/ubuntu %s main" % self.release))

    def test_ignore_count(self):
        "Check if the files that should not be generated are missing"
        self.check_file_strippedline("ignorecount", "0")

    def test_apt_conf(self):
        "Check if the selected apt conf arrived"
        self.check_file_strippedline("aptconf", 'Acquire::Retries "3";')


class XenialTestAptSrc(relbase.xenial, TestAptSrcAbs):
    """ XenialTestAptSrc
       Basic Test for Xenial without HWE
       Not that for this feature we don't support/care pre-Xenial
    """
    __test__ = True

    def test_release_output_files(self):
        "Check if all release specific output files exist"
        self.output_files_exist(
            ["smoser-ubuntu-ppa-xenial.list"])
