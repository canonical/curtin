# This file is part of curtin. See LICENSE file for copyright and license info.
"""List the supported feature names to stdout."""

import sys
from .. import storage_config
from . import populate_one_subcmd

CMD_ARGUMENTS = (
    (('-s', '--storage'),
     {'help': 'apply storage config validator to config file',
      'action': 'store_true', 'required': True}),
    (('-c', '--config'),
     {'help': 'path to configuration file to validate.',
      'required': True, 'metavar': 'FILE', 'action': 'store',
      'dest': 'schema_cfg'}),
)


def schema_validate_storage(confpath):
    try:
        storage_config.load_and_validate(confpath)
    except Exception as e:
        sys.stderr.write('  ' + str(e) + '\n')
        return 1

    sys.stdout.write('  Valid storage config: %s\n' % confpath)
    return 0


def schema_validate_main(args):
    errors = []
    if args.storage:
        sys.stdout.write(
            'Validating storage config in %s:\n' % args.schema_cfg)
        if schema_validate_storage(args.schema_cfg) != 0:
            errors.append('storage')

    return len(errors)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, schema_validate_main)
    parser.description = __doc__

# vi: ts=4 expandtab syntax=python
