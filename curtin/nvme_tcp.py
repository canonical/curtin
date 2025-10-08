# This file is part of curtin. See LICENSE file for copyright and license info.

'''Module that defines functions useful for dealing with NVMe/TCP'''

import contextlib
import json
import pathlib
import shlex
from typing import Any, Dict, Iterator, List, Set, Tuple

import yaml

from curtin.block import nvme
from curtin.log import LOG
from curtin.paths import target_path
from curtin import util


def _iter_nvme_tcp_controllers(cfg) -> Iterator[Dict[str, Any]]:
    for controller in nvme.get_nvme_controllers_from_config(cfg):
        if controller['transport'] == 'tcp':
            yield controller


def get_nvme_stas_controller_directives(cfg) -> Set[str]:
    """Parse the storage configuration and return a set of "controller ="
    directives to write in the [Controllers] section of a nvme-stas
    configuration file."""
    directives = set()
    for controller in _iter_nvme_tcp_controllers(cfg):
        controller_props = {
            'transport': 'tcp',
            'traddr': controller["tcp_addr"],
            'trsvcid': controller["tcp_port"],
        }

        props_str = ';'.join([f'{k}={v}' for k, v in controller_props.items()])
        directives.add(f'controller = {props_str}')

    return directives


def get_nvme_commands(cfg) -> List[Tuple[str]]:
    """Parse the storage configuration and return a set of commands
    to run to bring up the NVMe over TCP block devices."""
    commands: Set[Tuple[str]] = set()
    for controller in nvme.get_nvme_controllers_from_config(cfg):
        if controller['transport'] != 'tcp':
            continue

        commands.add((
            'nvme', 'connect-all',
            '--transport', 'tcp',
            '--traddr', controller['tcp_addr'],
            '--trsvcid', str(controller['tcp_port']),
        ))

    return sorted(commands)


def _iter_cfg_mounts(cfg) -> Iterator[Dict[str, Any]]:
    if 'storage' not in cfg or not isinstance(cfg['storage'], dict):
        return
    storage = cfg['storage']
    if 'config' not in storage or storage['config'] == 'disabled':
        return
    config = storage['config']
    for item in config:
        if item['type'] == 'mount':
            yield item


def _mount_item_requires_network(mount_item: Dict[str, Any]) -> bool:
    return '_netdev' in mount_item.get('options', '').split(',')


def need_network_in_initramfs(cfg) -> bool:
    """Parse the storage configuration and check if any of the mountpoints
    essential for booting requires network."""
    for item in _iter_cfg_mounts(cfg):
        if not _mount_item_requires_network(item):
            continue

        # We found a mountpoint that requires network. Let's check if it is
        # essential for booting.
        path = item['path']
        if path == '/' or path.startswith('/usr') or path.startswith('/var'):
            return True

    return False


def requires_firmware_support(cfg) -> bool:
    """Parse the storage configuration and check if the bootfs or ESP are on
    remote storage. If they are, we need firmware support to reach the
    initramfs.
    """
    rootfs_is_remote = False
    mounts_found = {'/boot': False, '/boot/efi': False}

    for item in _iter_cfg_mounts(cfg):
        path = item['path']
        if path == '/':
            rootfs_is_remote = _mount_item_requires_network(item)
        elif path in mounts_found.keys():
            mounts_found[path] = True
            if _mount_item_requires_network(item):
                # /boot or /boot/efi on remote storage mandates firmware
                # support. No need to continue checking other mounts.
                return True

    if not rootfs_is_remote:
        return False

    return not mounts_found['/boot']


