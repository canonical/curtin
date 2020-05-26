import os
import re
import platform
import shutil
import sys

from curtin import block
from curtin import config
from curtin import distro
from curtin import util
from curtin.log import LOG
from curtin.paths import target_path
from curtin.reporter import events
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

GRUB_MULTI_INSTALL = '/usr/lib/grub/grub-multi-install'


def get_grub_package_name(target_arch, uefi, rhel_ver=None):
    """Determine the correct grub distro package name.

    :param: target_arch: string specifying the target system architecture
    :param: uefi: boolean indicating if system is booted via UEFI or not
    :param: rhel_ver: string specifying the major Redhat version in use.
    :returns: tuple of strings, grub package name and grub target name
    """
    if target_arch is None:
        raise ValueError('Missing target_arch parameter')

    if uefi is None:
        raise ValueError('Missing uefi parameter')

    if 'ppc64' in target_arch:
        return ('grub-ieee1275', 'powerpc-ieee1275')
    if uefi:
        if target_arch == 'amd64':
            grub_name = 'grub-efi-%s' % target_arch
            grub_target = "x86_64-efi"
        elif target_arch == 'x86_64':
            # centos 7+, no centos6 support
            # grub2-efi-x64 installs a signed grub bootloader
            grub_name = "grub2-efi-x64"
            grub_target = "x86_64-efi"
        elif target_arch == 'arm64':
            grub_name = 'grub-efi-%s' % target_arch
            grub_target = "arm64-efi"
        elif target_arch == 'i386':
            grub_name = 'grub-efi-ia32'
            grub_target = 'i386-efi'
        else:
            raise ValueError('Unsupported UEFI arch: %s' % target_arch)
    else:
        grub_target = 'i386-pc'
        if target_arch in ['i386', 'amd64']:
            grub_name = 'grub-pc'
        elif target_arch == 'x86_64':
            if rhel_ver == '6':
                grub_name = 'grub'
            elif rhel_ver in ['7', '8']:
                grub_name = 'grub2-pc'
            else:
                raise ValueError('Unsupported RHEL version: %s', rhel_ver)
        else:
            raise ValueError('Unsupported arch: %s' % target_arch)

    return (grub_name, grub_target)


def get_grub_config_file(target=None, osfamily=None):
    """Return the filename used to configure grub.

    :param: osfamily: string specifying the target os family being configured
    :returns: string, path to the osfamily grub config file
    """
    if not osfamily:
        osfamily = distro.get_osfamily(target=target)

    if osfamily == distro.DISTROS.debian:
        # to avoid tripping prompts on upgrade LP: #564853
        return '/etc/default/grub.d/50-curtin-settings.cfg'

    return '/etc/default/grub'


def prepare_grub_dir(target, grub_cfg):
    util.ensure_dir(os.path.dirname(target_path(target, grub_cfg)))

    # LP: #1179940 . The 50-cloudig-settings.cfg file is written by the cloud
    # images build and defines/override some settings. Disable it.
    ci_cfg = target_path(target,
                         os.path.join(
                             os.path.dirname(grub_cfg),
                             "50-cloudimg-settings.cfg"))

    if os.path.exists(ci_cfg):
        LOG.debug('grub: moved %s out of the way', ci_cfg)
        shutil.move(ci_cfg, ci_cfg + '.disabled')


def get_carryover_params(distroinfo):
    # return a string to append to installed systems boot parameters
    # it may include a '--' after a '---'
    # see LP: 1402042 for some history here.
    # this is similar to 'user-params' from d-i
    cmdline = util.load_file('/proc/cmdline')
    preferred_sep = '---'  # KERNEL_CMDLINE_COPY_TO_INSTALL_SEP
    legacy_sep = '--'

    def wrap(sep):
        return ' ' + sep + ' '

    sections = []
    if wrap(preferred_sep) in cmdline:
        sections = cmdline.split(wrap(preferred_sep))
    elif wrap(legacy_sep) in cmdline:
        sections = cmdline.split(wrap(legacy_sep))
    else:
        extra = ""
        lead = cmdline

    if sections:
        lead = sections[0]
        extra = " ".join(sections[1:])

    carry_extra = []
    if extra:
        for tok in extra.split():
            if re.match(r'(BOOTIF=.*|initrd=.*|BOOT_IMAGE=.*)', tok):
                continue
            carry_extra.append(tok)

    carry_lead = []
    for tok in lead.split():
        if tok in carry_extra:
            continue
        if tok.startswith('console='):
            carry_lead.append(tok)

    # always append rd.auto=1 for redhat family
    if distroinfo.family == distro.DISTROS.redhat:
        carry_extra.append('rd.auto=1')

    return carry_lead + carry_extra


