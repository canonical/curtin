# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, helpers, skip_if_flag
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

from unittest import SkipTest
from curtin import config

import glob
import ipaddress
import os
import re
import textwrap
import yaml


class TestNetworkBaseTestsAbs(VMBaseClass):
    interactive = False
    test_type = 'network'
    extra_disks = []
    extra_nics = []
    # XXX: command | tee output is required for Centos under SELinux
    # http://danwalsh.livejournal.com/22860.html
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        echo "waiting for ipv6 to settle" && sleep 5
        route -n | tee first_route_n
        ip link show | tee ip_link_show
        cp /etc/resolv.conf .
        cp -av /etc/udev/rules.d/70-persistent-net.rules . ||:
        ip -o route show | tee ip_route_show
        ip -6 -o route show | tee ip_6_route_show
        route -n |tee route_n
        route -n -A inet6 |tee route_6_n
        cp -av /run/network ./run_network
        cp -av /var/log/upstart ./upstart ||:
        cp -av /etc/cloud ./etc_cloud
        cp -av /var/log/cloud*.log ./
        V=/usr/lib/python*/*-packages/cloudinit/version.py;
        grep -c NETWORK_CONFIG_V2 $V |tee cloudinit_passthrough_available
        mkdir -p etc_netplan
        cp -av /etc/netplan/* ./etc_netplan/ ||:
        networkctl |tee networkctl
        mkdir -p run_systemd_network
        cp -a /run/systemd/network/* ./run_systemd_network/ ||:
        cp -a /run/systemd/netif ./run_systemd_netif ||:
        cp -a /run/systemd/resolve ./run_systemd_resolve ||:
        cp -a /etc/systemd ./etc_systemd ||:
        journalctl --no-pager -b -x | tee journalctl_out
        sleep 10 && ip a | tee  ip_a

        exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_output_files_exist(self):
        self.output_files_exist([
            "ip_a",
            "ip_route_show",
            "route_6_n",
            "route_n",
        ])

    def read_eni(self):
        eni = ""
        eni_cfg = ""

        eni = self.load_collect_file("interfaces")
        self.logger.debug('etc/network/interfaces:\n{}'.format(eni))

        # we don't use collect_path as we're building a glob
        eni_dir = os.path.join(self.td.collect, "interfaces.d", "*.cfg")
        eni_cfg = '\n'.join([self.load_collect_file(cfg)
                             for cfg in glob.glob(eni_dir)])

        return (eni, eni_cfg)

    def _network_renderer(self):
        """ Determine if target uses eni/ifupdown or netplan/networkd """

        etc_netplan = self.collect_path('etc_netplan')
        networkd = self.collect_path('run_systemd_network')

        if len(os.listdir(etc_netplan)) > 0 and len(os.listdir(networkd)) > 0:
            print('Network Renderer: systemd-networkd')
            return 'systemd-networkd'

        print('Network Renderer: ifupdown')
        return 'ifupdown'

    @skip_if_flag('expected_failure')
    def test_etc_network_interfaces(self):
        avail_str = self.load_collect_file('cloudinit_passthrough_available')
        pt_available = int(avail_str) == 1
        print('avail_str=%s pt_available=%s' % (avail_str, pt_available))

        if self._network_renderer() != "ifupdown" or pt_available:
            reason = ("{}: using net-passthrough; "
                      "deferring to cloud-init".format(self.__class__))
            raise SkipTest(reason)

        if not pt_available:
            raise SkipTest(
                'network passthrough not available on %s' % self.__class__)

        eni, eni_cfg = self.read_eni()
        self.logger.debug('etc/network/interfaces:\n{}'.format(eni))
        expected_eni = self.get_expected_etc_network_interfaces()

        eni_lines = eni.split('\n') + eni_cfg.split('\n')
        print("\n".join(eni_lines))
        expected_eni_lines = [
            line for line in expected_eni.split('\n') if len(line) > 0]
        for line in expected_eni_lines:
            if line.startswith("#"):
                continue
            if "hwaddress ether" in line:
                continue
            print('expected line:\n%s' % line)
            self.assertTrue(line in eni_lines, "not in eni: %s" % line)

    @skip_if_flag('expected_failure')
    def test_cloudinit_network_passthrough(self):
        cc_passthrough = "cloud.cfg.d/50-curtin-networking.cfg"

        avail_str = self.load_collect_file('cloudinit_passthrough_available')
        available = int(avail_str) == 1
        print('avail_str=%s available=%s' % (avail_str, available))

        if not available:
            raise SkipTest('not available on %s' % self.__class__)

        print('passthrough was available')
        pt_file = os.path.join(self.td.collect, 'etc_cloud',
                               cc_passthrough)
        print('checking if passthrough file written: %s' % pt_file)
        self.assertTrue(os.path.exists(pt_file))

        # compare
        original = {'network':
                    config.load_config(self.conf_file).get('network')}
        intarget = config.load_config(pt_file)
        self.assertEqual(original, intarget)

    @skip_if_flag('expected_failure')
    def test_cloudinit_network_disabled(self):
        cc_disabled = 'cloud.cfg.d/curtin-disable-cloudinit-networking.cfg'

        avail_str = self.load_collect_file('cloudinit_passthrough_available')
        available = int(avail_str) == 1
        print('avail_str=%s available=%s' % (avail_str, available))

        if available:
            raise SkipTest('passthrough available on %s' % self.__class__)

        print('passthrough not available')
        cc_disable_file = os.path.join(self.td.collect, 'etc_cloud',
                                       cc_disabled)
        print('checking if network:disable file written: %s' %
              cc_disable_file)
        self.assertTrue(os.path.exists(cc_disable_file))

        # compare
        original = {'network': {'config': 'disabled'}}
        intarget = config.load_config(cc_disable_file)

        print('checking cloud-init network-cfg content')
        self.assertEqual(original, intarget)

    @skip_if_flag('expected_failure')
    def test_etc_resolvconf(self):
        render2resolvconf = {
            'ifupdown': "resolv.conf",
            'systemd-networkd': "run_systemd_resolve/resolv.conf"
        }
        resolvconfpath = render2resolvconf.get(self._network_renderer(), None)
        self.assertTrue(resolvconfpath is not None)
        self.logger.debug('Selected path to resolvconf: %s', resolvconfpath)

        resolvconf = self.load_collect_file(resolvconfpath)
        self.logger.debug('etc/resolv.conf:\n{}'.format(resolvconf))

        resolv_lines = resolvconf.split('\n')
        self.logger.debug('resolv.conf lines:\n{}'.format(resolv_lines))
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
        self.logger.debug('parsed eni ifaces:\n{}'.format(expected_ifaces))

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
                    self.logger.debug('dns_line:%s', dns_line)
                    self.assertTrue(dns_line in resolv_lines)

    @skip_if_flag('expected_failure')
    def test_static_routes(self):
        '''check routing table'''
        network_state = self.get_network_state()

        # if we're using passthrough then we can't load state
        cc_passthrough = "cloud.cfg.d/50-curtin-networking.cfg"
        pt_file = os.path.join(self.td.collect, 'etc_cloud', cc_passthrough)
        print('checking if passthrough file written: %s' % pt_file)
        if not network_state and os.path.exists(pt_file):
            raise SkipTest('passthrough enabled, skipping %s' % self.__class__)

        ip_route_show = self.load_collect_file("ip_route_show")
        route_n = self.load_collect_file("route_n")

        print("ip route show:\n%s" % ip_route_show)
        print("route -n:\n%s" % route_n)
        routes = network_state.get('routes', [])
        print("found routes: [%s]" % routes)
        for route in routes:
            print('Checking static route: %s' % route)
            destnet = (
                ipaddress.IPv4Network("%s/%s" % (route.get('network'),
                                                 route.get('netmask'))))
            route['destination'] = destnet.with_prefixlen
            expected_string = (
                "{destination} via {gateway} dev.*".format(**route))
            if route.get('metric', 0) > 0:
                expected_string += "metric {metric}".format(**route)
            print('searching for: %s' % expected_string)
            m = re.search(expected_string, ip_route_show, re.MULTILINE)
            self.assertTrue(m is not None)

    @skip_if_flag('expected_failure')
    def test_ip_output(self):
        '''check iproute2 'ip a' output with test input'''
        network_state = self.get_network_state()
        self.logger.debug('expected_network_state:\n{}'.format(
            yaml.dump(network_state, default_flow_style=False, indent=4)))

        ip_a = self.load_collect_file("ip_a")
        self.logger.debug('ip a:\n{}'.format(ip_a))

        ip_dict = helpers.ip_a_to_dict(ip_a)
        print('parsed ip_a dict:\n{}'.format(
            yaml.dump(ip_dict, default_flow_style=False, indent=4)))

        route_n = self.load_collect_file("route_n")
        self.logger.debug("route -n:\n{}".format(route_n))

        route_6_n = self.load_collect_file("route_6_n")
        self.logger.debug("route -6 -n:\n{}".format(route_6_n))

        ip_route_show = self.load_collect_file("ip_route_show")
        ip_6_route_show = self.load_collect_file("ip_6_route_show")
        self.logger.debug("ip route show:\n{}".format(ip_route_show))
        for line in [line for line in ip_route_show.split('\n')
                     if 'src' in line and not line.startswith('default')]:
            print('ip_route_show: line: %s' % line)
            m = re.search(r'^(?P<network>\S+)\sdev\s' +
                          r'(?P<devname>\S+)\s+' +
                          r'proto\s(?P<proto>\S+)\s+' +
                          r'scope\s(?P<scope>\S+)\s+' +
                          r'src\s(?P<src_ip>\S+)',
                          line)
            if m:
                route_info = m.groupdict('')
                self.logger.debug(route_info)
            else:
                raise ValueError('Failed match ip_route_show line: %s' % line)

        routes = {
            '4': route_n,
            'ip_route_show': ip_route_show,
            '6': route_6_n,
            'ip_6_route_show': ip_6_route_show,
        }
        interfaces = network_state.get('interfaces')
        for iface in interfaces.values():
            print("\nnetwork_state iface: %s" % (
                yaml.dump(iface, default_flow_style=False, indent=4)))
            ipcfg = ip_dict.get(iface['name'], {})
            self.check_interface(iface['name'],
                                 iface,
                                 ipcfg,
                                 routes)

    def check_interface(self, ifname, iface, ipcfg, routes):
        print('check_interface: testing '
              'ifname:{}\niface:\n{}\n\nipcfg:\n{}'.format(ifname, iface,
                                                           ipcfg))
        # FIXME: remove check?
        # initial check, do we have the correct iface ?
        print('ifname={}'.format(ifname))
        self.assertTrue(isinstance(ipcfg, dict), "%s is not dict" % (ipcfg))
        print("ipcfg['interface']={}".format(ipcfg['interface']))
        self.assertEqual(ifname, ipcfg['interface'])

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
                # drop duplicate gateways (static routes)
                return list(set(gateways))

            def __has_gw_route(line, gw_ip):
                # For Disco and older releases we match
                #    'UG' matches route_* gateways
                # For Eoan which does not contain net-tools/route commands
                #  'default' matches ip_route/ip_6_route default routes
                #  'via' matches ip_route/ip_6_route non-default gateways
                gwk = {'UG', 'default', 'via'}
                return gwk.intersection(set(line.split())) and gw_ip in line

            # handle gateways by looking at routing table
            configured_gws = __find_gw_config(subnet)
            print('iface:%s configured_gws: %s' % (ifname, configured_gws))
            for gw_ip in configured_gws:
                self.logger.debug('found a gateway in subnet config: %s',
                                  gw_ip)
                if ":" in gw_ip:
                    route_d = (routes['6'] if len(routes['6']) else
                               routes['ip_6_route_show'])
                else:
                    route_d = (routes['4'] if len(routes['4']) else
                               routes['ip_route_show'])

                found_gws = [line for line in route_d.split('\n')
                             if __has_gw_route(line, gw_ip)]
                self.logger.debug('found gateways in guest output:\n%s',
                                  found_gws)

                print('found_gws: %s\nexpected: %s' % (found_gws,
                                                       configured_gws))
                # we only need to check that we found at least one as we walk
                self.assertGreater(len(found_gws), 0)
                for fgw in found_gws:
                    fgw_split = fgw.split()
                    # in ip_route_show/ip_6_route_show we end up with
                    # lines which have one or more 'via' sections.
                    # in the ipv6 case, we see many nexthops with
                    # fe80::2, which we want to ignore. This loop
                    # lets us find the actual gateway value by
                    # walking until we find a non fe80::2 gateway
                    if 'via' in fgw_split:
                        for el_idx, elem in enumerate(fgw_split):
                            if elem == 'via':
                                if fgw_split[el_idx + 1] != "fe80::2":
                                    gw_idx = el_idx + 1
                                    break
                    else:
                        gw_idx = 1

                    self.logger.debug('configured gw:%s found gw:%s',
                                      gw_ip, fgw_split[gw_idx])
                    self.assertEqual(gw_ip, fgw_split[gw_idx])


class TestNetworkBasicAbs(TestNetworkBaseTestsAbs):
    """ Basic network testing with ipv4
    """
    conf_file = "examples/tests/basic_network.yaml"


class CentosTestNetworkBasicAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/centos_basic.yaml"

    def test_etc_network_interfaces(self):
        pass

    def test_etc_resolvconf(self):
        pass


class XenialTestNetworkBasic(relbase.xenial, TestNetworkBasicAbs):
    __test__ = True


class BionicTestNetworkBasic(relbase.bionic, TestNetworkBasicAbs):
    __test__ = True


class FocalTestNetworkBasic(relbase.focal, TestNetworkBasicAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestNetworkBasic(relbase.jammy, TestNetworkBasicAbs):
    skip = True  # XXX Broken for now
    __test__ = True


class Centos70TestNetworkBasic(centos_relbase.centos70_xenial,
                               CentosTestNetworkBasicAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
