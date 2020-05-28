# This file is part of curtin. See LICENSE file for copyright and license info.

import json
from . import populate_one_subcmd
from curtin import block


def block_discover_main(args):
    """probe for existing devices and emit Curtin storage config output."""

    if args.probe_data:
        probe_data = block._discover_get_probert_data()
    else:
        probe_data = block.discover()

    print(json.dumps(probe_data, indent=2, sort_keys=True))


CMD_ARGUMENTS = (
    (('-p', '--probe-data'),
     {'help': 'dump probert probe-data to stdout emitting storage config.',
      'action': 'store_true', 'default': False}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_discover_main)

# vi: ts=4 expandtab syntax=python
