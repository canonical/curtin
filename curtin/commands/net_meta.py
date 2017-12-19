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
import curtin.util as util
import curtin.config as config

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
        raise NotImplementedError("netboot alias not implemented")
    else:
        raise ValueError("'%s' is not an alias: %s", alias, DEVNAME_ALIASES)


def interfaces_basic_dhcp(devices):
    content = '\n'.join(
        [("# This file describes the network interfaces available on "
         "your system"),
         "# and how to activate them. For more information see interfaces(5).",
         "",
         "# The loopback network interface",
         "auto lo",
         "iface lo inet loopback",
         ])

    for d in devices:
        content += '\n'.join(("", "", "auto %s" % d,
                              "iface %s inet dhcp" % d,))
    content += "\n"

    return content


def interfaces_custom(args):
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    network_config = cfg.get('network', [])
    if not network_config:
        raise Exception("network configuration is required by mode '%s' "
                        "but not provided in the config file" % 'custom')

    return config.dump_config({'network': network_config})


def net_meta(args):
    #    curtin net-meta --devices connected dhcp
    #    curtin net-meta --devices configured dhcp
    #    curtin net-meta --devices netboot dhcp
    #    curtin net-meta --devices connected custom

    # if network-config hook exists in target,
    # we do not run the builtin
    if util.run_hook_if_exists(args.target, 'network-config'):
        sys.exit(0)

    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)
    if cfg.get("network") is not None:
        args.mode = "custom"

    eni = "etc/network/interfaces"
    if args.mode == "auto":
        if not args.devices:
            args.devices = ["connected"]

        t_eni = None
        if args.target:
            t_eni = os.path.sep.join((args.target, eni,))
            if not os.path.isfile(t_eni):
                t_eni = None

        if t_eni:
            args.mode = "copy"
        else:
            args.mode = "dhcp"

    devices = []
    if args.devices:
        for dev in args.devices:
            if dev in DEVNAME_ALIASES:
                devices += resolve_alias(dev)
            else:
                devices.append(dev)

    if args.mode == "copy":
        if not args.target:
            raise argparse.ArgumentTypeError("mode 'copy' requires --target")

        t_eni = os.path.sep.join((args.target, "etc/network/interfaces",))
        with open(t_eni, "r") as fp:
            content = fp.read()

    elif args.mode == "dhcp":
        content = interfaces_basic_dhcp(devices)
    elif args.mode == 'custom':
        content = interfaces_custom(args)
        # if we have a config, write it out to OUTPUT_NETWORK_CONFIG
        output_network_config = os.environ.get("OUTPUT_NETWORK_CONFIG", "")
        if output_network_config:
            with open(output_network_config, "w") as fp:
                fp.write(content)

    if args.output == "-":
        sys.stdout.write(content)
    else:
        with open(args.output, "w") as fp:
            fp.write(content)

    sys.exit(0)


CMD_ARGUMENTS = (
    ((('-D', '--devices'),
      {'help': 'which devices to operate on', 'action': 'append',
       'metavar': 'DEVICE', 'type': network_device}),
     (('-o', '--output'),
      {'help': 'file to write to. defaults to env["OUTPUT_INTERFACES"] or "-"',
       'metavar': 'IFILE', 'action': 'store',
       'default': os.environ.get('OUTPUT_INTERFACES', "-")}),
     (('-t', '--target'),
      {'help': 'operate on target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     ('mode', {'help': 'meta-mode to use',
               'choices': ['dhcp', 'copy', 'auto', 'custom']})
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, net_meta)

# vi: ts=4 expandtab syntax=python
