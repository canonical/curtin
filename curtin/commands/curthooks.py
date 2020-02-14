# This file is part of curtin. See LICENSE file for copyright and license info.

import copy
import glob
import os
import platform
import re
import sys
import shutil
import textwrap

from curtin import config
from curtin import block
from curtin import distro
from curtin.block import iscsi
from curtin import net
from curtin import futil
from curtin.log import LOG
from curtin import paths
from curtin import swap
from curtin import util
from curtin import version as curtin_version
from curtin.block import deps as bdeps
from curtin.distro import DISTROS
from curtin.net import deps as ndeps
from curtin.reporter import events
from curtin.commands import apply_net, apt_config
from curtin.url_helper import get_maas_version

from . import populate_one_subcmd

write_files = futil._legacy_write_files  # LP: #1731709

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
        '3.16.0': '-lts-utopic',
        '3.19.0': '-lts-vivid',
        '4.2.0': '-lts-wily',
        '4.4.0': '-lts-xenial',
    },
    'xenial': {
        '4.3.0': '',  # development release has 4.3, release will have 4.4
        '4.4.0': '',
    }
}

CLOUD_INIT_YUM_REPO_TEMPLATE = """
[group_cloud-init-el-stable]
name=Copr repo for el-stable owned by @cloud-init
baseurl=https://copr-be.cloud.fedoraproject.org/results/@cloud-init/el-stable/epel-%s-$basearch/
type=rpm-md
skip_if_unavailable=True
gpgcheck=1
gpgkey=https://copr-be.cloud.fedoraproject.org/results/@cloud-init/el-stable/pubkey.gpg
repo_gpgcheck=0
enabled=1
enabled_metadata=1
"""

KERNEL_IMG_CONF_TEMPLATE = """# Kernel image management overrides
# See kernel-img.conf(5) for details
do_symlinks = yes
do_bootloader = {bootloader}
do_initrd = yes
link_in_boot = {inboot}
"""


def do_apt_config(cfg, target):
    cfg = apt_config.translate_old_apt_features(cfg)
    apt_cfg = cfg.get("apt")
    if apt_cfg is not None:
        LOG.info("curthooks handling apt to target %s with config %s",
                 target, apt_cfg)
        apt_config.handle_apt(apt_cfg, target)
    else:
        LOG.info("No apt config provided, skipping")


def disable_overlayroot(cfg, target):
    # cloud images come with overlayroot, but installed systems need disabled
    disable = cfg.get('disable_overlayroot', True)
    local_conf = os.path.sep.join([target, 'etc/overlayroot.local.conf'])
    if disable and os.path.exists(local_conf):
        LOG.debug("renaming %s to %s", local_conf, local_conf + ".old")
        shutil.move(local_conf, local_conf + ".old")


def _update_initramfs_tools(machine=None):
    """ Return a list of binary names used to update an initramfs.

    On some architectures there are helper binaries that are also
    used and will be included in the list.
    """
    tools = ['update-initramfs']
    if not machine:
        machine = platform.machine()
    if machine == 's390x':
        tools.append('zipl')
    elif machine == 'aarch64':
        tools.append('flash-kernel')
    return tools


def disable_update_initramfs(cfg, target, machine=None):
    """ Find update-initramfs tools in target and change their name. """
    with util.ChrootableTarget(target) as in_chroot:
        for tool in _update_initramfs_tools(machine=machine):
            found = util.which(tool, target=target)
            if found:
                LOG.debug('Diverting original %s in target.', tool)
                rename = found + '.curtin-disabled'
                divert = ['dpkg-divert', '--add', '--rename',
                          '--divert', rename, found]
                in_chroot.subp(divert)

                # create a dummy update-initramfs which just returns true;
                # this handles postinstall scripts which make invoke $tool
                # directly
                util.write_file(target + found,
                                content="#!/bin/true\n# diverted by curtin",
                                mode=0o755)


def update_initramfs_is_disabled(target):
    """ Return a bool indicating if initramfs tooling is disabled. """
    disabled = []
    with util.ChrootableTarget(target) as in_chroot:
        out, _err = in_chroot.subp(['dpkg-divert', '--list'], capture=True)
        disabled = [divert for divert in out.splitlines()
                    if divert.endswith('.curtin-disabled')]
    return len(disabled) > 0


def enable_update_initramfs(cfg, target, machine=None):
    """ Enable initramfs update tools by restoring their original name. """
    if update_initramfs_is_disabled(target):
        with util.ChrootableTarget(target) as in_chroot:
            for tool in _update_initramfs_tools(machine=machine):
                LOG.info('Restoring %s in target for initrd updates.', tool)
                found = util.which(tool, target=target)
                if not found:
                    continue
                # remove the diverted
                util.del_file(target + found)
                # un-divert and restore original file
                in_chroot.subp(
                    ['dpkg-divert', '--rename', '--remove', found])


def setup_zipl(cfg, target):
    if platform.machine() != 's390x':
        return

    # assuming that below gives the "/" rootfs
    target_dev = block.get_devices_for_mp(target)[0]

    root_arg = None
    # not mapped rootfs, use UUID
    if 'mapper' in target_dev:
        root_arg = target_dev
    else:
        uuid = block.get_volume_uuid(target_dev)
        if uuid:
            root_arg = "UUID=%s" % uuid

    if not root_arg:
        msg = "Failed to identify root= for %s at %s." % (target, target_dev)
        LOG.warn(msg)
        raise ValueError(msg)

    zipl_conf = """
# This has been modified by the MAAS curtin installer
[defaultboot]
default=ubuntu

[ubuntu]
target = /boot
image = /boot/vmlinuz
ramdisk = /boot/initrd.img
parameters = root=%s

""" % root_arg
    futil.write_files(
        files={"zipl_conf": {"path": "/etc/zipl.conf", "content": zipl_conf}},
        base_dir=target)


def run_zipl(cfg, target):
    if platform.machine() != 's390x':
        return
    with util.ChrootableTarget(target) as in_chroot:
        in_chroot.subp(['zipl'])


def chzdev_persist_active_online(cfg, target):
    """Use chzdev to export active|online zdevices into target."""

    if platform.machine() != 's390x':
        return

    LOG.info('Persisting zdevice configuration in target')
    target_etc = paths.target_path(target, 'etc')
    (chzdev_conf, _) = chzdev_export(active=True, online=True)
    chzdev_persistent = chzdev_prepare_for_import(chzdev_conf)
    chzdev_import(data=chzdev_persistent,
                  persistent=True, noroot=True, base={'/etc': target_etc})


def chzdev_export(active=True, online=True, persistent=False,
                  export_file=None):
    """Use chzdev to export zdevice configuration."""
    if not export_file:
        # write to stdout
        export_file = "-"

    cmd = ['chzdev', '--quiet']
    if active:
        cmd.extend(['--active'])
    if online:
        cmd.extend(['--online'])
    if persistent:
        cmd.extend(['--persistent'])
    cmd.extend(['--export', export_file])

    return util.subp(cmd, capture=True)


