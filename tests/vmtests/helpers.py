#! /usr/bin/env python
#   Copyright (C) 2015 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.
import os
import subprocess
import signal
import threading
from unittest import TestLoader


class Command(object):
    """
    based on https://gist.github.com/kirpit/1306188
    """
    command = None
    process = None
    status = None
    exception = None
    returncode = -1

    def __init__(self, command, signal=signal.SIGTERM):
        self.command = command
        self.signal = signal

    def run(self, timeout=None, **kwargs):
        """ Run a command then return: (status, output, error). """
        def target(**kwargs):
            try:
                self.process = subprocess.Popen(self.command, **kwargs)
                self.process.communicate()
                self.status = self.process.returncode
            except subprocess.CalledProcessError as e:
                self.exception = e
                self.returncode = e.returncode
            except Exception as e:
                self.exception = e
        # thread
        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.process.send_signal(self.signal)
            thread.join()
            self.exception = TimeoutExpired(
                cmd=self.command, timeout=timeout)

        if self.exception:
            raise self.exception

        if self.status != 0:
            raise subprocess.CalledProcessError(cmd=self.command,
                                                returncode=self.status)

        return 0

try:
    TimeoutExpired = subprocess.TimeoutExpired
except AttributeError:
    class TimeoutExpired(subprocess.CalledProcessError):
        def __init__(self, *args, **kwargs):
            if not kwargs:
                kwargs = {}
            if len(args):
                # if args are given, convert them to kwargs.
                # *args is a tuple, convert it to a list to use pop
                args = list(args)
                for arg in ('cmd', 'output', 'timeout'):
                    kwargs[arg] = args.pop(0)
                    if not len(args):
                        break

            returncode = -1
            if 'timeout' in kwargs:
                self.timeout = kwargs.pop('timeout')
            else:
                self.timeout = -1

            # do not use super here as it confuses pylint
            # https://github.com/PyCQA/pylint/issues/773
            subprocess.CalledProcessError.__init__(self, returncode, **kwargs)


def check_call(cmd, signal=signal.SIGTERM, **kwargs):
    # provide a 'check_call' like interface, but kill with a nice signal
    return Command(cmd, signal).run(**kwargs)


def find_releases():
    """Return a sorted list of releases defined in test cases."""
    # Use the TestLoader to load all tests cases defined within
    # tests/vmtests/ and figure out which releases they are testing.
    loader = TestLoader()
    # dir with the vmtest modules (i.e. tests/vmtests/)
    tests_dir = os.path.dirname(__file__)
    # The root_dir for the curtin branch. (i.e. curtin/)
    root_dir = os.path.split(os.path.split(tests_dir)[0])[0]
    # Find all test modules defined in curtin/tests/vmtests/
    module_test_suites = loader.discover(tests_dir, top_level_dir=root_dir)
    releases = set()
    for mts in module_test_suites:
        for class_test_suite in mts:
            for test_case in class_test_suite:
                if getattr(test_case, 'release', ''):
                    releases.add(getattr(test_case, 'release'))
    return sorted(releases)


def _parse_ifconfig_xenial(ifconfig_out):
    """Parse ifconfig output from xenial or earlier and return a dictionary.
    given content like below, return:
    {'eth0': {'address': '10.8.1.78', 'broadcast': '10.8.1.255',
              'inet6': [{'address': 'fe80::216:3eff:fe63:c05d',
                         'prefixlen': '64', 'scope': 'Link'},
                        {'address': 'fdec:2922:2f07:0:216:3eff:fe63:c05d',
                         'prefixlen': '64', 'scope': 'Global'}],
              'interface': 'eth0', 'link_encap': 'Ethernet',
              'mac_address': '00:16:3e:63:c0:5d', 'mtu': 1500,
              'multicast': True, 'netmask': '255.255.255.0',
              'running': True, 'up': True}}

    eth0  Link encap:Ethernet  HWaddr 00:16:3e:63:c0:5d
          inet addr:10.8.1.78  Bcast:10.8.1.255  Mask:255.255.255.0
          inet6 addr: fe80::216:3eff:fe63:c05d/64 Scope:Link
          inet6 addr: fdec:2922:2f07:0:216:3eff:fe63:c05d/64 Scope:Global
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1
          RX packets:21503 errors:0 dropped:0 overruns:0 frame:0
          TX packets:11346 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:1000
          RX bytes:31556357 (31.5 MB)  TX bytes:870943 (870.9 KB)
    """
    ifaces = {}
    combined_fields = {'addr': 'address', 'Bcast': 'broadcast',
                       'Mask': 'netmask', 'MTU': 'mtu',
                       'encap': 'link_encap'}
    boolmap = {'RUNNING': 'running', 'UP': 'up', 'MULTICAST': 'multicast'}

    for line in ifconfig_out.splitlines():
        if not line:
            continue
        if not line.startswith(" "):
            cur_iface = line.split()[0].rstrip(":")
            cur_data = {'inet6': [], 'interface': cur_iface}
            for t in boolmap.values():
                cur_data[t] = False
            ifaces[cur_iface] = cur_data

        toks = line.split()

        if toks[0] == "inet6":
            cidr = toks[2]
            address, prefixlen = cidr.split("/")
            scope = toks[3].split(":")[1]
            cur_ipv6 = {'address': address, 'scope': scope,
                        'prefixlen': prefixlen}
            cur_data['inet6'].append(cur_ipv6)
            continue

        for i in range(0, len(toks)):
            cur_tok = toks[i]
            try:
                next_tok = toks[i+1]
            except IndexError:
                next_tok = None

            if cur_tok == "HWaddr":
                cur_data['mac_address'] = next_tok
            elif ":" in cur_tok:
                key, _colon, val = cur_tok.partition(":")
                if key in combined_fields:
                    cur_data[combined_fields[key]] = val
            elif cur_tok in boolmap:
                cur_data[boolmap[cur_tok]] = True

        if 'mtu' in cur_data:
            cur_data['mtu'] = int(cur_data['mtu'])

    return ifaces


