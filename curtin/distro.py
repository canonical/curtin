# This file is part of curtin. See LICENSE file for copyright and license info.
from collections import namedtuple
from contextlib import contextmanager
import os
import re
import textwrap
from typing import Optional, Sequence

from .paths import target_path
from .util import (
    ChrootableTarget,
    load_file,
    load_shell_content,
    ProcessExecutionError,
    set_unexecutable,
    string_types,
    subp,
    which
)
from .log import LOG

DistroInfo = namedtuple('DistroInfo', ('variant', 'family'))
DISTRO_NAMES = ['arch', 'centos', 'debian', 'fedora', 'freebsd', 'gentoo',
                'ol', 'opensuse', 'redhat', 'rhel', 'sles', 'suse', 'ubuntu',
                'rocky', 'almalinux', 'mariner']


# python2.7 lacks  PEP 435, so we must make use an alternative for py2.7/3.x
# https://stackoverflow.com/questions/36932/how-can-i-represent-an-enum-in-python
def distro_enum(*distros):
    return namedtuple('Distros', distros)(*distros)


DISTROS = distro_enum(*DISTRO_NAMES)

OS_FAMILIES = {
    DISTROS.debian: [DISTROS.debian, DISTROS.ubuntu],
    DISTROS.redhat: [DISTROS.centos, DISTROS.fedora, DISTROS.ol,
                     DISTROS.redhat, DISTROS.rhel, DISTROS.rocky,
                     DISTROS.almalinux, DISTROS.mariner],
    DISTROS.gentoo: [DISTROS.gentoo],
    DISTROS.freebsd: [DISTROS.freebsd],
    DISTROS.suse: [DISTROS.opensuse, DISTROS.sles, DISTROS.suse],
    DISTROS.arch: [DISTROS.arch],
}

# invert the mapping for faster lookup of variants
DISTRO_TO_OSFAMILY = (
    {variant: family for family, variants in OS_FAMILIES.items()
     for variant in variants})

_LSB_RELEASE = {}


def name_to_distro(distname):
    try:
        return DISTROS[DISTROS.index(distname)]
    except (IndexError, AttributeError):
        LOG.error('Unknown distro name: %s', distname)


def lsb_release(target=None):
    if target_path(target) != "/":
        # do not use or update cache if target is provided
        return _lsb_release(target)

    if not _LSB_RELEASE:
        data = _lsb_release()
        _LSB_RELEASE.update(data)
    return _LSB_RELEASE


def os_release(target=None):
    data = {}
    os_release = target_path(target, 'etc/os-release')
    if os.path.exists(os_release):
        data = load_shell_content(load_file(os_release),
                                  add_empty=False, empty_val=None)
    if not data:
        for relfile in [target_path(target, rel) for rel in
                        ['etc/centos-release', 'etc/redhat-release']]:
            data = _parse_redhat_release(release_file=relfile, target=target)
            if data:
                break

    return data


def _parse_redhat_release(release_file=None, target=None):
    """Return a dictionary of distro info fields from /etc/redhat-release.

    Dict keys will align with /etc/os-release keys:
        ID, VERSION_ID, VERSION_CODENAME
    """

    if not release_file:
        release_file = target_path('etc/redhat-release')
    if not os.path.exists(release_file):
        return {}
    redhat_release = load_file(release_file)
    redhat_regex = (
        r'(?P<name>.+) release (?P<version>[\d\.]+) '
        r'\((?P<codename>[^)]+)\)')
    match = re.match(redhat_regex, redhat_release)
    if match:
        group = match.groupdict()
        group['name'] = group['name'].lower().partition(' linux')[0]
        if group['name'] == 'red hat enterprise':
            group['name'] = 'redhat'
        return {'ID': group['name'], 'VERSION_ID': group['version'],
                'VERSION_CODENAME': group['codename']}
    return {}


def get_distroinfo(target=None):
    variant_os_release = os_release(target=target)
    variant_name = variant_os_release['ID']
    try:
        variant = name_to_distro(variant_name)
    except ValueError:
        for variant_name in variant_os_release["ID_LIKE"].split():
            try:
                variant = name_to_distro(variant_name)
                break
            except ValueError:
                pass
        else:
            raise ValueError("Unknown distro: %s" % variant_os_release['ID'])
    family = DISTRO_TO_OSFAMILY.get(variant)
    return DistroInfo(variant, family)


