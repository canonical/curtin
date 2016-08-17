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

from .. import log
import curtin.config as config
import curtin.net as net
import curtin.util as util
from . import populate_one_subcmd


LOG = log.LOG


def apply_net(target, network_state=None, network_config=None,
              postup_alias=None):
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

    net.render_network_state(target=target, network_state=ns,
                             postup_alias=postup_alias)


def detect_postup_alias(target):
    try:
        LOG.info('Checking target for version of ifupdown package')
        # check in-target version
        pkg_ver = util.get_package_version('ifupdown',
                                           target=target)
        if pkg_ver is None:
            raise Exception('Failed to get package version')

        LOG.debug("get_package_version:\n%s", pkg_ver)
        LOG.debug("ifupdown version is %s (major=%s minor=%s micro=%s)",
                  pkg_ver['semantic_version'], pkg_ver['major'],
                  pkg_ver['minor'], pkg_ver['micro'])
        # ifupdown versions < 0.8.6 need ifup alias to prevent 120 second
        # timeout, i.e. 0.7.47 in Trusty uses them.
        if pkg_ver['semantic_version'] < 806:
            return True
    except Exception:
        LOG.warn("Failed reading ifupdown pkg version (using defaults)")

    return False


def apply_net_main(args):
    #  curtin apply_net [--net-state=/config/netstate.yml] [--target=/]
    #                   [--net-config=/config/maas_net.yml]
    state = util.load_command_environment()

    log.basicConfig(stream=args.log_file, verbosity=1)

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

    postup_alias = False
    if args.postup_alias is not None:
        postup_alias = config.value_as_boolean(args.postup_alias)
    else:
        postup_alias = detect_postup_alias(target=state['target'])
    LOG.info('Applying network configuration')
    try:
        apply_net(target=state['target'],
                  network_state=state['network_state'],
                  network_config=state['network_config'],
                  postup_alias=postup_alias)
    except Exception:
        LOG.exception('failed to apply network config')

    LOG.info('Applied network configuration successfully')
    sys.exit(0)


CMD_ARGUMENTS = (
    ((('-s', '--net-state'),
     {'help': ('file to read containing network state. '
               'defaults to env["OUTPUT_NETWORK_STATE"]'),
      'metavar': 'NETSTATE', 'action': 'store',
      'default': os.environ.get('OUTPUT_NETWORK_STATE')}),
     (('-t', '--target'),
      {'help': ('target filesystem root to configure networking to. '
                'default is env["TARGET_MOUNT_POINT"]'),
       'metavar': 'TARGET', 'action': 'store',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('-a', '--postup-alias'),
      {'help': ('target filesystem check for postup alias config. '
                'default is not set'),
       'metavar': 'POST', 'action': 'store',
       'default': None}),
     (('-c', '--net-config'),
      {'help': ('file to read containing curtin network config.'
                'defaults to env["OUTPUT_NETWORK_CONFIG"]'),
       'metavar': 'NETCONFIG', 'action': 'store',
       'default': os.environ.get('OUTPUT_NETWORK_CONFIG')})))


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, apply_net_main)

# vi: ts=4 expandtab syntax=python