def replace_grub_cmdline_linux_default(target, new_args):
    # we always update /etc/default/grub to avoid "hiding" the override in
    # a grub.d directory.
    newcontent = 'GRUB_CMDLINE_LINUX_DEFAULT="%s"' % " ".join(new_args)
    target_grubconf = target_path(target, '/etc/default/grub')
    content = ""
    if os.path.exists(target_grubconf):
        content = util.load_file(target_grubconf)
    existing = re.search(
        r'GRUB_CMDLINE_LINUX_DEFAULT=.*', content, re.MULTILINE)
    if existing:
        omode = 'w+'
        updated_content = content[:existing.start()]
        updated_content += newcontent
        updated_content += content[existing.end():]
    else:
        omode = 'a+'
        updated_content = newcontent + '\n'

    util.write_file(target_grubconf, updated_content, omode=omode)
    LOG.debug('updated %s to set: %s', target_grubconf, newcontent)


def write_grub_config(target, grubcfg, grub_conf, new_params):
    replace_default = config.value_as_boolean(
        grubcfg.get('replace_linux_default', True))
    if replace_default:
        replace_grub_cmdline_linux_default(target, new_params)

    probe_os = config.value_as_boolean(
        grubcfg.get('probe_additional_os', False))
    if not probe_os:
        probe_content = [
            ('# Curtin disable grub os prober that might find other '
             'OS installs.'),
            'GRUB_DISABLE_OS_PROBER="true"',
            '']
        util.write_file(target_path(target, grub_conf),
                        "\n".join(probe_content), omode='a+')

    # if terminal is present in config, but unset, then don't
    grub_terminal = grubcfg.get('terminal', 'console')
    if not isinstance(grub_terminal, str):
        raise ValueError("Unexpected value %s for 'terminal'. "
                         "Value must be a string" % grub_terminal)
    if not grub_terminal.lower() == "unmodified":
        terminal_content = [
            '# Curtin configured GRUB_TERMINAL value',
            'GRUB_TERMINAL="%s"' % grub_terminal]
        util.write_file(target_path(target, grub_conf),
                        "\n".join(terminal_content), omode='a+')


def find_efi_loader(target, bootid):
    efi_path = '/boot/efi/EFI'
    possible_loaders = [
        os.path.join(efi_path, bootid, 'shimx64.efi'),
        os.path.join(efi_path, 'BOOT', 'BOOTX64.EFI'),
        os.path.join(efi_path, bootid, 'grubx64.efi'),
    ]
    for loader in possible_loaders:
        tloader = target_path(target, path=loader)
        if os.path.exists(tloader):
            LOG.debug('find_efi_loader: found %s', loader)
            return loader
    return None


def get_efi_disk_part(devices):
    for disk in devices:
        (parent, partnum) = block.get_blockdev_for_partition(disk)
        if partnum:
            return (parent, partnum)

    return (None, None)


def get_grub_install_command(uefi, distroinfo, target):
    grub_install_cmd = 'grub-install'
    if distroinfo.family == distro.DISTROS.debian:
        # prefer grub-multi-install if present
        if uefi and os.path.exists(target_path(target, GRUB_MULTI_INSTALL)):
            grub_install_cmd = GRUB_MULTI_INSTALL
    elif distroinfo.family == distro.DISTROS.redhat:
        grub_install_cmd = 'grub2-install'

    LOG.debug('Using grub install command: %s', grub_install_cmd)
    return grub_install_cmd


def gen_uefi_install_commands(grub_name, grub_target, grub_cmd, update_nvram,
                              distroinfo, devices, target):
    install_cmds = [['efibootmgr', '-v']]
    post_cmds = []
    bootid = distroinfo.variant
    efidir = '/boot/efi'
    if distroinfo.family == distro.DISTROS.debian:
        install_cmds.append(['dpkg-reconfigure', grub_name])
        install_cmds.append(['update-grub'])
    elif distroinfo.family == distro.DISTROS.redhat:
        loader = find_efi_loader(target, bootid)
        if loader and update_nvram:
            grub_cmd = None  # don't install just add entry
            efi_disk, efi_part_num = get_efi_disk_part(devices)
            install_cmds.append(['efibootmgr', '--create', '--write-signature',
                                 '--label', bootid, '--disk', efi_disk,
                                 '--part', efi_part_num, '--loader', loader])
            post_cmds.append(['grub2-mkconfig', '-o',
                              '/boot/efi/EFI/%s/grub.cfg' % bootid])
        else:
            post_cmds.append(['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'])
    else:
        raise ValueError("Unsupported os family for grub "
                         "install: %s" % distroinfo.family)

    if grub_cmd == GRUB_MULTI_INSTALL:
        # grub-multi-install is called with no arguments
        install_cmds.append([grub_cmd])
    elif grub_cmd:
        install_cmds.append(
            [grub_cmd, '--target=%s' % grub_target,
             '--efi-directory=%s' % efidir, '--bootloader-id=%s' % bootid,
             '--recheck'] + ([] if update_nvram else ['--no-nvram']))

    # check efi boot menu before and after
    post_cmds.append(['efibootmgr', '-v'])

    return (install_cmds, post_cmds)


