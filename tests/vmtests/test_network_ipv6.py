from . import VMBaseClass, logger
from .releases import base_vm_classes as relbase

import ipaddress
import os
import re
import subprocess
import textwrap
import yaml


class TestNetworkIPV6Abs(VMBaseClass):
    interactive = False
    conf_file = "examples/network-ipv6-bond-vlan.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ifconfig -a > ifconfig_a
        cp -av /etc/network/interfaces .
        cp -av /etc/network/interfaces.d .
        cp /etc/resolv.conf .
        cp -av /etc/udev/rules.d/70-persistent-net.rules .
        ip -o route show > ip_route_show
        route -n > route_n
        cp -av /run/network ./run_network
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["ifconfig_a",
                                 "interfaces",
                                 "resolv.conf",
                                 "70-persistent-net.rules",
                                 "ip_route_show",
                                 "route_n"])

    def test_etc_network_interfaces(self):
        with open(os.path.join(self.td.collect, "interfaces")) as fp:
            eni = fp.read()
            logger.debug('etc/network/interfaces:\n{}'.format(eni))

        expected_eni = self.get_expected_etc_network_interfaces()
        eni_lines = eni.split('\n')
        for line in expected_eni.split('\n'):
            self.assertTrue(line in eni_lines)

    def test_etc_resolvconf(self):
        with open(os.path.join(self.td.collect, "resolv.conf")) as fp:
            resolvconf = fp.read()
            logger.debug('etc/resolv.conf:\n{}'.format(resolvconf))

        resolv_lines = resolvconf.split('\n')
        logger.debug('resolv.conf lines:\n{}'.format(resolv_lines))
        # resolv.conf
        '''
        nameserver X.Y.Z.A
        nameserver 1.2.3.4
        search foo.bar
        '''

        # eni
        ''''
        auto eth1:1
        iface eth1:1 inet static
            dns-nameserver X.Y.Z.A
            dns-search foo.bar
        '''

        # iface dict
        ''''
        eth1:1:
          dns:
            nameserver: X.Y.Z.A
            search: foo.bar
        '''
        expected_ifaces = self.get_expected_etc_resolvconf()
        logger.debug('parsed eni ifaces:\n{}'.format(expected_ifaces))
        for ifname in expected_ifaces.keys():
            iface = expected_ifaces.get(ifname)
            for k, v in iface.get('dns', {}).items():
                dns_line = '{} {}'.format(
                    k.replace('nameservers', 'nameserver'), " ".join(v))
                logger.debug('dns_line:{}'.format(dns_line))
                self.assertTrue(dns_line in resolv_lines)

    def test_ifconfig_output(self):
        '''check ifconfig output with test input'''
        network_state = self.get_network_state()
        logger.debug('expected_network_state:\n{}'.format(
            yaml.dump(network_state, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.collect, "ifconfig_a")) as fp:
            ifconfig_a = fp.read()
            logger.debug('ifconfig -a:\n{}'.format(ifconfig_a))

        ifconfig_dict = helpers.ifconfig_to_dict(ifconfig_a)
        logger.debug('parsed ifcfg dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.collect, "ip_route_show")) as fp:
            ip_route_show = fp.read()
            logger.debug("ip route show:\n{}".format(ip_route_show))
            for line in [line for line in ip_route_show.split('\n')
                         if 'src' in line]:
                m = re.search(r'^(?P<network>\S+)\sdev\s' +
                              r'(?P<devname>\S+)\s+' +
                              r'proto kernel\s+scope link' +
                              r'\s+src\s(?P<src_ip>\S+)',
                              line)
                route_info = m.groupdict('')
                logger.debug(route_info)

        with open(os.path.join(self.td.collect, "route_n")) as fp:
            route_n = fp.read()
            logger.debug("route -n:\n{}".format(route_n))

        interfaces = network_state.get('interfaces')
        for iface in interfaces.values():
            subnets = iface.get('subnets', {})
            if subnets:
                for index, subnet in zip(range(0, len(subnets)), subnets):
                    iface['index'] = index
                    if index == 0:
                        ifname = "{name}".format(**iface)
                    else:
                        ifname = "{name}:{index}".format(**iface)

                    self.check_interface(iface,
                                         ifconfig_dict.get(ifname),
                                         route_n)
            else:
                iface['index'] = 0
                self.check_interface(iface,
                                     ifconfig_dict.get(iface['name']),
                                     route_n)

    def check_interface(self, iface, ifconfig, route_n):
        logger.debug(
            'testing iface:\n{}\n\nifconfig:\n{}'.format(iface, ifconfig))
        subnets = iface.get('subnets', {})
        if subnets and iface['index'] != 0:
            ifname = "{name}:{index}".format(**iface)
        else:
            ifname = "{name}".format(**iface)

        # initial check, do we have the correct iface ?
        logger.debug('ifname={}'.format(ifname))
        logger.debug("ifconfig['interface']={}".format(ifconfig['interface']))
        self.assertEqual(ifname, ifconfig['interface'])

        # check physical interface attributes
        for key in ['mac_address', 'mtu']:
            if key in iface and iface[key]:
                self.assertEqual(iface[key],
                                 ifconfig[key])

        def __get_subnet(subnets, subidx):
            for index, subnet in zip(range(0, len(subnets)), subnets):
                if index == subidx:
                    break
            return subnet

        # check subnet related attributes, and specifically only
        # the subnet specified by iface['index']
        subnets = iface.get('subnets', {})
        if subnets:
            subnet = __get_subnet(subnets, iface['index'])
            if 'address' in subnet and subnet['address']:
                if ':' in subnet['address']:
                    inet_iface = ipaddress.IPv6Interface(
                        subnet['address'])
                else:
                    inet_iface = ipaddress.IPv4Interface(
                        subnet['address'])

                # check ip addr
                self.assertEqual(str(inet_iface.ip),
                                 ifconfig['address'])

                self.assertEqual(str(inet_iface.netmask),
                                 ifconfig['netmask'])

                self.assertEqual(
                    str(inet_iface.network.broadcast_address),
                    ifconfig['broadcast'])

            # handle gateway by looking at routing table
            if 'gateway' in subnet and subnet['gateway']:
                gw_ip = subnet['gateway']
                gateways = [line for line in route_n.split('\n')
                            if 'UG' in line and gw_ip in line]
                logger.debug('matching gateways:\n{}'.format(gateways))
                self.assertEqual(len(gateways), 1)
                [gateways] = gateways
                (dest, gw, genmask, flags, metric, ref, use, iface) = \
                    gateways.split()
                logger.debug('expected gw:{} found gw:{}'.format(gw_ip, gw))
                self.assertEqual(gw_ip, gw)


class TestNetworkIPV6StaticAbs(TestNetworkIPV6Abs):
    conf_file = "examples/tests/basic_network_static_ipv6.yaml"


class TestNetworkIPV6VlanAbs(TestNetworkIPV6Abs):
    conf_file = "examples/tests/vlan_network_ipv6.yaml"
    collect_scripts = TestNetworkIPV6Abs.collect_scripts + [textwrap.dedent("""
             cd OUTPUT_COLLECT_D
             dpkg-query -W -f '${Status}' vlan > vlan_installed
             ip -d link show eth1.2667 > ip_link_show_eth1.2667
             ip -d link show eth1.2668 > ip_link_show_eth1.2668
             ip -d link show eth1.2669 > ip_link_show_eth1.2669
             ip -d link show eth1.2670 > ip_link_show_eth1.2670
             """)]

    def get_vlans(self):
        network_state = self.get_network_state()
        logger.debug('get_vlans ns:\n{}'.format(
            yaml.dump(network_state, default_flow_style=False, indent=4)))
        interfaces = network_state.get('interfaces')
        return [iface for iface in interfaces.values()
                if iface['type'] == 'vlan']

    def test_output_files_exist_vlan(self):
        link_files = ["ip_link_show_{}".format(vlan['name'])
                      for vlan in self.get_vlans()]
        self.output_files_exist(["vlan_installed"] + link_files)

    def test_vlan_installed(self):
        with open(os.path.join(self.td.collect, "vlan_installed")) as fp:
            status = fp.read().strip()
            logger.debug('vlan installed?: {}'.format(status))
            self.assertEqual('install ok installed', status)

    def test_vlan_enabled(self):

        # we must have at least one
        self.assertGreaterEqual(len(self.get_vlans()), 1)

        # did they get configured?
        for vlan in self.get_vlans():
            link_file = "ip_link_show_" + vlan['name']
            vlan_msg = "vlan protocol 802.1Q id " + str(vlan['vlan_id'])
            self.check_file_regex(link_file, vlan_msg)


class TestNetworkIPV6ENISource(TestNetworkIPV6Abs):
    """ Curtin now emits a source /etc/network/interfaces.d/*.cfg
        line.  This test exercises this feature by emitting additional
        network configuration in /etc/network/interfaces.d/eth2.cfg

        This relies on the network_config.yaml of the TestClass to
        define a spare nic with no configuration.  This ensures that
        a udev rule for eth2 is emitted so we can reference the interface
        in our injected configuration.

        Note, ifupdown allows multiple stanzas with the same iface name
        and combines the options together during ifup.  We rely on this
        feature allowing etc/network/interfaces to have an unconfigured
        iface eth2 inet manual line, and then defer the configuration
        to /etc/network/interfaces.d/eth2.cfg

        This testcase then uses curtin.net.deb_parse_config method to
        extract information about what curtin wrote and compare that
        with what was actually configured (which we capture via ifconfig)
    """

    conf_file = "examples/tests/network_source_ipv6.yaml"
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ifconfig -a > ifconfig_a
        cp -av /etc/network/interfaces .
        cp -a /etc/network/interfaces.d .
        cp /etc/resolv.conf .
        cp -av /etc/udev/rules.d/70-persistent-net.rules .
        ip -o route show > ip_route_show
        route -n > route_n
        """)]

    def test_source_cfg_exists(self):
        """Test that our curthooks wrote our injected config."""
        self.output_files_exist(["interfaces.d/eth2.cfg"])

    def test_etc_network_interfaces_source_cfg(self):
        """ Compare injected configuration as parsed by curtin matches
            how ifup configured the interface."""
        # interfaces uses absolute paths, fix for test-case
        interfaces = os.path.join(self.td.collect, "interfaces")
        cmd = ['sed', '-i.orig', '-e', 's,/etc/network/,,g',
               '{}'.format(interfaces)]
        subprocess.check_call(cmd, stderr=subprocess.STDOUT)

        curtin_ifaces = self.parse_deb_config(interfaces)
        logger.debug('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))
        print('parsed eni dict:\n{}'.format(
            yaml.dump(curtin_ifaces, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.collect, "ifconfig_a")) as fp:
            ifconfig_a = fp.read()
            logger.debug('ifconfig -a:\n{}'.format(ifconfig_a))

        ifconfig_dict = helpers.ifconfig_to_dict(ifconfig_a)
        logger.debug('parsed ifconfig dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))
        print('parsed ifconfig dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))

        iface = 'eth2'
        self.assertTrue(iface in curtin_ifaces)

        expected_address = curtin_ifaces[iface].get('address', None)
        self.assertIsNotNone(expected_address)

        # handle CIDR notation
        def _nocidr(addr):
            return addr.split("/")[0]
        actual_address = ifconfig_dict[iface].get('address', "")
        self.assertEqual(_nocidr(expected_address), _nocidr(actual_address))


class PreciseHWETTestNetwork(relbase.precise_hwe_t, TestNetworkIPV6Abs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class PreciseHWETTestNetworkIPV6Static(relbase.precise_hwe_t,
                                      TestNetworkIPV6StaticAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkIPV6(relbase.trusty, TestNetworkIPV6Abs):
    __test__ = True


class TrustyTestNetworkIPV6Static(relbase.trusty, TestNetworkIPV6StaticAbs):
    __test__ = True


class TrustyHWEUTestNetworkIPV6(relbase.trusty_hwe_u, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEUTestNetworkIPV6Static(relbase.trusty_hwe_u,
                                      TestNetworkIPV6StaticAbs):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkIPV6(relbase.trusty_hwe_v, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkIPV6Static(relbase.trusty_hwe_v,
                                      TestNetworkIPV6StaticAbs):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkIPV6(relbase.trusty_hwe_w, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkIPV6Static(relbase.trusty_hwe_w,
                                      TestNetworkIPV6StaticAbs):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkIPV6(relbase.xenial, TestNetworkIPV6Abs):
    __test__ = True


class XenialTestNetworkIPV6Static(relbase.xenial, TestNetworkIPV6StaticAbs):
    __test__ = True


class PreciseTestNetworkIPV6Vlan(relbase.precise, TestNetworkIPV6VlanAbs):
    __test__ = True

    # precise ip -d link show output is different (of course)
    def test_vlan_enabled(self):

        # we must have at least one
        self.assertGreaterEqual(len(self.get_vlans()), 1)

        # did they get configured?
        for vlan in self.get_vlans():
            link_file = "ip_link_show_" + vlan['name']
            vlan_msg = "vlan id " + str(vlan['vlan_id'])
            self.check_file_regex(link_file, vlan_msg)


class TrustyTestNetworkIPV6Vlan(relbase.trusty, TestNetworkIPV6VlanAbs):
    __test__ = True


class XenialTestNetworkIPV6Vlan(relbase.xenial, TestNetworkIPV6VlanAbs):
    __test__ = True


class PreciseTestNetworkIPV6ENISource(relbase.precise,
                                      TestNetworkIPV6ENISource):
    __test__ = False
    # not working, still debugging though; possible older ifupdown doesn't
    # like the multiple iface method.


class TrustyTestNetworkIPV6ENISource(relbase.trusty, TestNetworkIPV6ENISource):
    __test__ = True


class XenialTestNetworkIPV6ENISource(relbase.xenial, TestNetworkIPV6ENISource):
    __test__ = True
