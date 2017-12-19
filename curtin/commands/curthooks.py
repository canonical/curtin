#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

import glob
import os
import platform
import re
import sys
import shutil

from curtin import config
from curtin import block
from curtin import futil
from curtin.log import LOG
from curtin import util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-t', '--target'),
      {'help': 'operate on target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET', 'default': None}),
     (('-c', '--config'),
      {'help': 'operate on config. default is env[CONFIG]',
       'action': 'store', 'metavar': 'CONFIG', 'default': None}),
     )
)

KERNEL_MAPPING = {
    'precise': {
        '3.2.0': '',
        '3.5.0': '-lts-quantal',
        '3.8.0': '-lts-raring',
        '3.11.0': '-lts-saucy',
        '3.13.0': '-lts-trusty',
    },
    'trusty': {
        '3.13.0': '',
    },
}


def write_files(cfg, target):
    # this takes 'write_files' entry in config and writes files in the target
    # config entry example:
    # f1:
    #  path: /file1
    #  content: !!binary |
    #    f0VMRgIBAQAAAAAAAAAAAAIAPgABAAAAwARAAAAAAABAAAAAAAAAAJAVAAAAAAA
    # f2: {path: /file2, content: "foobar", permissions: '0666'}
    if 'write_files' not in cfg:
        return

    for (key, info) in cfg.get('write_files').items():
        if not info.get('path'):
            LOG.warn("Warning, write_files[%s] had no 'path' entry", key)
            continue

        futil.write_finfo(path=target + os.path.sep + info['path'],
                          content=info.get('content', ''),
                          owner=info.get('owner', "-1:-1"),
                          perms=info.get('permissions',
                                         info.get('perms', "0644")))


def apt_config(cfg, target):
    # cfg['apt_proxy']

    proxy_cfg_path = os.path.sep.join(
        [target, '/etc/apt/apt.conf.d/90curtin-aptproxy'])
    if cfg.get('apt_proxy'):
        util.write_file(
            proxy_cfg_path,
            content='Acquire::HTTP::Proxy "%s";\n' % cfg['apt_proxy'])
    else:
        if os.path.isfile(proxy_cfg_path):
            os.path.unlink(proxy_cfg_path)

    # cfg['apt_mirrors']
    # apt_mirrors:
    #  ubuntu_archive: http://local.archive/ubuntu
    #  ubuntu_security: http://local.archive/ubuntu
    sources_list = os.path.sep.join([target, '/etc/apt/sources.list'])
    if (isinstance(cfg.get('apt_mirrors'), dict) and
            os.path.isfile(sources_list)):
        repls = [
            ('ubuntu_archive', r'http://\S*[.]*archive.ubuntu.com/\S*'),
            ('ubuntu_security', r'http://security.ubuntu.com/\S*'),
        ]
        content = None
        for name, regex in repls:
            mirror = cfg['apt_mirrors'].get(name)
            if not mirror:
                continue

            if content is None:
                with open(sources_list) as fp:
                    content = fp.read()
                util.write_file(sources_list + ".dist", content)

            content = re.sub(regex, mirror + " ", content)

        if content is not None:
            util.write_file(sources_list, content)


def disable_overlayroot(cfg, target):
    # cloud images come with overlayroot, but installed systems need disabled
    disable = cfg.get('disable_overlayroot', True)
    local_conf = os.path.sep.join([target, 'etc/overlayroot.local.conf'])
    if disable and os.path.exists(local_conf):
        LOG.debug("renaming %s to %s", local_conf, local_conf + ".old")
        shutil.move(local_conf, local_conf + ".old")


def clean_cloud_init(target):
    flist = glob.glob(
        os.path.sep.join([target, "/etc/cloud/cloud.cfg.d/*dpkg*"]))

    LOG.debug("cleaning cloud-init config from: %s" % flist)
    for dpkg_cfg in flist:
        os.unlink(dpkg_cfg)