def chzdev_import(data=None, persistent=True, noroot=True, base=None,
                  import_file=None):
    """Use chzdev to import zdevice configuration."""
    if not any([data, import_file]):
        raise ValueError('Must provide data or input_file value.')

    if all([data, import_file]):
        raise ValueError('Cannot provide both data and input_file value.')

    if not import_file:
        import_file = "-"

    cmd = ['chzdev', '--quiet']
    if persistent:
        cmd.extend(['--persistent'])
    if noroot:
        cmd.extend(['--no-root-update'])
    if base:
        if type(base) == dict:
            cmd.extend(
                ['--base'] + ["%s=%s" % (k, v) for k, v in base.items()])
        else:
            cmd.extend(['--base', base])

    if data:
        data = data.encode()

    cmd.extend(['--import', import_file])
    return util.subp(cmd, data=data, capture=True)


def chzdev_prepare_for_import(chzdev_conf):
    """ Transform chzdev --export output into an importable form by
    replacing 'active' with 'persistent' and dropping any options
    set to 'n/a' which chzdev --import cannot handle.

    :param chzdev_conf: string output from calling chzdev --export
    :returns: string of transformed configuration
    """
    if not chzdev_conf or not isinstance(chzdev_conf, util.string_types):
        raise ValueError("Input value invalid: '%s'" % chzdev_conf)

    # transform [active] -> [persistent] and drop .*=n/a\n
    transform = re.compile(r'^\[active|^.*=n/a\n', re.MULTILINE)

    def replacements(match):
        if '[active' in match:
            return '[persistent'
        if '=n/a' in match:
            return ''

    # Note, we add a trailing newline match the final .*=n/a\n and trim
    # any trailing newlines after transforming
    if '=n/a' in chzdev_conf:
        chzdev_conf += '\n'

    return transform.sub(lambda match: replacements(match.group(0)),
                         chzdev_conf).strip()


def get_flash_kernel_pkgs(arch=None, uefi=None):
    if arch is None:
        arch = util.get_architecture()
    if uefi is None:
        uefi = util.is_uefi_bootable()
    if uefi:
        return None
    if not arch.startswith('arm'):
        return None

    try:
        fk_packages, _ = util.subp(
            ['list-flash-kernel-packages'], capture=True)
        return fk_packages
    except util.ProcessExecutionError:
        # Ignore errors
        return None


def setup_kernel_img_conf(target):
    # kernel-img.conf only needed on release prior to 19.10
    lsb_info = distro.lsb_release(target=target)
    if tuple(map(int, lsb_info['release'].split('.'))) >= (19, 10):
        return

    kernel_img_conf_vars = {
        'bootloader': 'no',
        'inboot': 'yes',
    }
    # see zipl-installer
    if platform.machine() == 's390x':
        kernel_img_conf_vars['bootloader'] = 'yes'
    # see base-installer/debian/templates-arch
    if util.get_platform_arch() in ['amd64', 'i386']:
        kernel_img_conf_vars['inboot'] = 'no'
    kernel_img_conf_path = os.path.sep.join([target, '/etc/kernel-img.conf'])
    content = KERNEL_IMG_CONF_TEMPLATE.format(**kernel_img_conf_vars)
    util.write_file(kernel_img_conf_path, content=content)


def install_kernel(cfg, target):
    kernel_cfg = cfg.get('kernel', {'package': None,
                                    'fallback-package': "linux-generic",
                                    'mapping': {}})
    if kernel_cfg is not None:
        kernel_package = kernel_cfg.get('package')
        kernel_fallback = kernel_cfg.get('fallback-package')
    else:
        kernel_package = None
        kernel_fallback = None

    mapping = copy.deepcopy(KERNEL_MAPPING)
    config.merge_config(mapping, kernel_cfg.get('mapping', {}))

    # Machines using flash-kernel may need additional dependencies installed
    # before running. Run those checks in the ephemeral environment so the
    # target only has required packages installed.  See LP:1640519
    fk_packages = get_flash_kernel_pkgs()
    if fk_packages:
        distro.install_packages(fk_packages.split(), target=target)

    if kernel_package:
        distro.install_packages([kernel_package], target=target)
        return

    # uname[2] is kernel name (ie: 3.16.0-7-generic)
    # version gets X.Y.Z, flavor gets anything after second '-'.
    kernel = os.uname()[2]
    codename, _ = util.subp(['lsb_release', '--codename', '--short'],
                            capture=True, target=target)
    codename = codename.strip()
    version, abi, flavor = kernel.split('-', 2)

    try:
        map_suffix = mapping[codename][version]
    except KeyError:
        LOG.warn("Couldn't detect kernel package to install for %s."
                 % kernel)
        if kernel_fallback is not None:
            distro.install_packages([kernel_fallback], target=target)
        return

    package = "linux-{flavor}{map_suffix}".format(
        flavor=flavor, map_suffix=map_suffix)

    if distro.has_pkg_available(package, target):
        if distro.has_pkg_installed(package, target):
            LOG.debug("Kernel package '%s' already installed", package)
        else:
            LOG.debug("installing kernel package '%s'", package)
            distro.install_packages([package], target=target)
    else:
        if kernel_fallback is not None:
            LOG.info("Kernel package '%s' not available.  "
                     "Installing fallback package '%s'.",
                     package, kernel_fallback)
            distro.install_packages([kernel_fallback], target=target)
        else:
            LOG.warn("Kernel package '%s' not available and no fallback."
                     " System may not boot.", package)


def uefi_remove_old_loaders(grubcfg, target):
    """Removes the old UEFI loaders from efibootmgr."""
    efi_output = util.get_efibootmgr(target)
    current_uefi_boot = efi_output.get('current', None)
    old_efi_entries = {
        entry: info
        for entry, info in efi_output['entries'].items()
        if re.match(r'^.*File\(\\EFI.*$', info['path'])
    }
    old_efi_entries.pop(current_uefi_boot, None)
    remove_old_loaders = grubcfg.get('remove_old_uefi_loaders', True)
    if old_efi_entries:
        if remove_old_loaders:
            with util.ChrootableTarget(target) as in_chroot:
                for entry, info in old_efi_entries.items():
                    LOG.debug("removing old UEFI entry: %s" % info['name'])
                    in_chroot.subp(
                        ['efibootmgr', '-B', '-b', entry], capture=True)
        else:
            LOG.debug(
                "Skipped removing %d old UEFI entrie%s.",
                len(old_efi_entries),
                '' if len(old_efi_entries) == 1 else 's')
            for info in old_efi_entries.values():
                LOG.debug(
                    "UEFI entry '%s' might no longer exist and "
                    "should be removed.", info['name'])


def uefi_reorder_loaders(grubcfg, target):
    """Reorders the UEFI BootOrder to place BootCurrent first.

    The specifically doesn't try to do to much. The order in which grub places
    a new EFI loader is up to grub. This only moves the BootCurrent to the
    front of the BootOrder.
    """
    if grubcfg.get('reorder_uefi', True):
        efi_output = util.get_efibootmgr(target)
        currently_booted = efi_output.get('current', None)
        boot_order = efi_output.get('order', [])
        if currently_booted:
            if currently_booted in boot_order:
                boot_order.remove(currently_booted)
            boot_order = [currently_booted] + boot_order
            new_boot_order = ','.join(boot_order)
            LOG.debug(
                "Setting currently booted %s as the first "
                "UEFI loader.", currently_booted)
            LOG.debug(
                "New UEFI boot order: %s", new_boot_order)
            with util.ChrootableTarget(target) as in_chroot:
                in_chroot.subp(['efibootmgr', '-o', new_boot_order])
    else:
        LOG.debug("Skipped reordering of UEFI boot methods.")
        LOG.debug("Currently booted UEFI loader might no longer boot.")


