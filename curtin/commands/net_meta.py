# This file is part of curtin. See LICENSE file for copyright and license info.

import argparse
import os
import sys

from curtin import net
from curtin.log import LOG
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


def interfaces_basic_dhcp(devices, macs=None):
    # return network configuration that says to dhcp on provided devices
    if macs is None:
        macs = {}
        for dev in devices:
            macs[dev] = net.get_interface_mac(dev)

    config = []
    for dev in devices:
        config.append({
            'type': 'physical', 'name': dev, 'mac_address': macs.get(dev),
            'subnets': [{'type': 'dhcp4'}]})

    return {'network': {'version': 1, 'config': config}}


def interfaces_custom(args):
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    network_config = cfg.get('network', [])
    if not network_config:
        raise Exception("network configuration is required by mode '%s' "
                        "but not provided in the config file" % 'custom')

    return {'network': network_config}


def net_meta(args):
    #    curtin net-meta --devices connected dhcp
    #    curtin net-meta --devices configured dhcp
    #    curtin net-meta --devices netboot dhcp
    #    curtin net-meta --devices connected custom

    # if network-config hook exists in target,
    # we do not run the builtin
    if util.run_hook_if_exists(args.target, 'network-config'):
        sys.exit(0)

    if args.mode == "disabled":
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

    LOG.debug("net-meta mode is '%s'.  devices=%s", args.mode, devices)

    output_network_config = os.environ.get("OUTPUT_NETWORK_CONFIG", "")
    if args.mode == "copy":
        if not args.target:
            raise argparse.ArgumentTypeError("mode 'copy' requires --target")

        t_eni = os.path.sep.join((args.target, "etc/network/interfaces",))
        with open(t_eni, "r") as fp:
            content = fp.read()
        LOG.warn("net-meta mode is 'copy', static network interfaces files"
                 "can be brittle.  Copied interfaces: %s", content)
        target = args.output

    elif args.mode == "dhcp":
        target = output_network_config
        content = config.dump_config(interfaces_basic_dhcp(devices))

    elif args.mode == 'custom':
        target = output_network_config
        content = config.dump_config(interfaces_custom(args))

    else:
        raise Exception("Unexpected network config mode '%s'." % args.mode)

    if not target:
        raise Exception(
            "No target given for mode = '%s'. Nowhere to write content: %s" %
            (args.mode, content))

    LOG.debug("writing to file %s with network config: %s", target, content)
    if target == "-":
        sys.stdout.write(content)
    else:
        with open(target, "w") as fp:
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
               'choices': ['dhcp', 'copy', 'auto', 'custom', 'disabled']})
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, net_meta)

# vi: ts=4 expandtab syntax=python