def install_kernel(cfg, target):
    kernel_cfg = cfg.get('kernel', {'package': None,
                                    'fallback-package': None,
                                    'mapping': {}})

    with util.RunInChroot(target) as in_chroot:
        if kernel_cfg is not None:
            kernel_package = kernel_cfg.get('package')
            kernel_fallback = kernel_cfg.get('fallback-package')
        else:
            kernel_package = None
            kernel_fallback = None

        if kernel_package:
            util.install_packages([kernel_package], target=target)
            return

        _, _, kernel, _, _ = os.uname()
        out, _ = in_chroot(['lsb_release', '--codename', '--short'],
                           capture=True)
        version, _, flavor = kernel.split('-', 2)
        config.merge_config(kernel_cfg['mapping'], KERNEL_MAPPING)

        try:
            map_suffix = kernel_cfg['mapping'][out.strip()][version]
        except KeyError:
            LOG.warn("Couldn't detect kernel package to install for %s."
                     % kernel)
            if kernel_fallback is not None:
                util.install_packages([kernel_fallback])
            return

        package = "linux-{flavor}{map_suffix}".format(
            flavor=flavor, map_suffix=map_suffix)
        out, _ = in_chroot(['apt-cache', 'search', package], capture=True)
        if (len(out.strip()) > 0 and
                not util.has_pkg_installed(package, target)):
            util.install_packages([package], target=target)
        else:
            LOG.warn("Tried to install kernel %s but package not found."
                     % package)
            if kernel_fallback is not None:
                util.install_packages([kernel_fallback], target=target)


def apply_debconf_selections(cfg, target):
    # debconf_selections:
    #  set1: |
    #   cloud-init cloud-init/datasources multiselect MAAS
    #  set2: pkg pkg/value string bar
    selsets = cfg.get('debconf_selections')
    if not selsets:
        LOG.debug("debconf_selections was not set in config")
        return

    # for each entry in selections, chroot and apply them.
    # keep a running total of packages we've seen.
    pkgs_cfgd = set()
    for key, content in selsets.items():
        LOG.debug("setting for %s, %s" % (key, content))
        util.subp(['chroot', target, 'debconf-set-selections'],
                  data=content.encode())
        for line in content.splitlines():
            if line.startswith("#"):
                continue
            pkg = re.sub(r"[:\s].*", "", line)
            pkgs_cfgd.add(pkg)

    pkgs_installed = get_installed_packages(target)

    LOG.debug("pkgs_cfgd: %s" % pkgs_cfgd)
    LOG.debug("pkgs_installed: %s" % pkgs_installed)
    need_reconfig = pkgs_cfgd.intersection(pkgs_installed)

    if len(need_reconfig) == 0:
        LOG.debug("no need for reconfig")
        return

    # For any packages that are already installed, but have preseed data
    # we populate the debconf database, but the filesystem configuration
    # would be preferred on a subsequent dpkg-reconfigure.
    # so, what we have to do is "know" information about certain packages
    # to unconfigure them.
    unhandled = []
    to_config = []
    for pkg in need_reconfig:
        if pkg in CONFIG_CLEANERS:
            LOG.debug("unconfiguring %s" % pkg)
            CONFIG_CLEANERS[pkg](target)
            to_config.append(pkg)
        else:
            unhandled.append(pkg)

    if len(unhandled):
        LOG.warn("The following packages were installed and preseeded, "
                 "but cannot be unconfigured: %s", unhandled)

    util.subp(['chroot', target, 'dpkg-reconfigure',
               '--frontend=noninteractive'] +
              list(to_config), data=None)


def get_installed_packages(target=None):
    cmd = []
    if target is not None:
        cmd = ['chroot', target]
    cmd.extend(['dpkg-query', '--list'])

    (out, _err) = util.subp(cmd, capture=True)
    if isinstance(out, bytes):
        out = out.decode()

    pkgs_inst = set()
    for line in out.splitlines():
        try:
            (state, pkg, other) = line.split(None, 2)
        except ValueError:
            continue
        if state.startswith("hi") or state.startswith("ii"):
            pkgs_inst.add(re.sub(":.*", "", pkg))

    return pkgs_inst


