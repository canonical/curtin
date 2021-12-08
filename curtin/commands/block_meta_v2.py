# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.commands.block_meta import (
    disk_handler as disk_handler_v1,
    partition_handler as partition_handler_v1,
    )


def disk_handler_v2(info, storage_config, handlers):
    disk_handler_v1(info, storage_config, handlers)


def partition_handler_v2(info, storage_config, handlers):
    partition_handler_v1(info, storage_config, handlers)


# vi: ts=4 expandtab syntax=python
