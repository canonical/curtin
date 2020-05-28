# This file is part of curtin. See LICENSE file for copyright and license info.

from .block_meta import (
    extract_storage_ordered_dict,
    get_device_paths_from_storage_config,
)
from curtin import block
from curtin.log import LOG
from .import populate_one_subcmd


def clear_holders_main(args):
    """
    wrapper for clear_holders accepting cli args
    """
    cfg = {}
    if args.config:
        cfg = args.config

    # run clear holders on potential devices
    devices = args.devices
    if not devices:
        if 'storage' in cfg:
            devices = get_device_paths_from_storage_config(
                extract_storage_ordered_dict(cfg))
        if len(devices) == 0:
            devices = cfg.get('block-meta', {}).get('devices', [])

    if (not all(block.is_block_device(device) for device in devices) or
            len(devices) == 0):
        raise ValueError('invalid devices specified')

    block.clear_holders.start_clear_holders_deps()
    if args.shutdown_plan:
        # get current holders and plan how to shut them down
        holder_trees = [block.clear_holders.gen_holders_tree(path)
                        for path in devices]
        LOG.info('Current device storage tree:\n%s',
                 '\n'.join(block.clear_holders.format_holders_tree(tree)
                           for tree in holder_trees))
        ordered_devs = (
            block.clear_holders.plan_shutdown_holder_trees(holder_trees))
        LOG.info('Shutdown Plan:\n%s', "\n".join(map(str, ordered_devs)))

    else:
        block.clear_holders.clear_holders(devices, try_preserve=args.preserve)
        if args.preserve:
            print('ran clear_holders attempting to preserve data. however, '
                  'hotplug support for some devices may cause holders to '
                  'restart ')
        block.clear_holders.assert_clear(devices)


CMD_ARGUMENTS = (
    (('devices',
      {'help': 'devices to free', 'default': [], 'nargs': '*'}),
     (('-P', '--shutdown-plan'),
      {'help': 'Print the clear-holder shutdown plan only',
       'default': False, 'action': 'store_true'}),
     (('-p', '--preserve'),
      {'help': 'try to shut down holders without erasing anything',
       'default': False, 'action': 'store_true'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, clear_holders_main)

# vi: ts=4 expandtab syntax=python
