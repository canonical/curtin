# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_apt_config_cmd
    Collection of tests for the apt configuration features when called via the
    apt-config standalone command.
"""
import textwrap

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase
from curtin.config import load_config


class TestAptConfigCMD(VMBaseClass):
    """TestAptConfigCMD - test standalone command"""
    test_type = 'config'
    conf_file = "examples/tests/apt_config_command.yaml"
    interactive = False
    extra_disks = []
    fstab_expected = {}
    disk_to_check = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp /etc/apt/sources.list.d/curtin-dev-ubuntu-test-archive-*.list .
        cp /etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg .
        apt-cache policy | grep proposed > proposed-enabled

        exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_cmd_proposed_enabled(self):
        """check if proposed was enabled"""
        self.output_files_exist(["proposed-enabled"])
        self.check_file_regex("proposed-enabled",
                              r"500.*%s-proposed" % self.release)

    @skip_if_flag('expected_failure')
    def test_cmd_ppa_enabled(self):
        """check if specified curtin-dev ppa was enabled"""
        self.output_files_exist(
            ["curtin-dev-ubuntu-test-archive-%s.list" % self.release])
        self.check_file_regex("curtin-dev-ubuntu-test-archive-%s.list" %
                              self.release,
                              (r"http://ppa.launchpad.net/"
                               r"curtin-dev/test-archive/ubuntu(/*)"
                               r" %s main" % self.release))

    @skip_if_flag('expected_failure')
    def test_cmd_preserve_source(self):
        """check if cloud-init was prevented from overwriting"""
        self.output_files_exist(["curtin-preserve-sources.cfg"])
        # For earlier than xenial 'apt_preserve_sources_list' is expected
        self.assertEqual(
            {'apt': {'preserve_sources_list': True}},
            load_config(self.collect_path("curtin-preserve-sources.cfg")))


class XenialTestAptConfigCMDCMD(relbase.xenial, TestAptConfigCMD):
    """ XenialTestAptSrcModifyCMD
        apt feature Test for Xenial using the standalone command
    """
    skip = True  # XXX Broken for now
    __test__ = True


class BionicTestAptConfigCMDCMD(relbase.bionic, TestAptConfigCMD):
    skip = True  # XXX Broken for now
    __test__ = True


class FocalTestAptConfigCMDCMD(relbase.focal, TestAptConfigCMD):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestAptConfigCMDCMD(relbase.jammy, TestAptConfigCMD):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
