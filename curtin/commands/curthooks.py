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

import copy
import os
import platform
import sys
import shutil
import textwrap

from curtin import config
from curtin import block
from curtin import futil
from curtin.log import LOG
from curtin import swap
from curtin import util
from curtin.reporter import events
from curtin.commands import apply_net, apt_config

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
    zipl_cfg = {
        "write_files": {
            "zipl_cfg": {
                "path": "/etc/zipl.conf",
                "content": zipl_conf,
            }
        }
    }
    write_files(zipl_cfg, target)


def run_zipl(cfg, target):
    if platform.machine() != 's390x':
        return
    with util.ChrootableTarget(target) as in_chroot:
        in_chroot.subp(['zipl'])


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
        util.install_packages(fk_packages.split(), target=target)

    if kernel_package:
        util.install_packages([kernel_package], target=target)
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
            util.install_packages([kernel_fallback], target=target)
        return

    package = "linux-{flavor}{map_suffix}".format(
        flavor=flavor, map_suffix=map_suffix)

    if util.has_pkg_available(package, target):
        if util.has_pkg_installed(package, target):
            LOG.debug("Kernel package '%s' already installed", package)
        else:
            LOG.debug("installing kernel package '%s'", package)
            util.install_packages([package], target=target)
    else:
        if kernel_fallback is not None:
            LOG.info("Kernel package '%s' not available.  "
                     "Installing fallback package '%s'.",
                     package, kernel_fallback)
            util.install_packages([kernel_fallback], target=target)
        else:
            LOG.warn("Kernel package '%s' not available and no fallback."
                     " System may not boot.", package)


def setup_grub(cfg, target):
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
    except ValueError as e:
        pass

    if storage_cfg_odict:
        storage_grub_devices = []
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
            except ValueError as e:
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
                        awk "\$6 == prep { print d \$1 }" "d=$d" prep=4100
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

    if instdevs:
        instdevs = [block.get_dev_name_entry(i)[1] for i in instdevs]
    else:
        instdevs = ["none"]
    LOG.debug("installing grub to %s [replace_default=%s]",
              instdevs, replace_default)
    with util.ChrootableTarget(target):
        args = ['install-grub']
        if util.is_uefi_bootable():
            args.append("--uefi")
            if grubcfg.get('update_nvram', False):
                LOG.debug("GRUB UEFI enabling NVRAM updates")
                args.append("--update-nvram")
            else:
                LOG.debug("NOT enabling UEFI nvram updates")
                LOG.debug("Target system may not boot")
        args.append(target)

        # capture stdout and stderr joined.
        join_stdout_err = ['sh', '-c', 'exec "$0" "$@" 2>&1']
        out, _err = util.subp(
            join_stdout_err + args + instdevs, env=env, capture=True)
        LOG.debug("%s\n%s\n", args, out)


def update_initramfs(target=None, all_kernels=False):
    cmd = ['update-initramfs', '-u']
    if all_kernels:
        cmd.extend(['-k', 'all'])
    with util.ChrootableTarget(target) as in_chroot:
        in_chroot.subp(cmd)


def copy_fstab(fstab, target):
    if not fstab:
        LOG.warn("fstab variable not in state, not copying fstab")
        return

    shutil.copy(fstab, os.path.sep.join([target, 'etc/fstab']))


def copy_crypttab(crypttab, target):
    if not crypttab:
        LOG.warn("crypttab config must be specified, not copying")
        return

    shutil.copy(crypttab, os.path.sep.join([target, 'etc/crypttab']))


def copy_mdadm_conf(mdadm_conf, target):
    if not mdadm_conf:
        LOG.warn("mdadm config must be specified, not copying")
        return

    LOG.info("copying mdadm.conf into target")
    shutil.copy(mdadm_conf, os.path.sep.join([target,
                'etc/mdadm/mdadm.conf']))


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
    for rule in os.listdir(rules_d):
        target_file = os.path.join(
            target, "etc/udev/rules.d", "%s.rules" % rule)
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


def detect_and_handle_multipath(cfg, target):
    DEFAULT_MULTIPATH_PACKAGES = ['multipath-tools-boot']
    mpcfg = cfg.get('multipath', {})
    mpmode = mpcfg.get('mode', 'auto')
    mppkgs = mpcfg.get('packages', DEFAULT_MULTIPATH_PACKAGES)
    mpbindings = mpcfg.get('overwrite_bindings', True)

    if isinstance(mppkgs, str):
        mppkgs = [mppkgs]

    if mpmode == 'disabled':
        return

    if mpmode == 'auto' and not block.detect_multipath(target):
        return

    LOG.info("Detected multipath devices. Installing support via %s", mppkgs)

    util.install_packages(mppkgs, target=target)
    replace_spaces = True
    try:
        # check in-target version
        pkg_ver = util.get_package_version('multipath-tools', target=target)
        LOG.debug("get_package_version:\n%s", pkg_ver)
        LOG.debug("multipath version is %s (major=%s minor=%s micro=%s)",
                  pkg_ver['semantic_version'], pkg_ver['major'],
                  pkg_ver['minor'], pkg_ver['micro'])
        # multipath-tools versions < 0.5.0 do _NOT_ want whitespace replaced
        # i.e. 0.4.X in Trusty.
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
        # has bug opened for this issue (LP: 1432062) but it was not fixed yet.
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
            grub_dev += "-part%s" % partno

        LOG.debug("configuring multipath install for root=%s wwid=%s",
                  grub_dev, wwid)

        multipath_bind_content = '\n'.join(
            ['# This file was created by curtin while installing the system.',
             "%s %s" % (mpname, wwid),
             '# End of content generated by curtin.',
             '# Everything below is maintained by multipath subsystem.',
             ''])
        util.write_file(multipath_bind_path, content=multipath_bind_content)

        grub_cfg = os.path.sep.join(
            [target, '/etc/default/grub.d/50-curtin-multipath.cfg'])
        msg = '\n'.join([
            '# Written by curtin for multipath device wwid "%s"' % wwid,
            'GRUB_DEVICE=%s' % grub_dev,
            'GRUB_DISABLE_LINUX_UUID=true',
            ''])
        util.write_file(grub_cfg, content=msg)

    else:
        LOG.warn("Not sure how this will boot")

    # Initrams needs to be updated to include /etc/multipath.cfg
    # and /etc/multipath/bindings files.
    update_initramfs(target, all_kernels=True)