def _parse_ifconfig_yakkety(ifconfig_out):
    """Parse ifconfig output from yakkety or later(?) and return a dictionary.

    given ifconfig output like below, return:
    {'ens2': {'address': '10.5.0.78',
              'broadcast': '10.5.255.255',
              'broadcast_flag': True,
              'inet6': [{'address': 'fe80::f816:3eff:fe05:9673',
                         'prefixlen': '64', 'scopeid': '0x20<link>'},
                        {'address': 'fe80::f816:3eff:fe05:9673',
                         'prefixlen': '64', 'scopeid': '0x20<link>'}],
              'interface': 'ens2', 'link_encap': 'Ethernet',
              'mac_address': 'fa:16:3e:05:96:73', 'mtu': 1500,
              'multicast': True, 'netmask': '255.255.0.0',
              'running': True, 'up': True}}

    ens2: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
            inet 10.5.0.78  netmask 255.255.0.0  broadcast 10.5.255.255
            inet6 fe80::f816:3eff:fe05:9673  prefixlen 64  scopeid 0x20<link>
            inet6 fe80::f816:3eff:fe05:9673  prefixlen 64  scopeid 0x20<link>
            ether fa:16:3e:05:96:73  txqueuelen 1000  (Ethernet)
            RX packets 33196  bytes 48916947 (48.9 MB)
            RX errors 0  dropped 0  overruns 0  frame 0
            TX packets 5458  bytes 411486 (411.4 KB)
            TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
    """
    fmap = {'mtu': 'mtu', 'inet': 'address',
            'netmask': 'netmask', 'broadcast': 'broadcast',
            'ether': 'mac_address'}
    boolmap = {'RUNNING': 'running', 'UP': 'up', 'MULTICAST': 'multicast',
               'BROADCAST': 'broadcast_flag'}

    ifaces = {}
    for line in ifconfig_out.splitlines():
        if not line:
            continue
        if not line.startswith(" "):
            cur_iface = line.split()[0].rstrip(":")
            cur_data = {'inet6': [], 'interface': cur_iface}
            for t in boolmap.values():
                cur_data[t] = False
            ifaces[cur_iface] = cur_data

        toks = line.split()
        if toks[0] == "inet6":
            cur_ipv6 = {'address': toks[1]}
            cur_data['inet6'].append(cur_ipv6)

        for i in range(0, len(toks)):
            cur_tok = toks[i]
            try:
                next_tok = toks[i+1]
            except IndexError:
                next_tok = None
            if cur_tok in fmap:
                cur_data[fmap[cur_tok]] = next_tok
            elif cur_tok in ('prefixlen', 'scopeid'):
                cur_ipv6[cur_tok] = next_tok
                cur_data['inet6'].append
            elif cur_tok.startswith("flags="):
                # flags=4163<UP,BROADCAST,RUNNING,MULTICAST>
                flags = cur_tok[cur_tok.find("<") + 1:
                                cur_tok.rfind(">")].split(",")
                for flag in flags:
                    if flag in boolmap:
                        cur_data[boolmap[flag]] = True
            elif cur_tok == "(Ethernet)":
                cur_data['link_encap'] = 'Ethernet'

        if 'mtu' in cur_data:
            cur_data['mtu'] = int(cur_data['mtu'])

    return ifaces


def ifconfig_to_dict(ifconfig_a):
    # if the first token of the first line ends in a ':' then assume yakkety
    # parse ifconfig output and return a dictionary.
    #
    # return a dictionary of network information like:
    #  {'ens2': {'address': '10.5.0.78', 'broadcast': '10.5.255.255',
    #         'broadcast_flag': True,
    #         'inet6': [{'address': 'fe80::f816:3eff:fe05:9673',
    #                    'prefixlen': '64', 'scopeid': '0x20<link>'},
    #                   {'address': 'fe80::f816:3eff:fe05:9673',
    #                    'prefixlen': '64', 'scopeid': '0x20<link>'}],
    #         'interface': 'ens2', 'link_encap': 'Ethernet',
    #         'mac_address': 'fa:16:3e:05:96:73', 'mtu': 1500,
    #         'multicast': True, 'netmask': '255.255.0.0',
    #         'running': True, 'up': True}}
    line = ifconfig_a.lstrip().splitlines()[0]
    if line.split()[0].endswith(":"):
        return _parse_ifconfig_yakkety(ifconfig_a)
    else:
        return _parse_ifconfig_xenial(ifconfig_a)