def setup_grub(cfg, target):
    grubcfg = cfg.get('grub', {})

    # copy legacy top level name
    if 'grub_install_devices' in cfg and 'install_devices' not in grubcfg:
        grubcfg['install_devices'] = cfg['grub_install_devices']

    if 'install_devices' in grubcfg:
        instdevs = grubcfg.get('install_devices')
        if isinstance(instdevs, str):
            instdevs = [instdevs]
        if instdevs is None:
            LOG.debug("grub installation disabled by config")
    else:
        devs = block.get_devices_for_mp(target)
        blockdevs = set()
        for maybepart in devs:
            (blockdev, part) = block.get_blockdev_for_partition(maybepart)
            blockdevs.add(blockdev)

        instdevs = list(blockdevs)

    # UEFI requires grub-efi-{arch}. If a signed version of that package
    # exists then it will be installed.
    if util.is_uefi_bootable():
        arch = util.get_architecture()
        pkgs = ['grub-efi-%s' % arch]

        # Architecture might support a signed UEFI loader
        uefi_pkg_signed = 'grub-efi-%s-signed' % arch
        if util.has_pkg_available(uefi_pkg_signed):
            pkgs.append(uefi_pkg_signed)

        # AMD64 has shim-signed for SecureBoot support
        if arch == "amd64":
            pkgs.append("shim-signed")

        # Install the UEFI packages needed for the architecture
        util.install_packages(pkgs, target=target)

    env = os.environ.copy()

    replace_default = grubcfg.get('replace_linux_default', True)
    if str(replace_default).lower() in ("0", "false"):
        env['REPLACE_GRUB_LINUX_DEFAULT'] = "0"
    else:
        env['REPLACE_GRUB_LINUX_DEFAULT'] = "1"

    instdevs = [block.get_dev_name_entry(i)[1] for i in instdevs]
    LOG.debug("installing grub to %s [replace_default=%s]",
              instdevs, replace_default)
    with util.ChrootableTarget(target):
        args = ['install-grub']
        if util.is_uefi_bootable():
            args.append("--uefi")
        args.append(target)
        util.subp(args + instdevs, env=env)


def update_initramfs(target):
    with util.RunInChroot(target) as in_chroot:
        in_chroot(['update-initramfs', '-u'])


def copy_fstab(fstab, target):
    if not fstab:
        LOG.warn("fstab variable not in state, not copying fstab")
        return

    shutil.copy(fstab, os.path.sep.join([target, 'etc/fstab']))


def copy_interfaces(interfaces, target):
    if not interfaces:
        LOG.warn("no interfaces file to copy!")
        return
    eni = os.path.sep.join([target, 'etc/network/interfaces'])
    shutil.copy(interfaces, eni)


def restore_dist_interfaces(cfg, target):
    # cloud images have a link of /etc/network/interfaces into /run
    eni = os.path.sep.join([target, 'etc/network/interfaces'])
    if not cfg.get('restore_dist_interfaces', True):
        return

    rp = os.path.realpath(eni)
    if (os.path.exists(eni + ".dist") and
            (rp.startswith("/run") or rp.startswith(target + "/run"))):

        LOG.debug("restoring dist interfaces, existing link pointed to /run")
        shutil.move(eni, eni + ".old")
        shutil.move(eni + ".dist", eni)


def curthooks(args):
    state = util.load_command_environment()

    if args.target is not None:
        target = args.target
    else:
        target = state['target']

    if target is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    cfg = util.load_command_config(args, state)

    write_files(cfg, target)
    apt_config(cfg, target)
    disable_overlayroot(cfg, target)
    install_kernel(cfg, target)
    apply_debconf_selections(cfg, target)

    restore_dist_interfaces(cfg, target)

    copy_interfaces(state.get('interfaces'), target)
    copy_fstab(state.get('fstab'), target)

    # As a rule, ARMv7 systems don't use grub. This may change some
    # day, but for now, assume no. They do require the initramfs
    # to be updated, and this also triggers boot loader setup via
    # flash-kernel.
    machine = platform.machine()
    if machine.startswith('armv7'):
        update_initramfs(target)
    else:
        setup_grub(cfg, target)

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, curthooks)


CONFIG_CLEANERS = {
    'cloud-init': clean_cloud_init,
}

# vi: ts=4 expandtab syntax=python
