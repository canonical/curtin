#   Copyright (C) 2013 Canonical Ltd.
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

import argparse
import os
import sys

from curtin import net

from . import populate_one_subcmd

DEVNAME_ALIASES = ['connected', 'configured', 'netboot']


def network_device(value):
    if value in DEVNAME_ALIASES:
        return value
    if (value.startswith('eth') or
            (value.startswith('en') and len(value) == 3)):
        return value
    raise argparse.ArgumentTypeError("%s does not look like a netdev name")


def resolve_alias(alias):
    if alias == "connected":
        alldevs = net.get_devicelist()
        return [d for d in alldevs if
                net.is_physical(d) and net.is_up(d)]
    elif alias == "configured":
        alldevs = net.get_devicelist()
        return [d for d in alldevs if
                net.is_physical(d) and net.is_up(d) and net.is_connected(d)]
    elif alias == "netboot":
        # should read /proc/cmdline here for BOOTIF
        raise NotImplemented("netboot alias not implemented")
    else:
        raise ValueError("'%s' is not an alias: %s", alias, DEVNAME_ALIASES)


def net_meta(args):
    #    curtin net-meta --devices connected dhcp
    #    curtin net-meta --devices configured dhcp
    #    curtin net-meta --devices netboot dhcp

    devices = []
    for dev in args.devices:
        if dev in DEVNAME_ALIASES:
            devices += resolve_alias(dev)
        else:
            devices.append(dev)

    content = '\n'.join(
        [("# This file describes the network interfaces available on "
         "your system"),
         "# and how to activate them. For more information see interfaces(5).",
         "",
         "# The loopback network interface"
         "auto lo",
         "iface lo inet loopback",
         ])

    for d in devices:
        content += '\n'.join(("", "", "auth %s" % d,
                              "iface %s inet dhcp" % d,))

    if args.output == "-":
        sys.stdout.write(content)
    else:
        with open(args.output, "w") as fp:
            fp.write(content)


CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'type': network_device}),
     (('-o', '--output'),
      {'help': 'file to write to. defaults to env["INTERFACES"] or "-"',
       'metavar': 'IFILE', 'action': 'store',
       'default': os.environ.get('INTERFACES', "-")}),
     ('mode', {'help': 'meta-mode to use', 'choices': ['dhcp']})
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, net_meta)

# vi: ts=4 expandtab syntax=python
