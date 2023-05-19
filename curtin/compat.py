# This file is part of curtin. See LICENSE file for copyright and license info.

import re

from curtin import util


def _get_util_linux_ver():
    line = util.subp(['losetup', '--version'], capture=True)[0].strip()
    m = re.fullmatch(r'losetup from util-linux ([\d.]+)', line)
    if m is None:
        return None
    return m.group(1)


def _check_util_linux_ver(ver, label='', fatal=False):
    ul_ver = _get_util_linux_ver()
    result = ul_ver is not None and ul_ver >= ver
    if not result and fatal:
        raise RuntimeError(
            'this system lacks the required {} support'.format(label))
    return result


def supports_large_sectors(fatal=False):
    # Known requirements:
    # * Kernel 4.14+
    #   * Minimum supported things have a higher kernel, so skip that check
    # * util-linux 2.30+
    #   * xenial has 2.27.1, bionic has 2.31.1
    # However, see also this, which suggests using 2.37.1:
    # https://lore.kernel.org/lkml/20210615084259.yj5pmyjonfqcg7lg@ws.net.home/
    return _check_util_linux_ver('2.37.1', 'large sector', fatal)


def supports_sfdisk_no_tell_kernel(fatal=False):
    # Needs util-linux 2.29+
    return _check_util_linux_ver('2.29', 'sfdisk', fatal)