def setup_grub(cfg, target, osfamily=DISTROS.debian):
    # target is the path to the mounted filesystem

    # FIXME: these methods need moving to curtin.block
    # and using them from there rather than commands.block_meta
    from curtin.commands.block_meta import (extract_storage_ordered_dict,
                                            get_path_to_storage_volume)

    grubcfg = cfg.get('grub', {})

    # copy legacy top level name
    if 'grub_install_devices' in cfg and 'install_devices' not in grubcfg:
        grubcfg['install_devices'] = cfg['grub_install_devices']

    LOG.debug("setup grub on target %s", target)
    # if there is storage config, look for devices tagged with 'grub_device'
    storage_cfg_odict = None
    try:
        storage_cfg_odict = extract_storage_ordered_dict(cfg)
    except ValueError:
        pass

    if storage_cfg_odict:
        storage_grub_devices = []
        if util.is_uefi_bootable():
            # Curtin only supports creating one EFI system partition. Thus the
            # grub_device can only be the default system partition mounted at
            # /boot/efi.
            for item_id, item in storage_cfg_odict.items():
                if item.get('path') == '/boot/efi':
                    efi_dev_id = storage_cfg_odict[item['device']]['volume']
                    LOG.debug("checking: %s", item)
                    storage_grub_devices.append(get_path_to_storage_volume(
                        efi_dev_id, storage_cfg_odict))
                    break
        else:
            for item_id, item in storage_cfg_odict.items():
                if not item.get('grub_device'):
                    continue
                LOG.debug("checking: %s", item)
                storage_grub_devices.append(
                    get_path_to_storage_volume(item_id, storage_cfg_odict))

        if len(storage_grub_devices) > 0:
            grubcfg['install_devices'] = storage_grub_devices

    LOG.debug("install_devices: %s", grubcfg.get('install_devices'))
    if 'install_devices' in grubcfg:
        instdevs = grubcfg.get('install_devices')
        if isinstance(instdevs, str):
            instdevs = [instdevs]
        if instdevs is None:
            LOG.debug("grub installation disabled by config")
    else:
        # If there were no install_devices found then we try to do the right
        # thing.  That right thing is basically installing on all block
        # devices that are mounted.  On powerpc, though it means finding PrEP
        # partitions.
        devs = block.get_devices_for_mp(target)
        blockdevs = set()
        for maybepart in devs:
            try:
                (blockdev, part) = block.get_blockdev_for_partition(maybepart)
                blockdevs.add(blockdev)
            except ValueError:
                # if there is no syspath for this device such as a lvm
                # or raid device, then a ValueError is raised here.
                LOG.debug("failed to find block device for %s", maybepart)

        if platform.machine().startswith("ppc64"):
            # assume we want partitions that are 4100 (PReP). The snippet here
            # just prints the partition number partitions of that type.
            shnip = textwrap.dedent("""
                export LANG=C;
                for d in "$@"; do
                    sgdisk "$d" --print |
                        awk '$6 == prep { print d $1 }' "d=$d" prep=4100
                done
                """)
            try:
                out, err = util.subp(
                    ['sh', '-c', shnip, '--'] + list(blockdevs),
                    capture=True)
                instdevs = str(out).splitlines()
                if not instdevs:
                    LOG.warn("No power grub target partitions found!")
                    instdevs = None
            except util.ProcessExecutionError as e:
                LOG.warn("Failed to find power grub partitions: %s", e)
                instdevs = None
        else:
            instdevs = list(blockdevs)

    env = os.environ.copy()

    replace_default = grubcfg.get('replace_linux_default', True)
    if str(replace_default).lower() in ("0", "false"):
        env['REPLACE_GRUB_LINUX_DEFAULT'] = "0"
    else:
        env['REPLACE_GRUB_LINUX_DEFAULT'] = "1"

    probe_os = grubcfg.get('probe_additional_os', False)
    if probe_os not in (False, True):
        raise ValueError("Unexpected value %s for 'probe_additional_os'. "
                         "Value must be boolean" % probe_os)
    env['DISABLE_OS_PROBER'] = "0" if probe_os else "1"

    # if terminal is present in config, but unset, then don't
    grub_terminal = grubcfg.get('terminal', 'console')
    if not isinstance(grub_terminal, str):
        raise ValueError("Unexpected value %s for 'terminal'. "
                         "Value must be a string" % grub_terminal)
    if not grub_terminal.lower() == "unmodified":
        env['GRUB_TERMINAL'] = grub_terminal

    if instdevs:
        instdevs = [block.get_dev_name_entry(i)[1] for i in instdevs]
    else:
        instdevs = ["none"]

    if util.is_uefi_bootable() and grubcfg.get('update_nvram', True):
        uefi_remove_old_loaders(grubcfg, target)

    LOG.debug("installing grub to %s [replace_default=%s]",
              instdevs, replace_default)

    with util.ChrootableTarget(target):
        args = ['install-grub']
        if util.is_uefi_bootable():
            args.append("--uefi")
            LOG.debug("grubcfg: %s", grubcfg)
            if grubcfg.get('update_nvram', True):
                LOG.debug("GRUB UEFI enabling NVRAM updates")
                args.append("--update-nvram")
            else:
                LOG.debug("NOT enabling UEFI nvram updates")
                LOG.debug("Target system may not boot")
        args.append('--os-family=%s' % osfamily)
        args.append(target)

        # capture stdout and stderr joined.
        join_stdout_err = ['sh', '-c', 'exec "$0" "$@" 2>&1']
        out, _err = util.subp(
            join_stdout_err + args + instdevs, env=env, capture=True)
        LOG.debug("%s\n%s\n", args + instdevs, out)

    if util.is_uefi_bootable() and grubcfg.get('update_nvram', True):
        uefi_reorder_loaders(grubcfg, target)


def update_initramfs(target=None, all_kernels=False):
    """ Invoke update-initramfs in the target path.

    Look up the installed kernel versions in the target
    to ensure that an initrd get created or updated as needed.
    This allows curtin to invoke update-initramfs exactly once
    at the end of the install instead of multiple calls.
    """
    if update_initramfs_is_disabled(target):
        return

    # We keep the all_kernels flag for callers, the implementation
    # now will operate correctly on all kernels present in the image
    # which is almost always exactly one.
    #
    # Ideally curtin should be able to use update-initramfs -k all
    # however, update-initramfs expects to be able to find out which
    # versions of kernels are installed by using values from the
    # kernel package invoking update-initramfs -c <kernel version>.
    # With update-initramfs diverted, nothing captures the kernel
    # version strings in the place where update-initramfs expects
    # to find this information.  Instead, curtin will examine
    # /boot to see what kernels and initramfs are installed and
    # either create or update as needed.
    #
    # This loop below will examine the contents of target's
    # /boot and pattern match for kernel files. On Ubuntu this
    # is in the form of /boot/vmlinu[xz]-<uname -r version>.
    #
    # For each kernel, we extract the version string and then
    # construct the name of of the initrd file that *would*
    # have been created when the kernel package was installed
    # if curtin had not diverted update-initramfs to prevent
    # duplicate initrd creation.
    #
    # if the initrd file exists, then we only need to invoke
    # update-initramfs's -u (update) method.  If the file does
    # not exist, then we need to run the -c (create) method.
    boot = paths.target_path(target, 'boot')
    for kernel in sorted(glob.glob(boot + '/vmlinu*-*')):
        kfile = os.path.basename(kernel)
        # handle vmlinux or vmlinuz
        kprefix = kfile.split('-')[0]
        version = kfile.replace(kprefix + '-', '')
        initrd = kernel.replace(kprefix, 'initrd.img')
        # -u == update, -c == create
        mode = '-u' if os.path.exists(initrd) else '-c'
        cmd = ['update-initramfs', mode, '-k', version]
        with util.ChrootableTarget(target) as in_chroot:
            in_chroot.subp(cmd)
            if not os.path.exists(initrd):
                files = os.listdir(target + '/boot')
                LOG.debug('Failed to find initrd %s', initrd)
                LOG.debug('Files in target /boot: %s', files)