def get_distro(target=None):
    distinfo = get_distroinfo(target=target)
    return distinfo.variant


def get_osfamily(target=None):
    distinfo = get_distroinfo(target=target)
    return distinfo.family


def is_ubuntu_core(target=None):
    """Check if any Ubuntu-Core specific directory is present at target"""
    return any([is_ubuntu_core_16(target),
                is_ubuntu_core_18(target),
                is_ubuntu_core_20(target)])


def is_ubuntu_core_16(target=None):
    """Check if Ubuntu-Core 16 specific directory is present at target"""
    return os.path.exists(target_path(target, 'system-data/var/lib/snapd'))


def is_ubuntu_core_18(target=None):
    """Check if Ubuntu-Core 18 specific directory is present at target"""
    return is_ubuntu_core_16(target)


def is_ubuntu_core_20(target=None):
    """Check if Ubuntu-Core 20 specific directory is present at target"""
    return os.path.exists(target_path(target, 'snaps'))


def is_centos(target=None):
    """Check if CentOS specific file is present at target"""
    return os.path.exists(target_path(target, 'etc/centos-release'))


def is_rhel(target=None):
    """Check if RHEL specific file is present at target"""
    return os.path.exists(target_path(target, 'etc/redhat-release'))


def _lsb_release(target=None):
    fmap = {'Codename': 'codename', 'Description': 'description',
            'Distributor ID': 'id', 'Release': 'release'}

    data = {}
    try:
        out, _ = subp(['lsb_release', '--all'], capture=True, target=target)
        for line in out.splitlines():
            fname, _, val = line.partition(":")
            if fname in fmap:
                data[fmap[fname]] = val.strip()
        missing = [k for k in fmap.values() if k not in data]
        if len(missing):
            LOG.warn("Missing fields in lsb_release --all output: %s",
                     ','.join(missing))

    except ProcessExecutionError as err:
        LOG.warn("Unable to get lsb_release --all: %s", err)
        data = {v: "UNAVAILABLE" for v in fmap.values()}

    return data


def apt_update(target=None, env=None):
    LOG.debug("Updating apt sources in %s", target)
    if env is None:
        env = os.environ.copy()

    restore_perms = []

    try:
        # this file gets executed on apt-get update sometimes. (LP: #1527710)
        motd_update = target_path(
            target, "/usr/lib/update-notifier/update-motd-updates-available")
        pmode = set_unexecutable(motd_update)
        if pmode is not None:
            restore_perms.append((motd_update, pmode),)

        update_cmd = [
            'apt-get', '--quiet',
            '--option=Acquire::Languages=none',
            'update']

        # do not using 'run_apt_command' so we can use 'retries' to subp
        with ChrootableTarget(target, allow_daemons=True) as inchroot:
            inchroot.subp(update_cmd, env=env, retries=(1, 2, 3))
    finally:
        for fname, perms in restore_perms:
            os.chmod(fname, perms)


def run_apt_command(mode, args=None, opts=None, env=None, target=None,
                    execute=True, allow_daemons=False, clean=True,
                    download_retries: Optional[Sequence[int]] = None,
                    download_only=False, assume_downloaded=False):
    defopts = ['--quiet', '--assume-yes',
               '--option=Dpkg::options::=--force-unsafe-io',
               '--option=Dpkg::Options::=--force-confold']
    if args is None:
        args = []

    if opts is None:
        opts = []

    if env is None:
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    if which('eatmydata', target=target):
        emd = ['eatmydata']
    else:
        emd = []

    cmd = emd + ['apt-get'] + defopts + opts + [mode] + args
    if not execute:
        return env, cmd

    if not assume_downloaded:
        apt_update(target, env=env)
    if mode in ['dist-upgrade', 'install', 'upgrade']:
        cmd_rv = apt_install(mode, args, opts=opts, env=env, target=target,
                             allow_daemons=allow_daemons,
                             download_retries=download_retries,
                             download_only=download_only,
                             assume_downloaded=assume_downloaded)
        if clean and not download_only:
            with ChrootableTarget(
                    target, allow_daemons=allow_daemons) as inchroot:
                inchroot.subp(['apt-get', 'clean'])
        return cmd_rv

    with ChrootableTarget(target, allow_daemons=allow_daemons) as inchroot:
        return inchroot.subp(cmd, env=env)