def install_missing_packages(cfg, target):
    ''' describe which operation types will require specific packages

    'custom_config_key': {
         'pkg1': ['op_name_1', 'op_name_2', ...]
     }
    '''
    custom_configs = {
        'storage': {
            'lvm2': ['lvm_volgroup', 'lvm_partition'],
            'mdadm': ['raid'],
            'bcache-tools': ['bcache']},
        'network': {
            'vlan': ['vlan'],
            'ifenslave': ['bond'],
            'bridge-utils': ['bridge']},
    }

    format_configs = {
        'xfsprogs': ['xfs'],
        'e2fsprogs': ['ext2', 'ext3', 'ext4'],
        'btrfs-tools': ['btrfs'],
    }

    needed_packages = []
    installed_packages = util.get_installed_packages(target)
    for cust_cfg, pkg_reqs in custom_configs.items():
        if cust_cfg not in cfg:
            continue

        all_types = set(
            operation['type']
            for operation in cfg[cust_cfg]['config']
            )
        for pkg, types in pkg_reqs.items():
            if set(types).intersection(all_types) and \
               pkg not in installed_packages:
                needed_packages.append(pkg)

        format_types = set(
            [operation['fstype']
             for operation in cfg[cust_cfg]['config']
             if operation['type'] == 'format'])
        for pkg, fstypes in format_configs.items():
            if set(fstypes).intersection(format_types) and \
               pkg not in installed_packages:
                needed_packages.append(pkg)

    arch_packages = {
        's390x': [('s390-tools', 'zipl')],
    }

    for pkg, cmd in arch_packages.get(platform.machine(), []):
        if not util.which(cmd, target=target):
            if pkg not in needed_packages:
                needed_packages.append(pkg)

    if needed_packages:
        state = util.load_command_environment()
        with events.ReportEventStack(
                name=state.get('report_stack_prefix'),
                reporting_enabled=True, level="INFO",
                description="Installing packages on target system: " +
                str(needed_packages)):
            util.install_packages(needed_packages, target=target)


def system_upgrade(cfg, target):
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

    util.system_upgrade(target=target)


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

    # if network-config hook exists in target,
    # we do not run the builtin
    if util.run_hook_if_exists(target, 'curtin-hooks'):
        sys.exit(0)

    cfg = config.load_command_config(args, state)
    stack_prefix = state.get('report_stack_prefix', '')

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="writing config files and configuring apt"):
        write_files(cfg, target)
        do_apt_config(cfg, target)
        disable_overlayroot(cfg, target)

    # packages may be needed prior to installing kernel
    install_missing_packages(cfg, target)

    # If a mdadm.conf file was created by block_meta than it needs to be copied
    # onto the target system
    mdadm_location = os.path.join(os.path.split(state['fstab'])[0],
                                  "mdadm.conf")
    if os.path.exists(mdadm_location):
        copy_mdadm_conf(mdadm_location, target)
        # as per https://bugs.launchpad.net/ubuntu/+source/mdadm/+bug/964052
        # reconfigure mdadm
        util.subp(['dpkg-reconfigure', '--frontend=noninteractive', 'mdadm'],
                  data=None, target=target)

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="installing kernel"):
        setup_zipl(cfg, target)
        install_kernel(cfg, target)
        run_zipl(cfg, target)

        restore_dist_interfaces(cfg, target)

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="setting up swap"):
        add_swap(cfg, target, state.get('fstab'))

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="apply networking"):
        apply_networking(target, state)

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="writing etc/fstab"):
        copy_fstab(state.get('fstab'), target)

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="configuring multipath"):
        detect_and_handle_multipath(cfg, target)

    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="updating packages on target system"):
        system_upgrade(cfg, target)

    # If a crypttab file was created by block_meta than it needs to be copied
    # onto the target system, and update_initramfs() needs to be run, so that
    # the cryptsetup hooks are properly configured on the installed system and
    # it will be able to open encrypted volumes at boot.
    crypttab_location = os.path.join(os.path.split(state['fstab'])[0],
                                     "crypttab")
    if os.path.exists(crypttab_location):
        copy_crypttab(crypttab_location, target)
        update_initramfs(target)

    # If udev dname rules were created, copy them to target
    udev_rules_d = os.path.join(state['scratch'], "rules.d")
    if os.path.isdir(udev_rules_d):
        copy_dname_rules(udev_rules_d, target)

    # As a rule, ARMv7 systems don't use grub. This may change some
    # day, but for now, assume no. They do require the initramfs
    # to be updated, and this also triggers boot loader setup via
    # flash-kernel.
    machine = platform.machine()
    if (machine.startswith('armv7') or
            machine.startswith('s390x') or
            machine.startswith('aarch64') and not util.is_uefi_bootable()):
        update_initramfs(target)
    else:
        setup_grub(cfg, target)

    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, curthooks)


# vi: ts=4 expandtab syntax=python