def copy_fstab(fstab, target):
    if not fstab:
        LOG.warn("fstab variable not in state, not copying fstab")
        return

    content = util.load_file(fstab)
    header = distro.fstab_header()
    util.write_file(os.path.sep.join([target, 'etc/fstab']),
                    content="%s\n%s" % (header, content))


def copy_crypttab(crypttab, target):
    if not crypttab:
        LOG.warn("crypttab config must be specified, not copying")
        return

    shutil.copy(crypttab, os.path.sep.join([target, 'etc/crypttab']))


def copy_iscsi_conf(nodes_dir, target, target_nodes_dir='etc/iscsi/nodes'):
    if not nodes_dir:
        LOG.warn("nodes directory must be specified, not copying")
        return

    LOG.info("copying iscsi nodes database into target")
    tdir = os.path.sep.join([target, target_nodes_dir])
    if not os.path.exists(tdir):
        shutil.copytree(nodes_dir, tdir)
    else:
        # if /etc/iscsi/nodes exists, copy dirs underneath
        for ndir in os.listdir(nodes_dir):
            source_dir = os.path.join(nodes_dir, ndir)
            target_dir = os.path.join(tdir, ndir)
            shutil.copytree(source_dir, target_dir)


def copy_mdadm_conf(mdadm_conf, target):
    if not mdadm_conf:
        LOG.warn("mdadm config must be specified, not copying")
        return

    LOG.info("copying mdadm.conf into target")
    shutil.copy(mdadm_conf, os.path.sep.join([target,
                'etc/mdadm/mdadm.conf']))


def copy_zpool_cache(zpool_cache, target):
    if not zpool_cache:
        LOG.warn("zpool_cache path must be specified, not copying")
        return

    shutil.copy(zpool_cache, os.path.sep.join([target, 'etc/zfs']))


def copy_zkey_repository(zkey_repository, target,
                         target_repo='etc/zkey/repository'):
    if not zkey_repository:
        LOG.warn("zkey repository path must be specified, not copying")
        return

    tdir = os.path.sep.join([target, target_repo])
    if not os.path.exists(tdir):
        util.ensure_dir(tdir)

    files_copied = []
    for src in os.listdir(zkey_repository):
        source_path = os.path.join(zkey_repository, src)
        target_path = os.path.join(tdir, src)
        if not os.path.exists(target_path):
            shutil.copy2(source_path, target_path)
            files_copied.append(target_path)

    LOG.debug('Imported zkey repo %s with files: %s',
              zkey_repository, files_copied)


def apply_networking(target, state):
    netconf = state.get('network_config')
    interfaces = state.get('interfaces')

    def is_valid_src(infile):
        with open(infile, 'r') as fp:
            content = fp.read()
            if len(content.split('\n')) > 1:
                return True
        return False

    if is_valid_src(netconf):
        LOG.info("applying network_config")
        apply_net.apply_net(target, network_state=None, network_config=netconf)
    else:
        LOG.debug("copying interfaces")
        copy_interfaces(interfaces, target)


def copy_interfaces(interfaces, target):
    if not interfaces:
        LOG.warn("no interfaces file to copy!")
        return
    eni = os.path.sep.join([target, 'etc/network/interfaces'])
    shutil.copy(interfaces, eni)


def copy_dname_rules(rules_d, target):
    if not rules_d:
        LOG.warn("no udev rules directory to copy")
        return
    target_rules_dir = paths.target_path(target, "etc/udev/rules.d")
    for rule in os.listdir(rules_d):
        target_file = os.path.join(target_rules_dir, rule)
        shutil.copy(os.path.join(rules_d, rule), target_file)


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


def add_swap(cfg, target, fstab):
    # add swap file per cfg to filesystem root at target. update fstab.
    #
    # swap:
    #  filename: 'swap.img',
    #  size: None # (or 1G)
    #  maxsize: 2G
    if 'swap' in cfg and not cfg.get('swap'):
        LOG.debug("disabling 'add_swap' due to config")
        return

    swapcfg = cfg.get('swap', {})
    fname = swapcfg.get('filename', None)
    size = swapcfg.get('size', None)
    maxsize = swapcfg.get('maxsize', None)

    if size:
        size = util.human2bytes(str(size))
    if maxsize:
        maxsize = util.human2bytes(str(maxsize))

    swap.setup_swapfile(target=target, fstab=fstab, swapfile=fname, size=size,
                        maxsize=maxsize)