def apt_install(mode, packages=None, opts=None, env=None, target=None,
                allow_daemons=False,
                download_retries: Optional[Sequence[int]] = None,
                download_only=False, assume_downloaded=False):
    """ Install or upgrade a set or all the packages using apt-get. """
    defopts = ['--quiet', '--assume-yes',
               '--option=Dpkg::options::=--force-unsafe-io',
               '--option=Dpkg::Options::=--force-confold']
    if packages is None:
        packages = []

    if opts is None:
        opts = []

    if mode not in ['install', 'upgrade', 'dist-upgrade']:
        raise ValueError(
            'Unsupported mode "%s" for apt package install/upgrade' % mode)

    if download_only and assume_downloaded:
        raise ValueError(
            'download-only and assume-downloaded options are incompatible')

    # download first, then install/upgrade from cache
    cmd = ['apt-get'] + defopts + opts + [mode]
    dl_opts = ['--download-only']
    # NOTE: it would feel natural to use --no-download here but sadly apt-get
    # can fail with "Internal Error, Pathname to install is not absolute [...]"
    # when packages were retrieved from the cdrom and not downloaded from the
    # Internet.
    inst_opts = []

    with ChrootableTarget(target, allow_daemons=allow_daemons) as inchroot:
        if not assume_downloaded:
            cmd_rv = inchroot.subp(cmd + dl_opts + packages, env=env,
                                   retries=download_retries)
        if not download_only:
            cmd_rv = inchroot.subp(cmd + inst_opts + packages, env=env)

    return cmd_rv


def run_yum_command(mode, args=None, opts=None, env=None, target=None,
                    execute=True, allow_daemons=False,
                    download_retries: Optional[Sequence[int]] = None,
                    download_only=False, assume_downloaded=False):
    defopts = ['--assumeyes', '--quiet']

    if args is None:
        args = []

    if opts is None:
        opts = []

    # dnf is a drop in replacement for yum. On newer RH based systems yum
    # is just a sym link to dnf.
    if which('dnf', target=target):
        cmd = ['dnf']
    else:
        cmd = ['yum']
    cmd += defopts + opts + [mode] + args
    if not execute:
        return env, cmd

    if mode in ["install", "update", "upgrade"]:
        return yum_install(mode, args, opts=opts, env=env, target=target,
                           allow_daemons=allow_daemons,
                           download_retries=download_retries,
                           download_only=download_only,
                           assume_downloaded=assume_downloaded)

    with ChrootableTarget(target, allow_daemons=allow_daemons) as inchroot:
        return inchroot.subp(cmd, env=env)


def yum_install(mode, packages=None, opts=None, env=None, target=None,
                allow_daemons=False,
                download_retries: Optional[Sequence[int]] = None,
                download_only=False, assume_downloaded=False):

    defopts = ['--assumeyes', '--quiet']

    if packages is None:
        packages = []

    if opts is None:
        opts = []

    if download_retries is None:
        download_retries = [1] * 10

    if mode not in ['install', 'update', 'upgrade']:
        raise ValueError(
            'Unsupported mode "%s" for yum package install/upgrade' % mode)

    if download_only and assume_downloaded:
        raise ValueError(
            'download-only and assume-downloaded options are incompatible')

    # dnf is a drop in replacement for yum. On newer RH based systems yum
    # is just a sym link to dnf.
    if which('dnf', target=target):
        cmd = ['dnf']
    else:
        cmd = ['yum']
    # download first, then install/upgrade from cache
    cmd += defopts + opts + [mode]
    dl_opts = ['--downloadonly', '--setopt=keepcache=1']
    inst_opts = ['--cacheonly']

    # rpm requires /dev /sys and /proc be mounted, use ChrootableTarget
    with ChrootableTarget(target, allow_daemons=allow_daemons) as inchroot:
        if not assume_downloaded:
            cmd_rv = inchroot.subp(cmd + dl_opts + packages,
                                   env=env, retries=download_retries)
        if not download_only:
            cmd_rv = inchroot.subp(cmd + inst_opts + packages, env=env)

    return cmd_rv


