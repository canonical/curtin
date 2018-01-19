# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import centos_base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs

import textwrap


# FIXME: should eventually be integrated with the real TestBasic
class CentosTestBasicAbs(VMBaseClass):
    __test__ = False
    conf_file = "examples/tests/centos_basic.yaml"
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"
    # XXX: command | tee output is required for Centos under SELinux
    # http://danwalsh.livejournal.com/22860.html
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent(
        """
        cd OUTPUT_COLLECT_D
        cat /etc/fstab > fstab
        rpm -qa | cat >rpm_qa
        ifconfig -a | cat >ifconfig_a
        ip a | cat >ip_a
        cp -a /etc/sysconfig/network-scripts .
        cp -a /var/log/messages .
        cp -a /var/log/cloud-init* .
        cp -a /var/lib/cloud ./var_lib_cloud
        cp -a /run/cloud-init ./run_cloud-init
        rpm -E '%rhel' > rpm_dist_version_major
        cp -a /etc/centos-release .
        """)]
    fstab_expected = {
        'LABEL=cloudimg-rootfs': '/',
    }

    def test_dname(self):
        pass

    def test_interfacesd_eth0_removed(self):
        pass

    def test_output_files_exist(self):
        self.output_files_exist(["fstab"])

    def test_centos_release(self):
        """Test this image is the centos release expected"""
        self.output_files_exist(["rpm_dist_version_major", "centos-release"])

        centos_release = self.load_collect_file("centos-release").lower()
        rpm_major_version = (
            self.load_collect_file("rpm_dist_version_major").strip())
        _, os_id, os_version = self.target_release.partition("centos")

        self.assertTrue(os_version.startswith(rpm_major_version),
                        "%s doesn't start with %s" % (os_version,
                                                      rpm_major_version))
        self.assertTrue(centos_release.startswith(os_id),
                        "%s doesn't start with %s" % (centos_release, os_id))


# FIXME: this naming scheme needs to be replaced
class Centos70FromXenialTestBasic(relbase.centos70fromxenial,
                                  CentosTestBasicAbs):
    __test__ = True


class Centos66FromXenialTestBasic(relbase.centos66fromxenial,
                                  CentosTestBasicAbs):
    __test__ = False
    # FIXME: test is disabled because the grub config script in target
    #        specifies drive using hd(1,0) syntax, which breaks when the
    #        installation medium is removed. other than this, the install works


class CentosTestBasicNetworkAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/centos_basic.yaml"
    extra_kern_args = "BOOTIF=eth0-52:54:00:12:34:00"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            cp -a /etc/sysconfig/network-scripts .
            cp -a /var/log/cloud-init* .
            cp -a /var/lib/cloud ./var_lib_cloud
            cp -a /run/cloud-init ./run_cloud-init
        """)]

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


class Centos70BasicNetworkFromXenialTestBasic(relbase.centos70fromxenial,
                                              CentosTestBasicNetworkAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