def detect_and_handle_multipath(cfg, target, osfamily=DISTROS.debian):
    DEFAULT_MULTIPATH_PACKAGES = {
        DISTROS.debian: ['multipath-tools-boot'],
        DISTROS.redhat: ['device-mapper-multipath'],
    }
    if osfamily not in DEFAULT_MULTIPATH_PACKAGES:
        raise ValueError(
                'No multipath package mapping for distro: %s' % osfamily)

    mpcfg = cfg.get('multipath', {})
    mpmode = mpcfg.get('mode', 'auto')
    mppkgs = mpcfg.get('packages',
                       DEFAULT_MULTIPATH_PACKAGES.get(osfamily))
    mpbindings = mpcfg.get('overwrite_bindings', True)

    if isinstance(mppkgs, str):
        mppkgs = [mppkgs]

    if mpmode == 'disabled':
        return

    if mpmode == 'auto' and not block.detect_multipath(target):
        return

    LOG.info("Detected multipath devices. Installing support via %s", mppkgs)
    needed = [pkg for pkg in mppkgs if pkg
              not in distro.get_installed_packages(target)]
    if needed:
        distro.install_packages(needed, target=target, osfamily=osfamily)

    replace_spaces = True
    if osfamily == DISTROS.debian:
        try:
            # check in-target version
            pkg_ver = distro.get_package_version('multipath-tools',
                                                 target=target)
            LOG.debug("get_package_version:\n%s", pkg_ver)
            LOG.debug("multipath version is %s (major=%s minor=%s micro=%s)",
                      pkg_ver['semantic_version'], pkg_ver['major'],
                      pkg_ver['minor'], pkg_ver['micro'])
            # multipath-tools versions < 0.5.0 do _NOT_
            # want whitespace replaced i.e. 0.4.X in Trusty.
            if pkg_ver['semantic_version'] < 500:
                replace_spaces = False
        except Exception as e:
            LOG.warn("failed reading multipath-tools version, "
                     "assuming it wants no spaces in wwids: %s", e)

    multipath_cfg_path = os.path.sep.join([target, '/etc/multipath.conf'])
    multipath_bind_path = os.path.sep.join([target, '/etc/multipath/bindings'])

    # We don't want to overwrite multipath.conf file provided by the image.
    if not os.path.isfile(multipath_cfg_path):
        # Without user_friendly_names option enabled system fails to boot
        # if any of the disks has spaces in its name. Package multipath-tools
        # has bug opened for this issue LP: #1432062 but it was not fixed yet.
        multipath_cfg_content = '\n'.join(
            ['# This file was created by curtin while installing the system.',
             'defaults {',
             '	user_friendly_names yes',
             '}',
             ''])
        util.write_file(multipath_cfg_path, content=multipath_cfg_content)

    if mpbindings or not os.path.isfile(multipath_bind_path):
        # we do assume that get_devices_for_mp()[0] is /
        target_dev = block.get_devices_for_mp(target)[0]
        wwid = block.get_scsi_wwid(target_dev,
                                   replace_whitespace=replace_spaces)
        blockdev, partno = block.get_blockdev_for_partition(target_dev)

        mpname = "mpath0"
        grub_dev = "/dev/mapper/" + mpname
        if partno is not None:
            if osfamily == DISTROS.debian:
                grub_dev += "-part%s" % partno
            elif osfamily == DISTROS.redhat:
                grub_dev += "p%s" % partno
            else:
                raise ValueError(
                        'Unknown grub_dev mapping for distro: %s' % osfamily)

        LOG.debug("configuring multipath install for root=%s wwid=%s",
                  grub_dev, wwid)

        multipath_bind_content = '\n'.join(
            ['# This file was created by curtin while installing the system.',
             "%s %s" % (mpname, wwid),
             '# End of content generated by curtin.',
             '# Everything below is maintained by multipath subsystem.',
             ''])
        util.write_file(multipath_bind_path, content=multipath_bind_content)

        if osfamily == DISTROS.debian:
            grub_cfg = os.path.sep.join(
                [target, '/etc/default/grub.d/50-curtin-multipath.cfg'])
            omode = 'w'
        elif osfamily == DISTROS.redhat:
            grub_cfg = os.path.sep.join([target, '/etc/default/grub'])
            omode = 'a'
        else:
            raise ValueError(
                    'Unknown grub_cfg mapping for distro: %s' % osfamily)

        msg = '\n'.join([
            '# Written by curtin for multipath device %s %s' % (mpname, wwid),
            'GRUB_DEVICE=%s' % grub_dev,
            'GRUB_DISABLE_LINUX_UUID=true',
            ''])
        util.write_file(grub_cfg, omode=omode, content=msg)
    else:
        LOG.warn("Not sure how this will boot")

    if osfamily == DISTROS.debian:
        # Initrams needs to be updated to include /etc/multipath.cfg
        # and /etc/multipath/bindings files.
        update_initramfs(target, all_kernels=True)
    elif osfamily == DISTROS.redhat:
        # Write out initramfs/dracut config for multipath
        dracut_conf_multipath = os.path.sep.join(
            [target, '/etc/dracut.conf.d/10-curtin-multipath.conf'])
        msg = '\n'.join([
            '# Written by curtin for multipath device wwid "%s"' % wwid,
            'force_drivers+=" dm-multipath "',
            'add_dracutmodules+="multipath"',
            'install_items+="/etc/multipath.conf /etc/multipath/bindings"',
            ''])
        util.write_file(dracut_conf_multipath, content=msg)
    else:
        raise ValueError(
                'Unknown initramfs mapping for distro: %s' % osfamily)


def detect_required_packages(cfg, osfamily=DISTROS.debian):
    """
    detect packages that will be required in-target by custom config items
    """

    mapping = {
        'storage': bdeps.detect_required_packages_mapping(osfamily=osfamily),
        'network': ndeps.detect_required_packages_mapping(osfamily=osfamily),
    }

    needed_packages = []
    for cfg_type, cfg_map in mapping.items():

        # skip missing or invalid config items, configs may
        # only have network or storage, not always both
        if not isinstance(cfg.get(cfg_type), dict):
            continue

        cfg_version = cfg[cfg_type].get('version')
        if not isinstance(cfg_version, int) or cfg_version not in cfg_map:
            msg = ('Supplied configuration version "%s", for config type'
                   '"%s" is not present in the known mapping.' % (cfg_version,
                                                                  cfg_type))
            raise ValueError(msg)

        mapped_config = cfg_map[cfg_version]
        found_reqs = mapped_config['handler'](cfg, mapped_config['mapping'])
        needed_packages.extend(found_reqs)

    LOG.debug('Curtin config dependencies requires additional packages: %s',
              needed_packages)
    return needed_packages


def install_missing_packages(cfg, target, osfamily=DISTROS.debian):
    ''' describe which operation types will require specific packages

    'custom_config_key': {
         'pkg1': ['op_name_1', 'op_name_2', ...]
     }
    '''
    installed_packages = distro.get_installed_packages(target)
    needed_packages = set([pkg for pkg in
                           detect_required_packages(cfg, osfamily=osfamily)
                           if pkg not in installed_packages])

    arch_packages = {
        's390x': [('s390-tools', 'zipl')],
    }

    for pkg, cmd in arch_packages.get(platform.machine(), []):
        if not util.which(cmd, target=target):
            if pkg not in needed_packages:
                needed_packages.add(pkg)

    # UEFI requires grub-efi-{arch}. If a signed version of that package
    # exists then it will be installed.
    if util.is_uefi_bootable():
        uefi_pkgs = ['efibootmgr']
        if osfamily == DISTROS.redhat:
            # centos/redhat doesn't support 32-bit?
            if 'grub2-efi-x64-modules' not in installed_packages:
                # Previously Curtin only supported unsigned GRUB due to an
                # upstream bug. By default lp:maas-image-builder and
                # packer-maas have grub preinstalled. If grub2-efi-x64-modules
                # is already in the image use unsigned grub so the install
                # doesn't require Internet access. If grub is missing use the
                # signed version.
                uefi_pkgs.extend(['grub2-efi-x64', 'shim-x64'])
        elif osfamily == DISTROS.debian:
            arch = util.get_architecture()
            if arch == 'i386':
                arch = 'ia32'
            uefi_pkgs.append('grub-efi-%s' % arch)

            # Architecture might support a signed UEFI loader
            uefi_pkg_signed = 'grub-efi-%s-signed' % arch
            if distro.has_pkg_available(uefi_pkg_signed):
                uefi_pkgs.append(uefi_pkg_signed)

            # AMD64 has shim-signed for SecureBoot support
            if arch == "amd64":
                uefi_pkgs.append("shim-signed")
        else:
            raise ValueError('Unknown grub2 package list for distro: %s' %
                             osfamily)
        needed_packages.update([pkg for pkg in uefi_pkgs
                                if pkg not in installed_packages])

    # Filter out ifupdown network packages on netplan enabled systems.
    has_netplan = ('nplan' in installed_packages or
                   'netplan.io' in installed_packages)
    if 'ifupdown' not in installed_packages and has_netplan:
        drops = set(['bridge-utils', 'ifenslave', 'vlan'])
        if needed_packages.union(drops):
            LOG.debug("Skipping install of %s.  Not needed on netplan system.",
                      needed_packages.union(drops))
            needed_packages = needed_packages.difference(drops)

    if needed_packages:
        to_add = list(sorted(needed_packages))
        state = util.load_command_environment()
        with events.ReportEventStack(
                name=state.get('report_stack_prefix'),
                reporting_enabled=True, level="INFO",
                description="Installing packages on target system: " +
                str(to_add)):
            distro.install_packages(to_add, target=target, osfamily=osfamily)


