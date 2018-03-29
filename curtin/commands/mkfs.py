# This file is part of curtin. See LICENSE file for copyright and license info.

from . import populate_one_subcmd
from curtin.block.mkfs import mkfs as run_mkfs
from curtin.block.mkfs import valid_fstypes

import sys

CMD_ARGUMENTS = (
    (('devices',
      {'help': 'create filesystem on the target volume(s) or storage config \
                item(s)',
       'metavar': 'DEVICE', 'action': 'store', 'nargs': '+'}),
     (('-f', '--fstype'),
      {'help': 'filesystem type to use. default is ext4',
       'choices': sorted(valid_fstypes()),
       'default': 'ext4', 'action': 'store'}),
     (('-l', '--label'),
      {'help': 'label to use for filesystem', 'action': 'store'}),
     (('-u', '--uuid'),
      {'help': 'uuid to use for filesystem', 'action': 'store'}),
     (('-s', '--strict'),
      {'help': 'exit if mkfs cannot do exactly what is specified',
       'action': 'store_true', 'default': False}),
     (('-F', '--force'),
      {'help': 'continue if some data already exists on device',
       'action': 'store_true', 'default': False})
     )
)


def mkfs(args):
    for device in args.devices:
        uuid = run_mkfs(device, args.fstype, strict=args.strict,
                        uuid=args.uuid, label=args.label,
                        force=args.force)

        print("Created '%s' filesystem in '%s' with uuid '%s' and label '%s'" %
              (args.fstype, device, uuid, args.label))

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, mkfs)

# vi: ts=4 expandtab syntax=python