def rpm_get_dist_id(target=None):
    """Use rpm command to extract the '%rhel' distro macro which returns
       the major os version id (6, 7, 8).  This works for centos or rhel
    """
    # rpm requires /dev /sys and /proc be mounted, use ChrootableTarget
    with ChrootableTarget(target) as in_chroot:
        dist, _ = in_chroot.subp(['rpm', '-E', '%rhel'], capture=True)
    return dist.rstrip()


def run_zypper_command(mode, args=None, opts=None, env=None, target=None,
                       execute=True, allow_daemons=False,
                       download_retries: Optional[Sequence[int]] = None,
                       download_only=False, assume_downloaded=False):
    defopts = ['--non-interactive', '--non-interactive-include-reboot-patches',
               '--quiet']

    if args is None:
        args = []

    if opts is None:
        opts = []

    cmd = ['zypper']
    cmd += defopts + opts + [mode] + args
    if not execute:
        return env, cmd

    # TODO add support for retried downloads, download-only and no-download.

    with ChrootableTarget(target, allow_daemons=allow_daemons) as inchroot:
        return inchroot.subp(cmd, env=env)


def system_upgrade(opts=None, target=None, env=None, allow_daemons=False,
                   osfamily=None,
                   download_retries: Optional[Sequence[int]] = None):
    LOG.debug("Upgrading system in %s", target)

    if not osfamily:
        osfamily = get_osfamily(target=target)

    distro_cfg = {
        DISTROS.debian: {'function': run_apt_command,
                         'subcommands': ('dist-upgrade', 'autoremove')},
        DISTROS.redhat: {'function': run_yum_command,
                         'subcommands': ('upgrade',)},
        DISTROS.suse: {'function': run_zypper_command,
                       'subcommands': ('refresh', 'update', 'purge-kernels',)},
    }
    if osfamily not in distro_cfg:
        raise ValueError('Distro "%s" does not have system_upgrade support',
                         osfamily)

    for mode in distro_cfg[osfamily]['subcommands']:
        ret = distro_cfg[osfamily]['function'](
                mode, opts=opts, target=target,
                env=env, allow_daemons=allow_daemons,
                download_retries=download_retries)
    return ret


def install_packages(pkglist, osfamily=None, opts=None, target=None, env=None,
                     allow_daemons=False,
                     download_retries: Optional[Sequence[int]] = None,
                     download_only=False, assume_downloaded=False):
    if isinstance(pkglist, str):
        pkglist = [pkglist]

    if not osfamily:
        osfamily = get_osfamily(target=target)

    installer_map = {
        DISTROS.debian: run_apt_command,
        DISTROS.redhat: run_yum_command,
        DISTROS.suse: run_zypper_command,
    }

    install_cmd = installer_map.get(osfamily)
    if not install_cmd:
        raise ValueError('No package install command for distro: %s' %
                         osfamily)

    return install_cmd('install', args=pkglist, opts=opts, target=target,
                       env=env, allow_daemons=allow_daemons,
                       download_retries=download_retries,
                       download_only=download_only,
                       assume_downloaded=assume_downloaded)


def dpkg_query_list_kernels(target=None):
    target = target_path(target)
    cmd = [
        "dpkg-query",
        "--show",
        "--showformat=${Package}/${db:Status-Abbrev}/${Provides}\n",
    ]

    out, _ = subp(cmd, capture=True, target=target)
    results = []
    for line in out.splitlines():
        package, status, provides = line.strip().split("/")
        # status abbreviation is 3 columns, 3rd is error state
        if status != "ii ":
            continue
        provide_packages = provides.split(", ")
        if "linux-image" in provide_packages:
            results.append(package)
    return results


def list_kernels(osfamily=None, target=None):
    if not osfamily:
        osfamily = get_osfamily(target=target)

    distro_cfg = {
        DISTROS.debian: dpkg_query_list_kernels
    }

    list_kernels_cmd = distro_cfg.get(osfamily)
    if list_kernels_cmd is None:
        raise ValueError('No package purge command for distro: %s' %
                         osfamily)

    return list_kernels_cmd(target=target)