def system_upgrade(cfg, target, osfamily=DISTROS.debian):
    """run system-upgrade (apt-get dist-upgrade) or other in target.

    config:
      system_upgrade:
        enabled: False

    """
    mycfg = {'system_upgrade': {'enabled': False}}
    config.merge_config(mycfg, cfg)
    mycfg = mycfg.get('system_upgrade')
    if not isinstance(mycfg, dict):
        LOG.debug("system_upgrade disabled by config. entry not a dict.")
        return

    if not config.value_as_boolean(mycfg.get('enabled', True)):
        LOG.debug("system_upgrade disabled by config.")
        return

    distro.system_upgrade(target=target, osfamily=osfamily)


def inject_pollinate_user_agent_config(ua_cfg, target):
    """Write out user-agent config dictionary to pollinate's
    user-agent file (/etc/pollinate/add-user-agent) in target.
    """
    if not isinstance(ua_cfg, dict):
        raise ValueError('ua_cfg is not a dictionary: %s', ua_cfg)

    pollinate_cfg = paths.target_path(target, '/etc/pollinate/add-user-agent')
    comment = "# written by curtin"
    content = "\n".join(["%s/%s %s" % (ua_key, ua_val, comment)
                         for ua_key, ua_val in ua_cfg.items()]) + "\n"
    util.write_file(pollinate_cfg, content=content)


def handle_pollinate_user_agent(cfg, target):
    """Configure the pollinate user-agent if provided configuration

    pollinate:
        user_agent: false  # disable writing out a user-agent string

    # custom agent key/value pairs
    pollinate:
       user_agent:
          key1: value1
          key2: value2

    No config will result in curtin fetching:
      curtin version
      maas version (via endpoint URL, if present)
    """
    if not util.which('pollinate', target=target):
        return

    pcfg = cfg.get('pollinate')
    if not isinstance(pcfg, dict):
        pcfg = {'user_agent': {}}

    uacfg = pcfg.get('user_agent', {})
    if uacfg is False:
        return

    # set curtin version
    uacfg['curtin'] = curtin_version.version_string()

    # maas configures a curtin reporting webhook handler with
    # an endpoint URL.  This url is used to query the MAAS REST
    # api to extract the exact maas version.
    maas_reporting = cfg.get('reporting', {}).get('maas', None)
    if maas_reporting:
        endpoint = maas_reporting.get('endpoint')
        maas_version = get_maas_version(endpoint)
        if maas_version:
            uacfg['maas'] = maas_version['version']

    inject_pollinate_user_agent_config(uacfg, target)


def configure_iscsi(cfg, state_etcd, target, osfamily=DISTROS.debian):
    # If a /etc/iscsi/nodes/... file was created by block_meta then it
    # needs to be copied onto the target system
    nodes = os.path.join(state_etcd, "nodes")
    if not os.path.exists(nodes):
        return

    LOG.info('Iscsi configuration found, enabling service')
    if osfamily == DISTROS.redhat:
        # copy iscsi node config to target image
        LOG.debug('Copying iscsi node config to target')
        copy_iscsi_conf(nodes, target, target_nodes_dir='var/lib/iscsi/nodes')

        # update in-target config
        with util.ChrootableTarget(target) as in_chroot:
            # enable iscsid service
            LOG.debug('Enabling iscsi daemon')
            in_chroot.subp(['chkconfig', 'iscsid', 'on'])

            # update selinux config for iscsi ports required
            for port in [str(port) for port in
                         iscsi.get_iscsi_ports_from_config(cfg)]:
                LOG.debug('Adding iscsi port %s to selinux iscsi_port_t list',
                          port)
                in_chroot.subp(['semanage', 'port', '-a', '-t',
                                'iscsi_port_t', '-p', 'tcp', port])

    elif osfamily == DISTROS.debian:
        copy_iscsi_conf(nodes, target)
    else:
        raise ValueError(
                'Unknown iscsi requirements for distro: %s' % osfamily)


def configure_mdadm(cfg, state_etcd, target, osfamily=DISTROS.debian):
    # If a mdadm.conf file was created by block_meta than it needs
    # to be copied onto the target system
    mdadm_location = os.path.join(state_etcd, "mdadm.conf")
    if not os.path.exists(mdadm_location):
        return

    conf_map = {
        DISTROS.debian: 'etc/mdadm/mdadm.conf',
        DISTROS.redhat: 'etc/mdadm.conf',
    }
    if osfamily not in conf_map:
        raise ValueError(
                'Unknown mdadm conf mapping for distro: %s' % osfamily)
    LOG.info('Mdadm configuration found, enabling service')
    shutil.copy(mdadm_location, paths.target_path(target,
                                                  conf_map[osfamily]))
    if osfamily == DISTROS.debian:
        # as per LP: #964052 reconfigure mdadm
        with util.ChrootableTarget(target) as in_chroot:
            in_chroot.subp(
                ['dpkg-reconfigure', '--frontend=noninteractive', 'mdadm'],
                data=None, target=target)


def handle_cloudconfig(cfg, base_dir=None):
    """write cloud-init configuration files into base_dir.

    cloudconfig format is a dictionary of keys and values of content

    cloudconfig:
      cfg-datasource:
        content:
         |
         #cloud-cfg
         datasource_list: [ MAAS ]
      cfg-maas:
        content:
         |
         #cloud-cfg
         reporting:
           maas: { consumer_key: 8cW9kadrWZcZvx8uWP,
                   endpoint: 'http://XXX',
                   token_key: jD57DB9VJYmDePCRkq,
                   token_secret: mGFFMk6YFLA3h34QHCv22FjENV8hJkRX,
                   type: webhook}
    """
    # check that cfg is dict
    if not isinstance(cfg, dict):
        raise ValueError("cloudconfig configuration is not in dict format")

    # for each item in the dict
    #   generate a path based on item key
    #   if path is already in the item, LOG warning, and use generated path
    for cfgname, cfgvalue in cfg.items():
        cfgpath = "50-cloudconfig-%s.cfg" % cfgname
        if 'path' in cfgvalue:
            LOG.warning("cloudconfig ignoring 'path' key in config")
        cfgvalue['path'] = cfgpath

    # re-use write_files format and adjust target to prepend
    LOG.debug('Calling write_files with cloudconfig @ %s', base_dir)
    LOG.debug('Injecting cloud-config:\n%s', cfg)
    futil.write_files(cfg, base_dir)


