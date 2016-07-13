""" testold_apt_features
    Testing the former minimal apt features of curtin
"""
import re
import textwrap

from . import VMBaseClass
from .releases import base_vm_classes as relbase


class TestOldAptAbs(VMBaseClass):
    """TestOldAptAbs - Basic tests for old apt features of curtin"""
    interactive = False
    extra_disks = []
    fstab_expected = {}
    disk_to_check = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        ls /dev/disk/by-dname > ls_dname
        find /etc/network/interfaces.d > find_interfacesd
        grep -A 3 "Name: debconf/priority" /var/cache/debconf/config.dat > debc
        apt-config dump > aptconf
        cp /etc/apt/apt.conf.d/90curtin-aptproxy .
        cp /etc/apt/sources.list .
        """)]
    boot_cloudconf = {'apt_preserve_sources_list': True}
    conf_file = "examples/tests/test_old_apt_features.yaml"

    def test_output_files_exist(self):
        """test_output_files_exist - Check if all output files exist"""
        self.output_files_exist(
            ["debc", "aptconf", "sources.list", "90curtin-aptproxy"])

    def test_debconf(self):
        """test_debconf - Check if debconf is in place"""
        self.check_file_strippedline("debc", "Value: low")

    def test_aptconf(self):
        """test_aptconf - Check if apt conf for proxy is in place"""
        # this gets configured by tools/launch and get_apt_proxy in
        # tests/vmtests/__init__.py, so compare with those
        rproxy = r"Acquire::http::Proxy \"" + re.escape(self.proxy) + r"\";"
        self.check_file_regex("aptconf", rproxy)
        self.check_file_regex("90curtin-aptproxy", rproxy)

    def test_mirrors(self):
        """test_mirrors - Check for mirrors placed in source.list"""
        exp_mirror = "http://us.archive.ubuntu.com/ubuntu"
        exp_secmirror = "http://archive.ubuntu.com/ubuntu"

        self.check_file_strippedline("sources.list",
                                     "deb %s  %s" %
                                     (exp_mirror, self.release) +
                                     " main restricted universe multiverse")
        self.check_file_strippedline("sources.list",
                                     "deb %s  %s-security" %
                                     (exp_secmirror, self.release) +
                                     " main restricted universe multiverse")


class XenialTestOldApt(relbase.xenial, TestOldAptAbs):
    """ XenialTestOldApt
       Old apt features for Xenial
    """
    __test__ = True
