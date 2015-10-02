#   Copyright (C) 2015 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
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
import sys

import curtin.net as net
import curtin.util as util
from . import populate_one_subcmd


def apply_net(target, network_state=None, network_config=None):
    if network_state is None and network_config is None:
        msg = "Must provide at least config or state"
        sys.stderr.write(msg + "\n")
        raise Exception(msg)

    if target is None:
        msg = "Must provide target"
        sys.stderr.write(msg + "\n")
        raise Exception(msg)

    if network_state:
        ns = net.network_state.from_state_file(network_state)
    elif network_config:
        ns = net.parse_net_config(network_config)

    net.render_network_state(target=target, network_state=ns)


def apply_net_main(args):
    #  curtin apply_net [--net-state=/config/netstate.yml] [--target=/]
    #                   [--net-config=/config/maas_net.yml]
    state = util.load_command_environment()

    if args.target is not None:
        state['target'] = args.target

    if args.net_state is not None:
        state['network_state'] = args.net_state

    if args.net_config is not None:
        state['network_config'] = args.net_config

    if state['target'] is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    if not state['network_config'] and not state['network_state']:
        sys.stderr.write("Must provide at least config or state\n")
        sys.exit(2)

    apply_net(target=state['target'],
              network_state=state['network_state'],
              network_config=state['network_config'])

    sys.exit(0)


CMD_ARGUMENTS = (
    ((('-s', '--net-state'),
     {'help': ('file to read containing network state. '
               'defaults to env["OUTPUT_NETWORK_STATE"]'),
      'metavar': 'NETSTATE', 'action': 'store',
      'default': os.environ.get('OUTPUT_NETWORK_STATE')}),
     (('-t', '--target'),
      {'help': ('target filesystem root to add swap file to. '
                'default is env["TARGET_MOUNT_POINT"]'),
       'metavar': 'TARGET', 'action': 'store',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('-c', '--net-config'),
      {'help': ('file to read containing curtin network config.'
                'defaults to env["OUTPUT_NETWORK_CONFIG"]'),
       'metavar': 'NETCONFIG', 'action': 'store',
       'default': os.environ.get('OUTPUT_NETWORK_CONFIG')})))


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, apply_net_main)

# vi: ts=4 expandtab syntax=python
