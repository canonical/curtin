from . import VMBaseClass, logger
from unittest import TestCase

import ipaddress
import os
import re
import textwrap
import yaml


def iface_extract(input):
    mo = re.search(r'^(?P<interface>\w+|\w+:\d+)\s+' +
                   r'Link encap:(?P<link_encap>\S+)\s+' +
                   r'(HWaddr\s+(?P<mac_address>\S+))?' +
                   r'(\s+inet addr:(?P<address>\S+))?' +
                   r'(\s+Bcast:(?P<broadcast>\S+)\s+)?' +
                   r'(Mask:(?P<netmask>\S+)\s+)?',
                   input, re.MULTILINE)

    mtu = re.search(r'(\s+MTU:(?P<mtu>\d+)\s+)\s+', input, re.MULTILINE)
    mtu_info = mtu.groupdict('')
    mtu_info['mtu'] = int(mtu_info['mtu'])

    if mo:
        info = mo.groupdict('')
        info['running'] = False
        info['up'] = False
        info['multicast'] = False
        if 'RUNNING' in input:
            info['running'] = True
        if 'UP' in input:
            info['up'] = True
        if 'MULTICAST' in input:
            info['multicast'] = True
        info.update(mtu_info)
        return info
    return {}


def ifconfig_to_dict(ifconfig):
    interfaces = {}
    for iface in [iface_extract(iface) for iface in ifconfig.split('\n\n')
                  if iface.strip()]:
        interfaces[iface['interface']] = iface

    return interfaces


class TestNetworkAbs(VMBaseClass):
    __test__ = False
    interactive = False
    conf_file = "examples/tests/basic_network.yaml"
    install_timeout = 600
    boot_timeout = 600
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ifconfig -a > ifconfig_a
        cp -av /etc/network/interfaces .
        cp /etc/resolv.conf .
        cp -av /etc/udev/rules.d/70-persistent-net.rules .
        ip -o route show > ip_route_show
        route -n > route_n
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["ifconfig_a",
                                 "interfaces",
                                 "resolv.conf",
                                 "70-persistent-net.rules",
                                 "ip_route_show",
                                 "route_n"])

    def test_etc_network_interfaces(self):
        with open(os.path.join(self.td.mnt, "interfaces")) as fp:
            eni = fp.read()
            logger.debug('etc/network/interfaces:\n{}'.format(eni))

        expected_eni = self.get_expected_etc_network_interfaces()
        eni_lines = eni.split('\n')
        for line in expected_eni.split('\n'):
            self.assertTrue(line in eni_lines)

    def test_etc_resolvconf(self):
        with open(os.path.join(self.td.mnt, "resolv.conf")) as fp:
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

        with open(os.path.join(self.td.mnt, "ifconfig_a")) as fp:
            ifconfig_a = fp.read()
            logger.debug('ifconfig -a:\n{}'.format(ifconfig_a))

        ifconfig_dict = ifconfig_to_dict(ifconfig_a)
        logger.debug('parsed ifcfg dict:\n{}'.format(
            yaml.dump(ifconfig_dict, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.mnt, "ip_route_show")) as fp:
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

        with open(os.path.join(self.td.mnt, "route_n")) as fp:
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


class TrustyTestNetwork(TestNetworkAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "trusty"
    arch = "amd64"


class WilyTestNetwork(TestNetworkAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"


class VividTestNetwork(TestNetworkAbs, TestCase):
    __test__ = True
    repo = "maas-daily"
    release = "vivid"
    arch = "amd64"
