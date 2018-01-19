# This file is part of curtin. See LICENSE file for copyright and license info.

from . import populate_one_subcmd
from curtin.block import iscsi


def block_attach_iscsi_main(args):
    iscsi.ensure_disk_connected(args.disk, args.save_config)

    return 0


CMD_ARGUMENTS = (
    ('disk',
     {'help': 'RFC4173 specification of iSCSI disk to attach'}),
    ('--save-config',
     {'help': 'save access configuration to local filesystem',
      'default': False, 'action': 'store_true'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_attach_iscsi_main)

# vi: ts=4 expandtab syntax=python
