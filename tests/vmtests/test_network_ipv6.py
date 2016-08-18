from . import VMBaseClass, logger, helpers
from .releases import base_vm_classes as relbase

import ipaddress
import os
import re
import textwrap
import yaml


class TestNetworkIPV6Abs(VMBaseClass):
    """ IPV6 complex testing.  The configuration exercises
        - ipv4 and ipv6 address on same interface
        - bonding in LACP mode
        - unconfigured subnets on bond
        - vlans over bonds
        - all IP is static
    """
    conf_file = "examples/network-ipv6-bond-vlan.yaml"
    interactive = False
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        ifconfig -a > ifconfig_a
        ip link show > ip_link_show
        ip a > ip_a
        cp -av /etc/sysctl.d .
        find /etc/network/interfaces.d > find_interfacesd
        cp -av /etc/network/interfaces .
        cp -av /etc/network/interfaces.d .
        cp /etc/resolv.conf .
        cp -av /etc/udev/rules.d/70-persistent-net.rules .
        ip -o route show > ip_route_show
        ip -6 -o route show > ip_6_route_show
        route -n > route_n
        route -6 -n > route_6_n
        cp -av /run/network ./run_network
        grep . -r /sys/class/net/bond0/ > sysfs_bond0 || :
        grep . -r /sys/class/net/bond0.108/ > sysfs_bond0.108 || :
        grep . -r /sys/class/net/bond0.208/ > sysfs_bond0.208 || :
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

        def _mk_dns_lines(dns_type, config):
            """ nameservers get a line per ns
                search is a space-separated list """
            lines = []
            if dns_type == 'nameservers':
                if ' ' in config:
                    config = config.split()
                for ns in config:
                    lines.append("nameserver %s" % ns)
            elif dns_type == 'search':
                if isinstance(config, list):
                    config = " ".join(config)
                lines.append("search %s" % config)

            return lines

        for ifname in expected_ifaces.keys():
            iface = expected_ifaces.get(ifname)
            for k, v in iface.get('dns', {}).items():
                print('k=%s v=%s' % (k, v))
                for dns_line in _mk_dns_lines(k, v):
                    logger.debug('dns_line:%s', dns_line)
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

        with open(os.path.join(self.td.collect, "route_6_n")) as fp:
            route_6_n = fp.read()
            logger.debug("route -6 -n:\n{}".format(route_6_n))

        routes = {
            '4': route_n,
            '6': route_6_n,
        }
        interfaces = network_state.get('interfaces')
        for iface in interfaces.values():
            subnets = iface.get('subnets', {})
            if subnets:
                for index, subnet in zip(range(0, len(subnets)), subnets):
                    iface['index'] = index
                    # ipv6 address can be configured without another iface
                    # kernel entry (there will be no eth0:1 for ipv6 subnets)
                    # FIXME: we need a subnet_is_ipv4/subnet_is_ipv6 method
                    # and this if ipv4 and index != 0; then use name+index
                    # else, just ifname
                    if index == 0 or ":" in subnet.get('address', ""):
                        ifname = "{name}".format(**iface)
                    else:
                        ifname = "{name}:{index}".format(**iface)

                    print('checking on ifname: %s idx=%s' % (ifname, index))
                    self.check_interface(ifname,
                                         index,
                                         iface,
                                         ifconfig_dict.get(ifname),
                                         routes)
            else:
                index = 0
                iface['index'] = index
                print('checking on iface["name"]: %s idx=%s' % (iface['name'],
                                                                index))
                self.check_interface(iface['name'],
                                     index,
                                     iface,
                                     ifconfig_dict.get(iface['name']),
                                     routes)

    def check_interface(self, ifname, index, iface, ifconfig, routes):
        logger.debug(
            'testing ifname:{}\niface:\n{}\n\nifconfig:\n{}'.format(ifname,
                                                                    iface,
                                                                    ifconfig))
        subnets = iface.get('subnets', {})

        # FIXME: remove check?
        # initial check, do we have the correct iface ?
        logger.debug('ifname={}'.format(ifname))
        logger.debug("ifconfig['interface']={}".format(ifconfig['interface']))
        self.assertEqual(ifname, ifconfig['interface'])

        # check physical interface attributes (skip bond members, macs change)
        if iface['type'] in ['physical'] and 'bond-master' not in iface:
            for key in ['mac_address']:
                print("checking mac on iface: %s" % iface['name'])
                if key in iface and iface[key]:
                    self.assertEqual(iface[key].lower(),
                                     ifconfig[key].lower())

        # we can check mtu on all interfaces
        for key in ['mtu']:
            if key in iface and iface[key]:
                print("checking mtu on iface: %s" % iface['name'])
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
        config_inet_iface = None
        found_inet_iface = None
        if subnets:
            subnet = __get_subnet(subnets, index)
            print('validating subnet idx=%s: \n%s' % (index, subnet))
            if 'address' in subnet and subnet['address']:
                # we will create to ipaddress.IPvXInterface objects
                # one based on config, and other from collected data
                # and compare.
                config_ipstr = subnet['address']
                if 'netmask' in subnet:
                    config_ipstr += "/%s" % subnet['netmask']

                # One more bit is how to construct the
                # right Version interface, detecting on ":" in address
                # detect ipv6 or v4
                if ':' in subnet['address']:
                    config_inet_iface = ipaddress.IPv6Interface(config_ipstr)
                    # if we're v6, the ifconfig dict has a list of ipv6
                    # addresses found on the interface, we walk this list
                    # looking for a matching address, or it wasn't found
                    for inet6 in ifconfig.get('inet6', []):
                        # we've a match, now contruct the ipaddress interface
                        if inet6['address'] == subnet['address']:
                            found_ipstr = inet6['address']
                            if 'netmask' in subnet:
                                found_ipstr += "/%s" % inet6.get('prefixlen')
                            found_inet_iface = (
                                ipaddress.IPv6Interface(found_ipstr))
                else:
                    # boring ipv4
                    config_inet_iface = ipaddress.IPv4Interface(config_ipstr)

                    found_ipstr = "%s/%s" % (ifconfig['address'],
                                             ifconfig['netmask'])
                    found_inet_iface = ipaddress.IPv4Interface(found_ipstr)

                # check ipaddress interface matches (config vs. found)
                self.assertIsNotNone(config_inet_iface)
                self.assertIsNotNone(found_inet_iface)
                self.assertEqual(config_inet_iface, found_inet_iface)

            def __find_gw_config(subnet):
                gateways = []
                if 'gateway' in subnet:
                    gateways.append(subnet.get('gateway'))
                for route in subnet.get('routes', []):
                    gateways += __find_gw_config(route)
                return gateways

            # handle gateways by looking at routing table
            configured_gws = __find_gw_config(subnet)
            for gw_ip in configured_gws:
                logger.debug('found a gateway in subnet config: %s', gw_ip)
                if ":" in gw_ip:
                    route_d = routes['6']
                else:
                    route_d = routes['4']

                found_gws = [line for line in route_d.split('\n')
                             if 'UG' in line and gw_ip in line]
                logger.debug('found a gateway in guest output:\n%s', found_gws)

                self.assertEqual(len(found_gws), len(configured_gws))
                for fgw in found_gws:
                    if ":" in gw_ip:
                        (dest, gw, flags, metric, ref, use, iface) = \
                            fgw.split()
                    else:
                        (dest, gw, genmask, flags, metric, ref, use, iface) = \
                            fgw.split()
                    logger.debug('configured gw:%s found gw:%s', gw_ip, gw)
                    self.assertEqual(gw_ip, gw)


class PreciseHWETTestNetwork(relbase.precise_hwe_t, TestNetworkIPV6Abs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkIPV6(relbase.trusty, TestNetworkIPV6Abs):
    __test__ = True


class TrustyHWEUTestNetworkIPV6(relbase.trusty_hwe_u, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkIPV6(relbase.trusty_hwe_v, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkIPV6(relbase.trusty_hwe_w, TrustyTestNetworkIPV6):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkIPV6(relbase.xenial, TestNetworkIPV6Abs):
    __test__ = True


class YakketyTestNetworkIPV6(relbase.yakkety, TestNetworkIPV6Abs):
    __test__ = True
