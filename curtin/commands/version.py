# This file is part of curtin. See LICENSE file for copyright and license info.

import sys
from .. import version
from . import populate_one_subcmd


def version_main(args):
    sys.stdout.write(version.version_string() + "\n")
    sys.exit(0)


CMD_ARGUMENTS = (
    (tuple())
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, version_main)

# vi: ts=4 expandtab syntax=python
