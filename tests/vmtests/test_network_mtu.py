# This file is part of curtin. See LICENSE file for copyright and license info.

from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from .test_network_ipv6 import TestNetworkIPV6Abs

import textwrap
import unittest


class TestNetworkMtuAbs(TestNetworkIPV6Abs):
    """ Test that the mtu of the ipv6 address is properly

    1.  devices default MTU to 1500, test if mtu under
        inet6 stanza can be set separately from device
        mtu (works on  and newer ifupdown), check
        via sysctl.

    2.  if ipv6 mtu is > than underlying device, this fails
        and is unnoticed, ifupdown/hook should fix by changing
        mtu of underlying device to the same size as the ipv6
        mtu

    3.  order of the v4 vs. v6 stanzas could affect final mtu
        ipv6 first, then ipv4 with mtu.
    """
    conf_file = "examples/tests/network_mtu.yaml"
    extra_collect_scripts = TestNetworkIPV6Abs.extra_collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        proc_v6="/proc/sys/net/ipv6/conf"
        for f in `seq 0 7`; do
            cat /sys/class/net/interface${f}/mtu |tee interface${f}_dev_mtu;
            cat $proc_v6/interface${f}/mtu |tee interface${f}_ipv6_mtu;
        done
        if [ -e /var/log/upstart ]; then
          cp -a /var/log/upstart ./var_log_upstart
        fi
        """)]

    def _load_mtu_data(self, ifname):
        """ load mtu related files by interface name.
            returns a dictionary with the follwing
            keys:  'device', and 'ipv6'.  """

        mtu_fn = {
            'device': "%s_dev_mtu" % ifname,
            'ipv6': "%s_ipv6_mtu" % ifname,
        }
        mtu_val = {}
        for fnk in mtu_fn.keys():
            mtu_val.update({fnk: int(self.load_collect_file(mtu_fn[fnk]))})

        return mtu_val

    def _check_subnet_mtu(self, subnet, iface):
        mtu_data = self._load_mtu_data(iface['name'])
        print('subnet:%s' % subnet)
        print('mtu_data:%s' % mtu_data)
        # ipv4 address mtu changes *device* mtu
        if '.' in subnet['address']:
            print('subnet_mtu=%s device_mtu=%s' % (int(subnet['mtu']),
                                                   int(mtu_data['device'])))
            self.assertEqual(int(subnet['mtu']),
                             int(mtu_data['device']))
        # ipv6 address mtu changes *protocol* mtu
        elif ':' in subnet['address']:
            print('subnet_mtu=%s ipv6_mtu=%s' % (int(subnet['mtu']),
                                                 int(mtu_data['device'])))
            self.assertEqual(int(subnet['mtu']),
                             int(mtu_data['ipv6']))

    def _check_iface_subnets(self, ifname):
        network_state = self.get_network_state()
        interfaces = network_state.get('interfaces')

        iface = interfaces.get(ifname)
        subnets = iface.get('subnets')
        print('iface=%s subnets=%s' % (iface['name'], subnets))
        for subnet in subnets:
            if 'mtu' in subnet:
                self._check_subnet_mtu(subnet, iface)

    def _disabled_ipv4_and_ipv6_mtu_all(self):
        """ we don't pass all tests, skip for now """
        network_state = self.get_network_state()
        interfaces = network_state.get('interfaces')

        for iface in interfaces.values():
            subnets = iface.get('subnets', {})
            if subnets:
                for index, subnet in zip(range(0, len(subnets)), subnets):
                    print("iface=%s subnet=%s" % (iface['name'], subnet))
                    if 'mtu' in subnet:
                        self._check_subnet_mtu(subnet, iface)

    def test_ipv6_mtu_smaller_than_ipv4_non_default(self):
        self._check_iface_subnets('interface0')

    def test_ipv6_mtu_equal_ipv4_non_default(self):
        self._check_iface_subnets('interface1')

    def test_ipv6_mtu_higher_than_default_no_ipv4_mtu(self):
        self._check_iface_subnets('interface2')

    def test_ipv6_mtu_higher_than_default_no_ipv4_iface_up(self):
        self._check_iface_subnets('interface3')

    def test_ipv6_mtu_smaller_than_ipv4_v6_iface_first(self):
        self._check_iface_subnets('interface4')

    def test_ipv6_mtu_equal_ipv4_non_default_v6_iface_first(self):
        self._check_iface_subnets('interface5')

    def test_ipv6_mtu_higher_than_default_no_ipv4_mtu_v6_iface_first(self):
        self._check_iface_subnets('interface6')

    def test_ipv6_mtu_higher_than_default_no_ipv4_iface_v6_iface_first(self):
        self._check_iface_subnets('interface7')


class CentosTestNetworkMtuAbs(TestNetworkMtuAbs):
    conf_file = "examples/tests/network_mtu.yaml"
    extra_collect_scripts = TestNetworkMtuAbs.extra_collect_scripts + [
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

    @unittest.skip("Sysconfig does not support mixed v4/v6 MTU: LP:#1706973")
    def test_ip_output(self):
        pass

    @unittest.skip("Sysconfig does not support mixed v4/v6 MTU: LP:#1706973")
    def test_ipv6_mtu_smaller_than_ipv4_v6_iface_first(self):
        pass

    @unittest.skip("Sysconfig does not support mixed v4/v6 MTU: LP:#1706973")
    def test_ipv6_mtu_smaller_than_ipv4_non_default(self):
        pass

    @unittest.skip("Sysconfig does not support mixed v4/v6 MTU: LP:#1706973")
    def test_ipv6_mtu_higher_than_default_no_ipv4_iface_up(self):
        pass

    @unittest.skip("Sysconfig does not support mixed v4/v6 MTU: LP:#1706973")
    def test_ipv6_mtu_higher_than_default_no_ipv4_iface_v6_iface_first(self):
        pass


class TrustyTestNetworkMtu(relbase.trusty, TestNetworkMtuAbs):
    __test__ = True

    # FIXME: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=809714
    # fixed in newer ifupdown than is in trusty
    def test_ipv6_mtu_smaller_than_ipv4_non_default(self):
        # trusty ifupdown uses device mtu to change v6 mtu
        pass


class TrustyHWEUTestNetworkMtu(relbase.trusty_hwe_u, TrustyTestNetworkMtu):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEVTestNetworkMtu(relbase.trusty_hwe_v, TrustyTestNetworkMtu):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEWTestNetworkMtu(relbase.trusty_hwe_w, TrustyTestNetworkMtu):
    # unsupported kernel, 2016-08
    __test__ = False


class TrustyHWEXTestNetworkMtu(relbase.trusty_hwe_x, TrustyTestNetworkMtu):
    __test__ = True


class TestNetworkMtu(relbase.xenial, TestNetworkMtuAbs):
    __test__ = True


@TestNetworkMtuAbs.skip_by_date("1671951", fixby="2018-09-26")
class BionicTestNetworkMtu(relbase.bionic, TestNetworkMtuAbs):
    __test__ = True


@TestNetworkMtuAbs.skip_by_date("1671951", fixby="2018-09-26")
class CosmicTestNetworkMtu(relbase.cosmic, TestNetworkMtuAbs):
    __test__ = True


class Centos66TestNetworkMtu(centos_relbase.centos66_xenial,
                             CentosTestNetworkMtuAbs):
    __test__ = True


class Centos70TestNetworkMtu(centos_relbase.centos70_xenial,
                             CentosTestNetworkMtuAbs):
    __test__ = True

# vi: ts=4 expandtab syntax=python
