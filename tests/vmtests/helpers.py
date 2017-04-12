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


def find_releases_by_distro():
    """
    Returns a dictionary of distros and the distro releases that will be tested

    distros:
        ubuntu:
            releases: []
            krels: []
        centos:
            releases: []
            krels: []
    """
    # Use the TestLoder to load all test cases defined within tests/vmtests/
    # and figure out what distros and releases they are testing. Any tests
    # which are disabled will be excluded.
    loader = TestLoader()
    # dir with the vmtest modules (i.e. tests/vmtests/)
    tests_dir = os.path.dirname(__file__)
    # The root_dir for the curtin branch. (i.e. curtin/)
    root_dir = os.path.split(os.path.split(tests_dir)[0])[0]
    # Find all test modules defined in curtin/tests/vmtests/
    module_test_suites = loader.discover(tests_dir, top_level_dir=root_dir)
    # find all distros and releases tested for each distro
    releases = []
    krels = []
    rel_by_dist = {}
    for mts in module_test_suites:
        for class_test_suite in mts:
            for test_case in class_test_suite:
                # skip disabled tests
                if not getattr(test_case, '__test__', False):
                    continue
                for (dist, rel, krel) in (
                        (getattr(test_case, a, None) for a in attrs)
                        for attrs in (('distro', 'release', 'krel'),
                                      ('target_distro', 'target_release',
                                       'krel'))):

                    if dist and rel:
                        distro = rel_by_dist.get(dist, {'releases': [],
                                                        'krels': []})
                        releases = distro.get('releases')
                        krels = distro.get('krels')
                        if rel not in releases:
                            releases.append(rel)
                        if krel and krel not in krels:
                            krels.append(krel)
                        rel_by_dist.update({dist: distro})

    return rel_by_dist


def _parse_ip_a(ip_a):
    """
    2: interface0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1480 qdisc pfifo_fast\
        state UP group default qlen 1000
        link/ether 52:54:00:12:34:00 brd ff:ff:ff:ff:ff:ff
        inet 192.168.1.2/24 brd 192.168.1.255 scope global interface0
            valid_lft forever preferred_lft forever
        inet6 2001:4800:78ff:1b:be76:4eff:fe06:1000/64 scope global
            valid_lft forever preferred_lft forever
        inet6 fe80::5054:ff:fe12:3400/64 scope link
        valid_lft forever preferred_lft forever
    """
    ifaces = {}
    combined_fields = {
        'brd': 'broadcast',
        'link/ether': 'mac_address',
    }
    interface_fields = [
        'group',
        'master',
        'mtu',
        'qdisc',
        'qlen',
        'state',
    ]
    inet_fields = [
        'valid_lft',
        'preferred_left'
    ]
    boolmap = {
        'BROADCAST': 'broadcast',
        'LOOPBACK': 'loopback',
        'LOWER_UP': 'lower_up',
        'MULTICAST': 'multicast',
        'RUNNING': 'running',
        'UP': 'up',
    }

    for line in ip_a.splitlines():
        if not line:
            continue

        toks = line.split()
        if not line.startswith("    "):
            cur_iface = line.split()[1].rstrip(":")
            cur_data = {
                'inet4': [],
                'inet6': [],
                'interface': cur_iface
            }
            # vlan's get a fancy name <iface name>@<vlan_link>
            if '@' in cur_iface:
                cur_iface, vlan_link = cur_iface.split("@")
                cur_data.update({'interface': cur_iface,
                                 'vlan_link': vlan_link})
            for t in boolmap.values():
                # <BROADCAST,MULTICAST,UP,LOWER_UP>
                cur_data[t] = t.upper() in line[2]
            ifaces[cur_iface] = cur_data

        for i in range(0, len(toks)):
            cur_tok = toks[i]
            try:
                next_tok = toks[i+1]
            except IndexError:
                next_tok = None

            # parse link/ether, brd
            if cur_tok in combined_fields.keys():
                cur_data[combined_fields[cur_tok]] = next_tok
            # mtu an other interface line key/value pairs
            elif cur_tok in interface_fields:
                cur_data[cur_tok] = next_tok
            elif cur_tok.startswith("inet"):
                cidr = toks[1]
                address = cidr
                prefixlen = None
                if '/' in cidr:
                    address, prefixlen = cidr.split("/")
                cur_ip = {
                    'address': address,
                    'prefixlen': prefixlen,
                }
                if ":" in address:
                    cur_ipv6 = cur_ip.copy()
                    cur_ipv6.update({'scope': toks[3]})
                    cur_data['inet6'].append(cur_ipv6)
                else:
                    cur_ipv4 = cur_ip.copy()
                    if len(toks) > 5:
                        cur_ipv4.update({'scope': toks[5]})
                    else:
                        cur_ipv4.update({'scope': toks[3]})
                    cur_data['inet4'].append(cur_ipv4)

                continue
            elif cur_tok in inet_fields:
                if ":" in address:
                    cur_ipv6[cur_tok] = next_tok
                else:
                    cur_ipv4[cur_tok] = next_tok
                continue

    return ifaces


def ip_a_to_dict(ip_a):
    # return a dictionary of network information like:
    # {'interface0': {'broadcast': '10.0.2.255',
    #                 'group': 'default',
    #                 'inet4': [{'address': '10.0.2.15',
    #                            'preferred_lft': 'forever',
    #                            'prefixlen': '24',
    #                            'scope': 'global',
    #                            'valid_lft': 'forever'}],
    #                 'inet6': [{'address': 'fe80::5054:ff:fe12:3400',
    #                            'preferred_lft': 'forever',
    #                            'prefixlen': '64',
    #                            'scope': 'link',
    #                            'valid_lft': 'forever'}],
    #                 'interface': 'interface0',
    #                 'loopback': False,
    #                 'lower_up': False,
    #                 'mac_address': '52:54:00:12:34:00',
    #                 'mtu': '1500',
    #                 'multicast': False,
    #                 'qdisc': 'pfifo_fast',
    #                 'qlen': '1000',
    #                 'running': False,
    #                 'state': 'UP',
    #                 'up': False},
    # from iproute2 `ip a` command output
    return _parse_ip_a(ip_a)