def ubuntu_core_curthooks(cfg, target=None):
    """ Ubuntu-Core 16 images cannot execute standard curthooks
        Instead we copy in any cloud-init configuration to
        the 'LABEL=writable' partition mounted at target.
    """

    ubuntu_core_target = os.path.join(target, "system-data")
    cc_target = os.path.join(ubuntu_core_target, 'etc/cloud/cloud.cfg.d')

    cloudconfig = cfg.get('cloudconfig', None)
    if cloudconfig:
        # remove cloud-init.disabled, if found
        cloudinit_disable = os.path.join(ubuntu_core_target,
                                         'etc/cloud/cloud-init.disabled')
        if os.path.exists(cloudinit_disable):
            util.del_file(cloudinit_disable)

        handle_cloudconfig(cloudconfig, base_dir=cc_target)

    netconfig = cfg.get('network', None)
    if netconfig:
        LOG.info('Writing network configuration')
        ubuntu_core_netconfig = os.path.join(cc_target,
                                             "50-curtin-networking.cfg")
        util.write_file(ubuntu_core_netconfig,
                        content=config.dump_config({'network': netconfig}))


def redhat_upgrade_cloud_init(netcfg, target=None, osfamily=DISTROS.redhat):
    """ CentOS images execute built-in curthooks which only supports
        simple networking configuration.  This hook enables advanced
        network configuration via config passthrough to the target.
    """
    def cloud_init_repo(version):
        if not version:
            raise ValueError('Missing required version parameter')

        return CLOUD_INIT_YUM_REPO_TEMPLATE % version

    if netcfg:
        LOG.info('Removing embedded network configuration (if present)')
        ifcfgs = glob.glob(
            paths.target_path(target, 'etc/sysconfig/network-scripts') +
            '/ifcfg-*')
        # remove ifcfg-* (except ifcfg-lo)
        for ifcfg in ifcfgs:
            if os.path.basename(ifcfg) != "ifcfg-lo":
                util.del_file(ifcfg)

        LOG.info('Checking cloud-init in target [%s] for network '
                 'configuration passthrough support.', target)
        passthrough = net.netconfig_passthrough_available(target)
        LOG.debug('passthrough available via in-target: %s', passthrough)

        # if in-target cloud-init is not updated, upgrade via cloud-init repo
        if not passthrough:
            cloud_init_yum_repo = (
                paths.target_path(target,
                                  'etc/yum.repos.d/curtin-cloud-init.repo'))
            rhel_ver = distro.rpm_get_dist_id(target)
            # Inject cloud-init daily yum repo
            util.write_file(cloud_init_yum_repo,
                            content=cloud_init_repo(rhel_ver))

            # ensure up-to-date ca-certificates to handle https mirror
            # connections for epel and cloud-init-el.
            packages = ['ca-certificates']

            if int(rhel_ver) < 8:
                # cloud-init in RHEL < 8 requires EPEL for dependencies.
                packages += ['epel-release']
                # RHEL8+ no longer ships bridge-utils. This does not effect
                # bridge configuration. Only install on RHEL < 8 if not
                # available, do not upgrade.
                with util.ChrootableTarget(target) as in_chroot:
                    try:
                        in_chroot.subp(['rpm', '-q', 'bridge-utils'],
                                       capture=False, rcs=[0])
                    except util.ProcessExecutionError:
                        LOG.debug(
                            'Image missing bridge-utils package, installing')
                        packages += ['bridge-utils']

            packages += ['cloud-init-el-release', 'cloud-init']

            # We separate the installation of repository packages (epel,
            # cloud-init-el-release) as we need a new invocation of yum
            # to read the newly installed repo files.
            for package in packages:
                distro.install_packages(
                    [package], target=target, osfamily=osfamily)

            # remove cloud-init el-stable bootstrap repo config as the
            # cloud-init-el-release package points to the correct repo
            util.del_file(cloud_init_yum_repo)

    LOG.info('Passing network configuration through to target')
    net.render_netconfig_passthrough(target, netconfig={'network': netcfg})


# Public API, maas may call this from internal curthooks
centos_apply_network_config = redhat_upgrade_cloud_init


def redhat_apply_selinux_autorelabel(target):
    """Creates file /.autorelabel.

    This is used by SELinux to relabel all of the
    files on the filesystem to have the correct
    security context. Without this SSH login will
    fail.
    """
    LOG.debug('enabling selinux autorelabel')
    open(paths.target_path(target, '.autorelabel'), 'a').close()


def redhat_update_dracut_config(target, cfg):
    initramfs_mapping = {
        'lvm': {'conf': 'lvmconf', 'modules': 'lvm'},
        'raid': {'conf': 'mdadmconf', 'modules': 'mdraid'},
    }

    # no need to update initramfs if no custom storage
    if 'storage' not in cfg:
        return False

    storage_config = cfg.get('storage', {}).get('config')
    if not storage_config:
        raise ValueError('Invalid storage config')

    add_conf = set()
    add_modules = set()
    for scfg in storage_config:
        if scfg['type'] == 'raid':
            add_conf.add(initramfs_mapping['raid']['conf'])
            add_modules.add(initramfs_mapping['raid']['modules'])
        elif scfg['type'] in ['lvm_volgroup', 'lvm_partition']:
            add_conf.add(initramfs_mapping['lvm']['conf'])
            add_modules.add(initramfs_mapping['lvm']['modules'])

    dconfig = ['# Written by curtin for custom storage config']
    dconfig.append('add_dracutmodules+="%s"' % (" ".join(add_modules)))
    for conf in add_conf:
        dconfig.append('%s="yes"' % conf)

    # Write out initramfs/dracut config for storage config
    dracut_conf_storage = os.path.sep.join(
        [target, '/etc/dracut.conf.d/50-curtin-storage.conf'])
    msg = '\n'.join(dconfig + [''])
    LOG.debug('Updating redhat dracut config')
    util.write_file(dracut_conf_storage, content=msg)
    return True


def redhat_update_initramfs(target, cfg):
    if not redhat_update_dracut_config(target, cfg):
        LOG.debug('Skipping redhat initramfs update, no custom storage config')
        return
    kver_cmd = ['rpm', '-q', '--queryformat',
                '%{VERSION}-%{RELEASE}.%{ARCH}', 'kernel']
    with util.ChrootableTarget(target) as in_chroot:
        LOG.debug('Finding redhat kernel version: %s', kver_cmd)
        kver, _err = in_chroot.subp(kver_cmd, capture=True)
        LOG.debug('Found kver=%s' % kver)
        initramfs = '/boot/initramfs-%s.img' % kver
        dracut_cmd = ['dracut', '-f', initramfs, kver]
        LOG.debug('Rebuilding initramfs with: %s', dracut_cmd)
        in_chroot.subp(dracut_cmd, capture=True)