def get_ip_commands(cfg) -> List[Tuple[str]]:
    """Look for the netplan configuration (supplied by subiquity using
    write_files directives) and attempt to extrapolate a set of 'ip' + 'dhcpcd'
    commands that would produce more or less the expected network
    configuration. At the moment, only trivial network configurations are
    supported, which are ethernet interfaces with or without DHCP and optional
    static routes."""
    commands: List[Tuple[str]] = []

    try:
        content = cfg['write_files']['etc_netplan_installer']['content']
    except KeyError:
        return []

    config = yaml.safe_load(content)

    try:
        ethernets = config['network']['ethernets']
    except KeyError:
        return []

    for ifname, ifconfig in ethernets.items():
        # Handle static IP addresses
        for address in ifconfig.get('addresses', []):
            commands.append(('ip', 'address', 'add', address, 'dev', ifname))

        # Handle DHCPv4 and DHCPv6
        dhcp4 = ifconfig.get('dhcp4', False)
        dhcp6 = ifconfig.get('dhcp6', False)
        if dhcp4 and dhcp6:
            commands.append(('dhcpcd', ifname))
        elif dhcp4:
            commands.append(('dhcpcd', '-4', ifname))
        elif dhcp6:
            commands.append(('dhcpcd', '-6', ifname))
        else:
            commands.append(('ip', 'link', 'set', ifname, 'up'))

        # Handle static routes
        for route in ifconfig.get('routes', []):
            cmd = ['ip', 'route', 'add', route['to']]
            with contextlib.suppress(KeyError):
                cmd += ['via', route['via']]
            if route.get('on-link', False):
                cmd += ['dev', ifname]
            commands.append(tuple(cmd))

    return commands


def dracut_add_systemd_network_cmdline(target: pathlib.Path) -> None:
    LOG.info('adding curtin-systemd-network-cmdline module to dracut')

    hook_contents = '''\
#!/bin/bash

type getcmdline > /dev/null 2>&1 || . /lib/dracut-lib.sh

/usr/lib/systemd/systemd-network-generator -- $(getcmdline)
'''
    module_setup_contents = '''\
#!/bin/bash

# called by dracut
depends() {
    echo systemd-networkd
    return 0
}

# called by dracut
install() {
    inst_hook pre-udev 99 "$moddir/networkd-cmdline.sh"
}
'''

    dracut_mods_dir = target / 'usr' / 'lib' / 'dracut' / 'modules.d'
    dracut_curtin_mod = dracut_mods_dir / '35curtin-systemd-network-cmdline'
    dracut_curtin_mod.mkdir(parents=True, exist_ok=True)

    hook = dracut_curtin_mod / 'networkd-cmdline.sh'
    with hook.open('w', encoding='utf-8') as fh:
        print(hook_contents, file=fh)
    hook.chmod(0o755)

    module_setup = dracut_curtin_mod / 'module-setup.sh'
    with module_setup.open('w', encoding='utf-8') as fh:
        print(module_setup_contents, file=fh)
    module_setup.chmod(0o755)


def configure_nvme_stas(cfg, target: pathlib.Path) -> None:
    LOG.info('writing nvme-stas configuration')

    controllers = get_nvme_stas_controller_directives(cfg)

    if not controllers:
        return

    stas_dir = target / 'etc' / 'stas'
    stas_dir.mkdir(parents=True, exist_ok=True)
    with (stas_dir / 'stafd-curtin.conf').open('w', encoding='utf-8') as fh:
        header = '''\
# This file was created by curtin.
'''
        print(header, file=fh)
        print('[Controllers]', file=fh)
        for controller in controllers:
            print(controller, file=fh)

    with contextlib.suppress(FileNotFoundError):
        (stas_dir / 'stafd.conf').replace(stas_dir / '.stafd.conf.bak')
    (stas_dir / 'stafd.conf').symlink_to('stafd-curtin.conf')


