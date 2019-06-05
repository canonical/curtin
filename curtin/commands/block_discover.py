# This file is part of curtin. See LICENSE file for copyright and license info.

import json
from . import populate_one_subcmd
from curtin import block


def block_discover_main(args):
    """probe for existing devices and emit Curtin storage config output."""

    print(json.dumps(block.discover(), indent=2, sort_keys=True))


CMD_ARGUMENTS = ()


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_discover_main)

# vi: ts=4 expandtab syntax=python