def gen_install_commands(grub_name, grub_cmd, distroinfo, devices,
                         rhel_ver=None):
    install_cmds = []
    post_cmds = []
    if distroinfo.family == distro.DISTROS.debian:
        install_cmds.append(['dpkg-reconfigure', grub_name])
        install_cmds.append(['update-grub'])
    elif distroinfo.family == distro.DISTROS.redhat:
        if rhel_ver in ["7", "8"]:
            post_cmds.append(
                ['grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'])
        else:
            raise ValueError('Unsupported "rhel_ver" value: %s' % rhel_ver)
    else:
        raise ValueError("Unsupported os family for grub "
                         "install: %s" % distroinfo.family)
    for dev in devices:
        install_cmds.append([grub_cmd, dev])

    return (install_cmds, post_cmds)


def check_target_arch_machine(target, arch=None, machine=None, uefi=None):
    """ Check target arch and machine type are grub supported. """
    if not arch:
        arch = distro.get_architecture(target=target)

    if not machine:
        machine = platform.machine()

    errmsg = "Grub is not supported on arch=%s machine=%s" % (arch, machine)
    # s390x uses zipl
    if arch == "s390x":
        raise RuntimeError(errmsg)

    # As a rule, ARMv7 systems don't use grub. This may change some
    # day, but for now, assume no. They do require the initramfs
    # to be updated, and this also triggers boot loader setup via
    # flash-kernel.
    if (machine.startswith('armv7') or
            machine.startswith('s390x') or
            machine.startswith('aarch64') and not uefi):
        raise RuntimeError(errmsg)


def install_grub(devices, target, uefi=None, grubcfg=None):
    """Install grub to devices inside target chroot.

    :param: devices: List of block device paths to install grub upon.
    :param: target: A string specifying the path to the chroot mountpoint.
    :param: uefi: A boolean set to True if system is UEFI bootable otherwise
                  False.
    :param: grubcfg: An config dict with grub config options.
    """

    if not devices:
        raise ValueError("Invalid parameter 'devices': %s" % devices)

    if not target:
        raise ValueError("Invalid parameter 'target': %s" % target)

    LOG.debug("installing grub to target=%s devices=%s [replace_defaults=%s]",
              target, devices, grubcfg.get('replace_default'))
    update_nvram = config.value_as_boolean(grubcfg.get('update_nvram', False))
    distroinfo = distro.get_distroinfo(target=target)
    target_arch = distro.get_architecture(target=target)
    rhel_ver = (distro.rpm_get_dist_id(target)
                if distroinfo.family == distro.DISTROS.redhat else None)

    check_target_arch_machine(target, arch=target_arch, uefi=uefi)
    grub_name, grub_target = get_grub_package_name(target_arch, uefi, rhel_ver)
    grub_conf = get_grub_config_file(target, distroinfo.family)
    new_params = get_carryover_params(distroinfo)
    prepare_grub_dir(target, grub_conf)
    write_grub_config(target, grubcfg, grub_conf, new_params)
    grub_cmd = get_grub_install_command(uefi, distroinfo, target)
    if uefi:
        install_cmds, post_cmds = gen_uefi_install_commands(
            grub_name, grub_target, grub_cmd, update_nvram, distroinfo,
            devices, target)
    else:
        install_cmds, post_cmds = gen_install_commands(
            grub_name, grub_cmd, distroinfo, devices, rhel_ver)

    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'

    LOG.debug('Grub install cmds:\n%s', str(install_cmds + post_cmds))
    with util.ChrootableTarget(target) as in_chroot:
        for cmd in install_cmds + post_cmds:
            in_chroot.subp(cmd, env=env, capture=True)


def install_grub_main(args):
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
    uefi = util.is_uefi_bootable()
    grubcfg = cfg.get('grub')
    with events.ReportEventStack(
            name=stack_prefix, reporting_enabled=True, level="INFO",
            description="Installing grub to target devices"):
        install_grub(args.devices, target, uefi=uefi, grubcfg=grubcfg)
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, install_grub_main)

# vi: ts=4 expandtab syntax=python
