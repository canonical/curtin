# This file is part of curtin. See LICENSE file for copyright and license info.
"""List the supported feature names to stdout."""

import sys
from .. import FEATURES
from . import populate_one_subcmd

CMD_ARGUMENTS = ((tuple()))


def features_main(args):
    sys.stdout.write("\n".join(sorted(FEATURES)) + "\n")
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, features_main)
    parser.description = __doc__

# vi: ts=4 expandtab syntax=python
