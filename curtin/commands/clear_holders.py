# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin import block
from . import populate_one_subcmd


def clear_holders_main(args):
    """
    wrapper for clear_holders accepting cli args
    """
    if (not all(block.is_block_device(device) for device in args.devices) or
            len(args.devices) == 0):
        raise ValueError('invalid devices specified')
    block.clear_holders.start_clear_holders_deps()
    block.clear_holders.clear_holders(args.devices, try_preserve=args.preserve)
    if args.preserve:
        print('ran clear_holders attempting to preserve data. however, '
              'hotplug support for some devices may cause holders to restart ')
    block.clear_holders.assert_clear(args.devices)


CMD_ARGUMENTS = (
    (('devices',
      {'help': 'devices to free', 'default': [], 'nargs': '+'}),
     (('-p', '--preserve'),
      {'help': 'try to shut down holders without erasing anything',
       'default': False, 'action': 'store_true'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, clear_holders_main)

# vi: ts=4 expandtab syntax=python
