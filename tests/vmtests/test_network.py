from . import VMBaseClass
from unittest import TestCase

import os
import textwrap


class TestNetworkAbs(VMBaseClass):
    __test__ = False
    interactive = False
    conf_file = "examples/tests/basic_network.yaml"
    install_timeout = 600
    boot_timeout = 600
    extra_disks = []
    extra_nics = []
    user_data = textwrap.dedent("""\
        #cloud-config
        password: passw0rd
        chpasswd: { expire: False }
        bootcmd:
          - mkdir -p /media/output
          - mount /dev/vdb /media/output
        runcmd:
          - ifconfig -a > /media/output/ifconfig_a
          - cp -av /etc/network/interfaces /media/output
          - cp -av /etc/udev/rules.d/70-persistent-net.rules /media/output
        power_state:
          mode: poweroff
        """)

    def test_output_files_exist(self):
        self.output_files_exist(["ifconfig_a",
                                 "interfaces",
                                 "70-persistent-net.rules"])

    def test_ifconfig_output(self):
        '''check ifconfig output with test input'''
        with open(os.path.join(self.td.mnt, "ifconfig_a")) as fp:
            ifconfig_a = fp.read()
            print(ifconfig_a)
        for iface in self.expected_interfaces():
            print(iface)
            self.assertTrue(iface in ifconfig_a)


class TrustyTestBasic(TestNetworkAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "trusty"
    arch = "amd64"


class WilyTestBasic(TestNetworkAbs, TestCase):
    __test__ = False
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestBasic(TestNetworkAbs, TestCase):
    __test__ = False
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"
