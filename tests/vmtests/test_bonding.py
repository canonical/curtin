from . import VMBaseClass, logger, helpers
from .releases import base_vm_classes as relbase

import ipaddress
import os
import re
import textwrap
import yaml


class TestNetworkAbs(VMBaseClass):
    interactive = False
    conf_file = "examples/tests/bonding_network.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ifconfig -a > ifconfig_a
        cp -av /etc/network/interfaces .
        cp -av /etc/udev/rules.d/70-persistent-net.rules .
        ip -o route show > ip_route_show
        route -n > route_n
        dpkg-query -W -f '${Status}' ifenslave > ifenslave_installed
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["ifconfig_a",
                                 "interfaces",
                                 "70-persistent-net.rules",
                                 "ip_route_show",
                                 "ifenslave_installed",
                                 "route_n"])

    def test_ifenslave_installed(self):
        with open(os.path.join(self.td.collect, "ifenslave_installed")) as fp:
            status = fp.read().strip()
            logger.debug('ifenslave installed: {}'.format(status))
            self.assertEqual('install ok installed', status)

    def test_etc_network_interfaces(self):
        with open(os.path.join(self.td.collect, "interfaces")) as fp:
            eni = fp.read()
            logger.debug('etc/network/interfaces:\n{}'.format(eni))

        expected_eni = self.get_expected_etc_network_interfaces()
        eni_lines = eni.split('\n')
        for line in expected_eni.split('\n'):
            self.assertTrue(line in eni_lines)

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
        # FIXME: can't check mac_addr under bonding since
        # the bond might change slave mac addrs
        for key in ['mtu']:
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


class PreciseHWETTestBonding(relbase.precise_hwe_t, TestNetworkAbs):
    __test__ = True
    # package names on precise are different, need to check on ifenslave-2.6
    collect_scripts = TestNetworkAbs.collect_scripts + [textwrap.dedent("""
             cd OUTPUT_COLLECT_D
             dpkg-query -W -f '${Status}' ifenslave-2.6 > ifenslave_installed
             """)]


class TrustyTestBonding(relbase.trusty, TestNetworkAbs):
    __test__ = False


class TrustyHWEUTestBonding(relbase.trusty_hwe_u, TrustyTestBonding):
    __test__ = True


class TrustyHWEVTestBonding(relbase.trusty_hwe_v, TrustyTestBonding):
    # Working, but off by default to safe test suite runtime
    # oldest/newest HWE-* covered above/below
    __test__ = False


class TrustyHWEWTestBonding(relbase.trusty_hwe_w, TrustyTestBonding):
    __test__ = True


class WilyTestBonding(relbase.wily, TestNetworkAbs):
    __test__ = True


class XenialTestBonding(relbase.xenial, TestNetworkAbs):
    __test__ = True


class YakketyTestBonding(relbase.yakkety, TestNetworkAbs):
    __test__ = True