def builtin_curthooks(cfg, target, state):
    LOG.info('Running curtin builtin curthooks')
    stack_prefix = state.get('report_stack_prefix', '')
    state_etcd = os.path.split(state['fstab'])[0]
    machine = platform.machine()

    distro_info = distro.get_distroinfo(target=target)
    if not distro_info:
        raise RuntimeError('Failed to determine target distro')
    osfamily = distro_info.family
    LOG.info('Configuring target system for distro: %s osfamily: %s',
             distro_info.variant, osfamily)
    if osfamily == DISTROS.debian:
        with events.ReportEventStack(
                name=stack_prefix + '/writing-apt-config',
                reporting_enabled=True, level="INFO",
                description="configuring apt configuring apt"):
            do_apt_config(cfg, target)
            disable_overlayroot(cfg, target)
            disable_update_initramfs(cfg, target, machine)

        # LP: #1742560 prevent zfs-dkms from being installed (Xenial)
        if distro.lsb_release(target=target)['codename'] == 'xenial':
            distro.apt_update(target=target)
            with util.ChrootableTarget(target) as in_chroot:
                in_chroot.subp(['apt-mark', 'hold', 'zfs-dkms'])

    # packages may be needed prior to installing kernel
    with events.ReportEventStack(
            name=stack_prefix + '/installing-missing-packages',
            reporting_enabled=True, level="INFO",
            description="installing missing packages"):
        install_missing_packages(cfg, target, osfamily=osfamily)

    with events.ReportEventStack(
            name=stack_prefix + '/configuring-iscsi-service',
            reporting_enabled=True, level="INFO",
            description="configuring iscsi service"):
        configure_iscsi(cfg, state_etcd, target, osfamily=osfamily)

    with events.ReportEventStack(
            name=stack_prefix + '/configuring-mdadm-service',
            reporting_enabled=True, level="INFO",
            description="configuring raid (mdadm) service"):
        configure_mdadm(cfg, state_etcd, target, osfamily=osfamily)

    if osfamily == DISTROS.debian:
        with events.ReportEventStack(
                name=stack_prefix + '/installing-kernel',
                reporting_enabled=True, level="INFO",
                description="installing kernel"):
            setup_zipl(cfg, target)
            setup_kernel_img_conf(target)
            install_kernel(cfg, target)
            run_zipl(cfg, target)
            restore_dist_interfaces(cfg, target)
            chzdev_persist_active_online(cfg, target)

    with events.ReportEventStack(
            name=stack_prefix + '/setting-up-swap',
            reporting_enabled=True, level="INFO",
            description="setting up swap"):
        add_swap(cfg, target, state.get('fstab'))

    if osfamily == DISTROS.redhat:
        # set cloud-init maas datasource for centos images
        if cfg.get('cloudconfig'):
            handle_cloudconfig(
                cfg['cloudconfig'],
                base_dir=paths.target_path(target,
                                           'etc/cloud/cloud.cfg.d'))

        # For vmtests to force execute redhat_upgrade_cloud_init, uncomment
        # the value in examples/tests/centos_defaults.yaml
        if cfg.get('_ammend_centos_curthooks'):
            with events.ReportEventStack(
                    name=stack_prefix + '/upgrading cloud-init',
                    reporting_enabled=True, level="INFO",
                    description="Upgrading cloud-init in target"):
                redhat_upgrade_cloud_init(cfg.get('network', {}), target)

    with events.ReportEventStack(
            name=stack_prefix + '/apply-networking-config',
            reporting_enabled=True, level="INFO",
            description="apply networking config"):
        apply_networking(target, state)

    with events.ReportEventStack(
            name=stack_prefix + '/writing-etc-fstab',
            reporting_enabled=True, level="INFO",
            description="writing etc/fstab"):
        copy_fstab(state.get('fstab'), target)

    with events.ReportEventStack(
            name=stack_prefix + '/configuring-multipath',
            reporting_enabled=True, level="INFO",
            description="configuring multipath"):
        detect_and_handle_multipath(cfg, target, osfamily=osfamily)

    with events.ReportEventStack(
            name=stack_prefix + '/system-upgrade',
            reporting_enabled=True, level="INFO",
            description="updating packages on target system"):
        system_upgrade(cfg, target, osfamily=osfamily)

    if osfamily == DISTROS.redhat:
        with events.ReportEventStack(
                name=stack_prefix + '/enabling-selinux-autorelabel',
                reporting_enabled=True, level="INFO",
                description="enabling selinux autorelabel mode"):
            redhat_apply_selinux_autorelabel(target)

    with events.ReportEventStack(
            name=stack_prefix + '/pollinate-user-agent',
            reporting_enabled=True, level="INFO",
            description="configuring pollinate user-agent on target"):
        handle_pollinate_user_agent(cfg, target)

    if osfamily == DISTROS.debian:
        # check for the zpool cache file and copy to target if present
        zpool_cache = '/etc/zfs/zpool.cache'
        if os.path.exists(zpool_cache):
            copy_zpool_cache(zpool_cache, target)

        zkey_repository = '/etc/zkey/repository'
        zkey_used = os.path.join(os.path.split(state['fstab'])[0], "zkey_used")
        if all(map(os.path.exists, [zkey_repository, zkey_used])):
            distro.install_packages(['s390-tools-zkey'], target=target,
                                    osfamily=osfamily)
            copy_zkey_repository(zkey_repository, target)

        # If a crypttab file was created by block_meta than it needs to be
        # copied onto the target system, and update_initramfs() needs to be
        # run, so that the cryptsetup hooks are properly configured on the
        # installed system and it will be able to open encrypted volumes
        # at boot.
        crypttab_location = os.path.join(os.path.split(state['fstab'])[0],
                                         "crypttab")
        if os.path.exists(crypttab_location):
            copy_crypttab(crypttab_location, target)
            update_initramfs(target)

    # If udev dname rules were created, copy them to target
    udev_rules_d = os.path.join(state['scratch'], "rules.d")
    if os.path.isdir(udev_rules_d):
        copy_dname_rules(udev_rules_d, target)

    with events.ReportEventStack(
            name=stack_prefix + '/updating-initramfs-configuration',
            reporting_enabled=True, level="INFO",
            description="updating initramfs configuration"):
        if osfamily == DISTROS.debian:
            # re-enable update_initramfs
            enable_update_initramfs(cfg, target, machine)
            update_initramfs(target, all_kernels=True)
        elif osfamily == DISTROS.redhat:
            redhat_update_initramfs(target, cfg)

    # As a rule, ARMv7 systems don't use grub. This may change some
    # day, but for now, assume no. They do require the initramfs
    # to be updated, and this also triggers boot loader setup via
    # flash-kernel.
    if (machine.startswith('armv7') or
            machine.startswith('s390x') or
            machine.startswith('aarch64') and not util.is_uefi_bootable()):
        return

    # all other paths lead to grub
    setup_grub(cfg, target, osfamily=osfamily)


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

    cfg = config.load_command_config(args, state)
    stack_prefix = state.get('report_stack_prefix', '')
    curthooks_mode = cfg.get('curthooks', {}).get('mode', 'auto')

    # UC is special, handle it first.
    if distro.is_ubuntu_core(target):
        LOG.info('Detected Ubuntu-Core image, running hooks')
        with events.ReportEventStack(
                name=stack_prefix, reporting_enabled=True, level="INFO",
                description="Configuring Ubuntu-Core for first boot"):
            ubuntu_core_curthooks(cfg, target)
        sys.exit(0)

    # user asked for target, or auto mode
    if curthooks_mode in ['auto', 'target']:
        if util.run_hook_if_exists(target, 'curtin-hooks'):
            sys.exit(0)

    builtin_curthooks(cfg, target, state)
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, curthooks)

# vi: ts=4 expandtab syntax=python
