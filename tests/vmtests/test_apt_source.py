""" test_apt_source
    Collection of tests for the apt_source configuration features
"""
import textwrap

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestAptSrcAbs(VMBaseClass):
    """TestAptSrcAbs - Basic tests for apt_sources features of curtin"""
    interactive = False
    extra_disks = []
    fstab_expected = {}
    disk_to_check = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        apt-key list "F430BBA5" > keyid-F430BBA5
        apt-key list "03683F77" > keyppa-03683F77
        apt-key list "F470A0AC" > keylongid-F470A0AC
        apt-key list "8280B242" > keyraw-8280B242
        cp /etc/apt/sources.list.d/byobu-ppa.list .
        cp /etc/apt/sources.list.d/my-repo2.list .
        cp /etc/apt/sources.list.d/my-repo4.list .
        cp /etc/apt/sources.list.d/smoser-ubuntu-ppa-xenial.list .
        find /etc/apt/sources.list.d/ -maxdepth 1 -name "*ignore*" | wc -l > ic
        apt-config dump | grep Retries > aptconf
        cp /etc/apt/sources.list sources.list

        """)]
    boot_cloudconf = {'apt_preserve_sources_list': True}
    mirror = "http://us.archive.ubuntu.com/ubuntu/"
    secmirror = "http://security.ubuntu.com/ubuntu/"

    def test_output_files_exist(self):
        """test_output_files_exist - Check if all output files exist"""
        self.output_files_exist(
            ["fstab", "ic", "keyid-F430BBA5", "keylongid-F470A0AC",
             "keyraw-8280B242", "keyppa-03683F77", "aptconf", "sources.list",
             "byobu-ppa.list", "my-repo2.list", "my-repo4.list"])
        self.output_files_exist(
            ["smoser-ubuntu-ppa-%s.list" % self.release])

    def test_keys_imported(self):
        """test_keys_imported - Check if all keys are imported correctly"""
        self.check_file_regex("keyid-F430BBA5",
                              r"Launchpad PPA for Ubuntu Screen Profile")
        self.check_file_regex("keylongid-F470A0AC",
                              r"Ryan Harper")
        self.check_file_regex("keyppa-03683F77",
                              r"Launchpad PPA for Scott Moser")
        self.check_file_regex("keyraw-8280B242",
                              r"Christian Ehrhardt")

    def test_source_files(self):
        """test_source_files - Check generated .lists for correct content"""
        # hard coded deb lines
        self.check_file_strippedline("byobu-ppa.list",
                                     ("deb http://ppa.launchpad.net/byobu/"
                                      "ppa/ubuntu xenial main"))
        self.check_file_strippedline("my-repo4.list",
                                     ("deb http://ppa.launchpad.net/alestic/"
                                      "ppa/ubuntu xenial main"))
        # mirror and release replacement in deb line
        self.check_file_strippedline("my-repo2.list", "deb %s %s multiverse" %
                                     (self.mirror, self.release))
        # auto creation by apt-add-repository
        self.check_file_strippedline("smoser-ubuntu-ppa-%s.list" %
                                     self.release,
                                     ("deb http://ppa.launchpad.net/smoser/"
                                      "ppa/ubuntu %s main" % self.release))

    def test_ignore_count(self):
        """test_ignore_count - Check for files that should not be created"""
        self.check_file_strippedline("ic", "0")

    def test_apt_conf(self):
        """test_apt_conf - Check if the selected apt conf was set"""
        self.check_file_strippedline("aptconf", 'Acquire::Retries "3";')


class TestAptSrcCustom(TestAptSrcAbs):
    """TestAptSrcNormal - tests valid in the custom sources.list case"""
    conf_file = "examples/tests/apt_source_custom.yaml"

    def test_custom_source_list(self):
        """test_custom_source_list - Check custom sources with replacement"""
        self.check_file_strippedline("sources.list",
                                     "deb %s %s main restricted" %
                                     (self.mirror, self.release))
        self.check_file_strippedline("sources.list",
                                     "deb-src %s %s main restricted" %
                                     (self.mirror, self.release))
        self.check_file_strippedline("sources.list",
                                     "deb %s %s universe restricted" %
                                     (self.mirror, self.release))
        self.check_file_strippedline("sources.list",
                                     "deb %s %s-security multiverse" %
                                     (self.secmirror, self.release))
        self.check_file_strippedline("sources.list",
                                     "# nice line to check in test")


class TestAptSrcPreserve(TestAptSrcAbs):
    """TestAptSrcPreserve - tests valid in the preserved sources.list case"""
    conf_file = "examples/tests/apt_source_preserve.yaml"

    def test_preserved_source_list(self):
        """test_preserved_source_list - Check sources to be preserved as-is"""
        self.check_file_regex("sources.list",
                              r"this file is written by cloud-init")


class TestAptSrcBuiltin(TestAptSrcAbs):
    """TestAptSrcPreserve - tests for the builtin sources.list template"""
    conf_file = "examples/tests/apt_source_builtin.yaml"

    def test_builtin_source_list(self):
        """test_builtin_source_list - Check builtin sources with replacement"""
        self.check_file_regex("sources.list",
                              r"this file is written by curtin")


class XenialTestAptSrcCustom(relbase.xenial, TestAptSrcCustom):
    """ XenialTestAptSrcCustom
       Apt_source Test for Xenial with a custom template
    """
    __test__ = True


class XenialTestAptSrcPreserve(relbase.xenial, TestAptSrcPreserve):
    """ XenialTestAptSrcPreserve
       Apt_source Test for Xenial with apt_preserve_sources_list enabled
    """
    __test__ = True


class XenialTestAptSrcBuiltin(relbase.xenial, TestAptSrcBuiltin):
    """ XenialTestAptSrcBuiltin
        Apt_source Test for Xenial using the builtin template
    """
    __test__ = True