@contextmanager
def ensure_one_kernel(osfamily=None, target=None):
    """ensure_one_kernel is a context manager that evalutates the state of
    installed kernels, before and after doing package operations.  With that
    information, kernels that only appear before and not after are removed.
    """
    before = set(list_kernels(osfamily=osfamily, target=target))
    yield

    LOG.debug('ensure_one_kernel: kernels before install %s', before)
    if not bool(before):
        LOG.debug('No kernels to remove - no kernels preinstalled')
        return

    # the second part of ensure_one_kernel is intended to be run after any
    # kernels we're installing have been installed.  We expect the list of
    # kernels to grow as a result.  So if the set has not changed, that means
    # that the kernel we asked to install was installed already, so we
    # shouldn't be removing one.  This should work fine for a single kernel
    # being preinstalled, but will fail to remove in the case of 2 kernels
    # preinstalled but only one of them is intended.
    after = set(list_kernels(osfamily=osfamily, target=target))
    LOG.debug('ensure_one_kernel: kernels after install %s', after)
    if not bool(after - before):
        LOG.debug(
            'No kernels to remove - kernel to install was already installed'
        )
        return

    purge_packages(list(before), target=target)


def purge_all_kernels(osfamily=None, target=None):
    kernels = list_kernels(osfamily=osfamily, target=target)
    if not bool(kernels):
        LOG.debug('No kernels to remove - no kernels preinstalled')
        return

    purge_packages(kernels, target=target)


def purge_packages(pkglist, osfamily=None, opts=None, target=None, env=None):
    if isinstance(pkglist, str):
        pkglist = [pkglist]

    LOG.debug('Removing packages %s', pkglist)

    if not osfamily:
        osfamily = get_osfamily(target=target)

    distro_cfg = {
        DISTROS.debian: {'function': run_apt_command,
                         'subcommands': ('purge', 'autoremove')},
    }

    purge_cmd = distro_cfg.get(osfamily)
    if not purge_cmd:
        raise ValueError('No package purge command for distro: %s' %
                         osfamily)

    for mode in distro_cfg[osfamily]['subcommands']:
        ret = distro_cfg[osfamily]['function'](
            mode,
            args=pkglist,
            opts=opts,
            target=target,
            env=env,
            assume_downloaded=True,
        )
    return ret


def has_pkg_available(pkg, target=None, osfamily=None):
    if not osfamily:
        osfamily = get_osfamily(target=target)

    if osfamily not in [DISTROS.debian, DISTROS.redhat, DISTROS.suse]:
        raise ValueError('has_pkg_available: unsupported distro family: %s',
                         osfamily)

    if osfamily == DISTROS.suse:
        out, _ = subp(['zypper', '--quiet', 'search',
                       '--match-exact', pkg], capture=True, target=target)
        return 'No matching items found.' not in out

    if osfamily == DISTROS.debian:
        out, _ = subp(['apt-cache', 'pkgnames'], capture=True, target=target)
        for item in out.splitlines():
            if pkg == item.strip():
                return True
        return False

    if osfamily == DISTROS.redhat:
        out, _ = run_yum_command('list', opts=['--cacheonly'])
        for item in out.splitlines():
            if item.lower().startswith(pkg.lower()):
                return True
        return False


def get_installed_packages(target=None):
    out = None
    if which('dpkg-query', target=target):
        (out, _) = subp(['dpkg-query', '--list'], target=target, capture=True)
    elif which('rpm', target=target):
        # rpm requires /dev /sys and /proc be mounted, use ChrootableTarget
        with ChrootableTarget(target) as in_chroot:
            (out, _) = in_chroot.subp(['rpm', '-qa', '--queryformat',
                                       'ii %{NAME} %{VERSION}-%{RELEASE}\n'],
                                      target=target, capture=True)
    if not out:
        raise ValueError('No package query tool')

    pkgs_inst = set()
    for line in out.splitlines():
        try:
            (state, pkg, other) = line.split(None, 2)
        except ValueError:
            continue
        if state.startswith("hi") or state.startswith("ii"):
            pkgs_inst.add(re.sub(":.*", "", pkg))

    return pkgs_inst


