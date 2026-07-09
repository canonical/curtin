# This file is part of curtin. See LICENSE file for copyright and license info.

"""Install Boot Loader Specification (BLS) Type 1 boot entries

This creates individual boot-entry files in /boot/loader/entries/ as
described in the UAPI Boot Loader Specification:
https://uapi-group.org/specifications/specs/boot_loader_specification/
"""

import os

from curtin import paths
from curtin import util
from curtin.log import LOG

# BLS architecture names that differ from the machine name
BLS_ARCH_MAP = {
    'x86_64': 'x86-64',
    'i686': 'x86',
    'i586': 'x86',
    'ppc64le': 'ppc64-le',
}

LOADER_DIR = '/boot/loader'
ENTRIES_DIR = LOADER_DIR + '/entries'


def build_loader_conf(timeout=50):
    """Build the content of the loader.conf file

    :param: timeout: Boot menu timeout in seconds
    """
    return f"""\
timeout {timeout}
"""


def get_bls_architecture(machine):
    """Return the BLS architecture name for the given machine

    :param: machine: A string specifying the target machine architecture.
    """
    return BLS_ARCH_MAP.get(machine, machine)


def get_machine_id(target):
    """Read the machine-id from the target filesystem

    :param: target: Path to the chroot mountpoint
    Return: machine-id string, or None if not available
    """
    machine_id_path = paths.target_path(target, '/etc/machine-id')
    if not os.path.exists(machine_id_path):
        return None
    return util.load_file(machine_id_path).strip()


def build_entry(fw_boot_dir, kernel_path, initrd_path,
                version, root_spec, machine_id=None,
                architecture=None, rescue=False):
    """Build the content of a single BLS entry file

    :param: fw_boot_dir: Firmware's view of the /boot directory
    :param: kernel_path: Kernel filename (e.g. vmlinuz-6.8.0-48-generic)
    :param: initrd_path: Initrd filename
    :param: version: Kernel version string
    :param: root_spec: Root device to pass to kernel
    :param: machine_id: Machine identifier from /etc/machine-id
    :param: architecture: BLS architecture name (e.g. x86-64, arm64)
    :param: rescue: If True, generate a rescue entry
    """
    title = f'Linux {version}'
    options = f'root={root_spec} ro'
    if rescue:
        title += ' (rescue target)'
        options += ' single'
    else:
        options += ' quiet'

    lines = [
        f'title {title}',
        f'version {version}',
    ]
    if machine_id:
        lines.append(f'machine-id {machine_id}')
    if architecture:
        lines.append(f'architecture {architecture}')
    lines += [
        f'linux {fw_boot_dir}/{kernel_path}',
        f'initrd {fw_boot_dir}/{initrd_path}',
        f'options {options}',
    ]

    return '\n'.join(lines) + '\n'


def build_entries(bootcfg, target, fw_boot_dir, root_spec, machine):
    """Build all BLS entry files

    :param: bootcfg: A boot-config dict
    :param: target: Path to the chroot mountpoint
    :param: fw_boot_dir: Firmware's view of the /boot directory
    :param: root_spec: Root device to pass to kernel
    :param: machine: A string specifying the target machine architecture.
    Return: list of (filename, content) tuples
    """
    machine_id = get_machine_id(target)
    architecture = get_bls_architecture(machine)
    entries = []
    for seq, (kernel_path, full_initrd_path, version) in enumerate(
            paths.get_kernel_list(target)):
        LOG.debug('P: Writing BLS config for %s...', kernel_path)
        initrd_path = os.path.basename(full_initrd_path)

        if 'default' in bootcfg.alternatives:
            fname = f'l{seq}-{version}.conf'
            content = build_entry(
                fw_boot_dir, kernel_path, initrd_path,
                version, root_spec, machine_id, architecture)
            entries.append((fname, content))

        if 'rescue' in bootcfg.alternatives:
            fname = f'l{seq}r-{version}.conf'
            content = build_entry(
                fw_boot_dir, kernel_path, initrd_path,
                version, root_spec, machine_id, architecture,
                rescue=True)
            entries.append((fname, content))

    return entries


def install_bls(bootcfg, target, fw_boot_dir, root_spec, machine):
    """Install BLS Type 1 boot entries to the target chroot

    :param: bootcfg: A boot-config dict
    :param: target: Path to the chroot mountpoint
    :param: fw_boot_dir: Firmware's view of the /boot directory
    :param: root_spec: Root device to pass to kernel
    :param: machine: A string specifying the target machine architecture.
    """
    LOG.debug(
        "P: Writing BLS entries, fw_boot_dir '%s' root_spec '%s'...",
        fw_boot_dir, root_spec)

    loader_path = paths.target_path(target, LOADER_DIR)
    entries_path = paths.target_path(target, ENTRIES_DIR)
    util.ensure_dir(entries_path)

    # Write loader.conf
    loader_conf = os.path.join(loader_path, 'loader.conf')
    with open(loader_conf, 'w', encoding='utf-8') as outf:
        outf.write(build_loader_conf())

    # Write individual entry files
    for fname, content in build_entries(
            bootcfg, target, fw_boot_dir, root_spec, machine):
        entry_path = os.path.join(entries_path, fname)
        with open(entry_path, 'w', encoding='utf-8') as outf:
            outf.write(content)
