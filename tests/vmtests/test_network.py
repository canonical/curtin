from . import VMBaseClass, logger, helpers
from .releases import base_vm_classes as relbase

import ipaddress
import os
import re
import textwrap
import yaml


class TestNetworkBaseTestsAbs(VMBaseClass):
    interactive = False
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        echo "waiting for ipv6 to settle" && sleep 5
        ifconfig -a > ifconfig_a
        ip link show > ip_link_show
        ip a > ip_a
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
        cp -av /var/log/upstart ./upstart ||:
        sleep 10 && ip a > ip_a
        """)]

    def test_output_files_exist(self):
        self.output_files_exist([
            "70-persistent-net.rules",
            "find_interfacesd",
            "ifconfig_a",
            "interfaces",
            "ip_a",
            "ip_route_show",
            "resolv.conf",
            "route_6_n",
            "route_n",
        ])

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

    def test_ip_output(self):
        '''check iproute2 'ip a' output with test input'''
        network_state = self.get_network_state()
        logger.debug('expected_network_state:\n{}'.format(
            yaml.dump(network_state, default_flow_style=False, indent=4)))

        with open(os.path.join(self.td.collect, "ip_a")) as fp:
            ip_a = fp.read()
            logger.debug('ip a:\n{}'.format(ip_a))

        ip_dict = helpers.ip_a_to_dict(ip_a)
        print('parsed ip_a dict:\n{}'.format(
            yaml.dump(ip_dict, default_flow_style=False, indent=4)))

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
            print("\nnetwork_state iface: %s" % (
                yaml.dump(iface, default_flow_style=False, indent=4)))
            self.check_interface(iface['name'],
                                 iface,
                                 ip_dict.get(iface['name']),
                                 routes)

    def check_interface(self, ifname, iface, ipcfg, routes):
        print('check_interface: testing '
              'ifname:{}\niface:\n{}\n\nipcfg:\n{}'.format(ifname, iface,
                                                           ipcfg))
        # FIXME: remove check?
        # initial check, do we have the correct iface ?
        print('ifname={}'.format(ifname))
        self.assertEqual(ifname, ipcfg['interface'])
        print("ipcfg['interface']={}".format(ipcfg['interface']))

        # check physical interface attributes (skip bond members, macs change)
        if iface['type'] in ['physical'] and 'bond-master' not in iface:
            for key in ['mac_address']:
                print("checking mac on iface: %s" % iface['name'])
                if key in iface and iface[key]:
                    self.assertEqual(iface[key].lower(),
                                     ipcfg[key].lower())

        # we can check mtu on all interfaces
        for key in ['mtu']:
            if key in iface and iface[key]:
                print("checking mtu on iface: %s" % iface['name'])
                self.assertEqual(int(iface[key]),
                                 int(ipcfg[key]))

        # check subnet related attributes
        subnets = iface.get('subnets')
        if subnets is None:
            subnets = []
        for subnet in subnets:
            config_inet_iface = None
            found_inet_iface = None
            print('validating subnet:\n%s' % subnet)
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
                    # v6
                    config_inet_iface = ipaddress.IPv6Interface(config_ipstr)
                    ip_func = ipaddress.IPv6Interface
                    addresses = ipcfg.get('inet6', [])
                else:
                    # v4
                    config_inet_iface = ipaddress.IPv4Interface(config_ipstr)
                    ip_func = ipaddress.IPv4Interface
                    addresses = ipcfg.get('inet4', [])

                # find a matching
                print('found addresses: %s' % addresses)
                for ip in addresses:
                    print('cur ip=%s\nsubnet=%s' % (ip, subnet))
                    # drop /CIDR if present for matching
                    if (ip['address'].split("/")[0] ==
                       subnet['address'].split("/")[0]):
                        print('found a match!')
                        found_ipstr = ip['address']
                        if ('netmask' in subnet or '/' in subnet['address']):
                            found_ipstr += "/%s" % ip.get('prefixlen')
                        found_inet_iface = ip_func(found_ipstr)
                        print('returning inet iface')
                        break

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
            print('iface:%s configured_gws: %s' % (ifname, configured_gws))
            for gw_ip in configured_gws:
                logger.debug('found a gateway in subnet config: %s', gw_ip)
                if ":" in gw_ip:
                    route_d = routes['6']
                else:
                    route_d = routes['4']

                found_gws = [line for line in route_d.split('\n')
                             if 'UG' in line and gw_ip in line]
                logger.debug('found gateways in guest output:\n%s', found_gws)

                print('found_gws: %s\nexpected: %s' % (found_gws,
                                                       configured_gws))
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


class TestNetworkBasicAbs(TestNetworkBaseTestsAbs):
    """ Basic network testing with ipv4
    """
    conf_file = "examples/tests/basic_network.yaml"


class PreciseHWETTestNetworkBasic(relbase.precise_hwe_t, TestNetworkBasicAbs):
    # FIXME: off due to hang at test: Starting execute cloud user/final scripts
    __test__ = False


class TrustyTestNetworkBasic(relbase.trusty, TestNetworkBasicAbs):
    __test__ = True


class TrustyHWEUTestNetworkBasic(relbase.trusty_hwe_u, TrustyTestNetworkBasic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEVTestNetworkBasic(relbase.trusty_hwe_v, TrustyTestNetworkBasic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class TrustyHWEWTestNetworkBasic(relbase.trusty_hwe_w, TrustyTestNetworkBasic):
    # Working, off by default to safe test suite runtime, covered by bonding
    __test__ = False


class XenialTestNetworkBasic(relbase.xenial, TestNetworkBasicAbs):
    __test__ = True


class YakketyTestNetworkBasic(relbase.yakkety, TestNetworkBasicAbs):
    __test__ = True