def has_pkg_installed(pkg, target=None):
    try:
        out, _ = subp(['dpkg-query', '--show', '--showformat',
                       '${db:Status-Abbrev}', pkg],
                      capture=True, target=target)
        return out.rstrip() == "ii"
    except ProcessExecutionError:
        return False


def parse_dpkg_version(raw, name=None, semx=None):
    """Parse a dpkg version string into various parts and calcualate a
       numerical value of the version for use in comparing package versions

       Native packages (without a '-'), will have the package version treated
       as the upstream version.

       returns a dictionary with fields:
          'epoch'
          'major' (int), 'minor' (int), 'micro' (int),
          'semantic_version' (int),
          'extra' (string), 'raw' (string), 'upstream' (string),
          'name' (present only if name is not None)
    """
    if not isinstance(raw, string_types):
        raise TypeError(
            "Invalid type %s for parse_dpkg_version" % raw.__class__)

    if semx is None:
        semx = (10000, 100, 1)

    raw_offset = 0
    if ':' in raw:
        epoch, _, upstream = raw.partition(':')
        raw_offset = len(epoch) + 1
    else:
        epoch = 0
        upstream = raw

    if "-" in raw[raw_offset:]:
        upstream = raw[raw_offset:].rsplit('-', 1)[0]
    else:
        # this is a native package, package version treated as upstream.
        upstream = raw[raw_offset:]

    match = re.search(r'[^0-9.]', upstream)
    if match:
        extra = upstream[match.start():]
        upstream_base = upstream[:match.start()]
    else:
        upstream_base = upstream
        extra = None

    toks = upstream_base.split(".", 3)
    if len(toks) == 4:
        major, minor, micro, extra = toks
    elif len(toks) == 3:
        major, minor, micro = toks
    elif len(toks) == 2:
        major, minor, micro = (toks[0], toks[1], 0)
    elif len(toks) == 1:
        major, minor, micro = (toks[0], 0, 0)

    version = {
        'epoch': int(epoch),
        'major': int(major),
        'minor': int(minor),
        'micro': int(micro),
        'extra': extra,
        'raw': raw,
        'upstream': upstream,
    }
    if name:
        version['name'] = name

    if semx:
        try:
            version['semantic_version'] = int(
                int(major) * semx[0] + int(minor) * semx[1] +
                int(micro) * semx[2])
        except (ValueError, IndexError):
            version['semantic_version'] = None

    return version


def get_package_version(pkg, target=None, semx=None):
    """Use dpkg-query to extract package pkg's version string
       and parse the version string into a dictionary
    """
    try:
        out, _ = subp(['dpkg-query', '--show', '--showformat',
                       '${Version}', pkg], capture=True, target=target)
        raw = out.rstrip()
        return parse_dpkg_version(raw, name=pkg, semx=semx)
    except ProcessExecutionError:
        return None


def fstab_header():
    return textwrap.dedent("""\
# /etc/fstab: static file system information.
#
# Use 'blkid' to print the universally unique identifier for a
# device; this may be used with UUID= as a more robust way to name devices
# that works even if disks are added and removed. See fstab(5).
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>""")


def dpkg_get_architecture(target=None):
    out, _ = subp(['dpkg', '--print-architecture'], capture=True,
                  target=target)
    return out.strip()


def rpm_get_architecture(target=None):
    # rpm requires /dev /sys and /proc be mounted, use ChrootableTarget
    with ChrootableTarget(target) as in_chroot:
        out, _ = in_chroot.subp(['rpm', '-E', '%_arch'], capture=True)
    return out.strip()


def get_architecture(target=None, osfamily=None):
    if not osfamily:
        osfamily = get_osfamily(target=target)

    if osfamily == DISTROS.debian:
        return dpkg_get_architecture(target=target)

    if osfamily in [DISTROS.redhat, DISTROS.suse]:
        return rpm_get_architecture(target=target)

    raise ValueError("Unhandled osfamily=%s" % osfamily)

# vi: ts=4 expandtab syntax=python