def initramfs_tools_configure(cfg, target: pathlib.Path) -> None:
    """Configure initramfs-tools for NVMe/TCP. This is a legacy approach where
    the network is hardcoded and nvme connect-all commands are manually
    crafted. However, this implementation does not require firmware support."""
    LOG.info('configuring initramfs-tools for NVMe over TCP')

    hook_contents = '''\
#!/bin/sh

PREREQ="udev"

prereqs()
{
    echo "$PREREQ"
}

case "$1" in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /usr/share/initramfs-tools/hook-functions

copy_exec /usr/sbin/nvme /usr/sbin
copy_file config /etc/nvme/hostid /etc/nvme/
copy_file config /etc/nvme/hostnqn /etc/nvme/
copy_file config /etc/curtin-nvme-over-tcp/network-up \\
    /etc/curtin-nvme-over-tcp/
copy_file config /etc/curtin-nvme-over-tcp/connect-nvme \\
    /etc/curtin-nvme-over-tcp/

manual_add_modules nvme-tcp
'''
    initramfs_tools_dir = target / 'etc' / 'initramfs-tools'

    initramfs_hooks_dir = initramfs_tools_dir / 'hooks'
    initramfs_hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = initramfs_hooks_dir / 'curtin-nvme-over-tcp'
    with hook.open('w', encoding='utf-8') as fh:
        print(hook_contents, file=fh)
    hook.chmod(0o755)

    bootscript_contents = '''\
#!/bin/sh

    PREREQ=""
prereqs() { echo "$PREREQ"; }
case "$1" in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /etc/curtin-nvme-over-tcp/network-up

modprobe nvme-tcp

. /etc/curtin-nvme-over-tcp/connect-nvme

'''

    initramfs_scripts_dir = initramfs_tools_dir / 'scripts'
    initramfs_init_premount_dir = initramfs_scripts_dir / 'init-premount'
    initramfs_init_premount_dir.mkdir(parents=True, exist_ok=True)
    bootscript = initramfs_init_premount_dir / 'curtin-nvme-over-tcp'
    with bootscript.open('w', encoding='utf-8') as fh:
        print(bootscript_contents, file=fh)
    bootscript.chmod(0o755)

    curtin_nvme_over_tcp_dir = target / 'etc' / 'curtin-nvme-over-tcp'
    curtin_nvme_over_tcp_dir.mkdir(parents=True, exist_ok=True)
    network_up_script = curtin_nvme_over_tcp_dir / 'network-up'
    connect_nvme_script = curtin_nvme_over_tcp_dir / 'connect-nvme'

    script_header = '''\
#!/bin/sh

# This file was created by curtin.
# If you make modifications to it, please remember to regenerate the initramfs
# using the command `update-initramfs -u`.
'''
    with open(connect_nvme_script, 'w', encoding='utf-8') as fh:
        print(script_header, file=fh)
        for cmd in get_nvme_commands(cfg):
            print(shlex.join(cmd), file=fh)

    with open(network_up_script, 'w', encoding='utf-8') as fh:
        print(script_header, file=fh)
        for cmd in get_ip_commands(cfg):
            print(shlex.join(cmd), file=fh)


class NetRuntimeError(RuntimeError):
    pass


def _iproute2(subcommand: List[str]):
    out, _ = util.subp(['ip', '-j'] + subcommand, capture=True)
    return json.loads(out)


def get_route_dest_ifname(dest: str) -> str:
    try:
        return _iproute2(['route', 'get', dest])[0]['dev']
    except (util.ProcessExecutionError, IndexError, KeyError) as exc:
        raise NetRuntimeError(f'could not determine route to {dest}') from exc


def get_iface_hw_addr(ifname: str) -> str:
    try:
        return _iproute2(['link', 'show', 'dev', ifname])[0]['address']
    except (util.ProcessExecutionError, IndexError, KeyError) as exc:
        raise NetRuntimeError(f'could not retrieve MAC for {ifname}') from exc


def dracut_adapt_netplan_config(cfg, *, target: pathlib.Path):
    '''Modify the netplan configuration (which has already been written to
    disk at this point) so that:
    * critical network interfaces (those handled by dracut) are not brought
    down during boot.
    * netplan does not panic if such an interface gets renamed by dracut (e.g.,
    to nbft0).
    '''
    ifnames: Set[str] = set()
    modified = False

    for controller in _iter_nvme_tcp_controllers(cfg):
        try:
            ifnames.add(get_route_dest_ifname(controller['tcp_addr']))
        except NetRuntimeError as exc:
            LOG.debug('%s, ignoring', exc)

    try:
        netplan_conf_path = pathlib.Path(
                target_path(
                    str(target),
                    cfg['write_files']['etc_netplan_installer']['path']))
    except KeyError:
        LOG.debug('could not find netplan configuration passed to cloud-init')
        return

    config = yaml.safe_load(netplan_conf_path.read_text())

    try:
        ethernets = config['network']['ethernets']
    except KeyError:
        LOG.debug('no ethernet interface in netplan configuration')
        return

    macaddresses: Dict[str, str] = {}

    for ifname in ifnames:
        try:
            macaddresses[ifname] = get_iface_hw_addr(ifname)
        except NetRuntimeError as exc:
            LOG.debug('%s, ignoring', exc)

    for ifname, ifconfig in ethernets.items():
        if ifname not in ifnames:
            continue
        # Ensure the interface is not brought down
        ifconfig['critical'] = True
        modified = True
        # Ensure we match the HW address and not the ifname.
        if 'match' not in ifconfig:
            ifconfig['match'] = {'macaddress': macaddresses[ifname]}

    if modified:
        netplan_conf_path.write_text(yaml.dump(config))
