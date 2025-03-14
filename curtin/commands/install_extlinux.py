# This file is part of curtin. See LICENSE file for copyright and license info.

"""This loosely follows the u-boot-update script in the u-boot-menu package"""

import io
import os

from curtin import config
from curtin import paths
from curtin.log import LOG

EXTLINUX_DIR = '/boot/extlinux'


def build_content(bootcfg: config.BootCfg, target: str):
    """Build the content of the extlinux.conf file

    For now this only supports x86, since it does not handle the 'fdt' option.
    Rather than add that, the plan is to use a FIT (Flat Image Tree) which can
    handle FDT selection automatically. This should avoid the complexity
    associated with fdt and fdtdir options.

    We assume that the boot directory is available as /boot in the target.
    """
    def get_entry(label, params, menu_label_append=''):
        return f'''\
label {label}
\tmenu label {menu_label} {version}{menu_label_append}
\tlinux /{kernel_path}
\tinitrd /{initrd_path}
\tappend {params}'''

    buf = io.StringIO()
    params = 'ro quiet'
    alternatives = ['default', 'recovery']
    menu_label = 'Linux'

    # For the recovery option, remove 'quiet' and add 'single'
    without_quiet = filter(lambda word: word != 'quiet', params.split())
    rec_params = ' '.join(list(without_quiet) + ['single'])

    print(f'''\
## {EXTLINUX_DIR}/extlinux.conf
##
## IMPORTANT WARNING
##
## The configuration of this file is generated automatically.
## Do not edit this file manually, use: u-boot-update

default l0
menu title U-Boot menu
prompt 0
timeout 50''', file=buf)
    for seq, (kernel_path, full_initrd_path, version) in enumerate(
            paths.get_kernel_list(target)):
        LOG.debug('P: Writing config for %s...', kernel_path)
        initrd_path = os.path.basename(full_initrd_path)
        print(file=buf)
        print(file=buf)
        print(get_entry(f'l{seq}', params), file=buf)

        if 'recovery' in alternatives:
            print(file=buf)
            print(get_entry(f'l{seq}r', rec_params, ' (rescue target)'),
                  file=buf)

    return buf.getvalue()


def install_extlinux(
        bootcfg: config.BootCfg,
        target: str,
        ):
    """Install extlinux to the target chroot.

    :param: bootcfg: An config dict with grub config options.
    :param: target: A string specifying the path to the chroot mountpoint.
    """
    content = build_content(bootcfg, target)
    extlinux_path = paths.target_path(target, '/boot/extlinux')
    os.makedirs(extlinux_path, exist_ok=True)
    with open(extlinux_path + '/extlinux.conf', 'w', encoding='utf-8') as outf:
        outf.write(content)
