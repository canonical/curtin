# This file is part of curtin. See LICENSE file for copyright and license info.

from . import populate_one_subcmd
from curtin.block import iscsi


def block_detach_iscsi_main(args):
    i = iscsi.IscsiDisk(args.disk)
    i.disconnect()

    return 0


CMD_ARGUMENTS = (
    ('disk',
     {'help': 'RFC4173 specification of iSCSI disk to attach'}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, block_detach_iscsi_main)

# vi: ts=4 expandtab syntax=python
