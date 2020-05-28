# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys

from curtin.util import (
    ProcessExecutionError,
    is_uefi_bootable,
    subp,
    which,
)

from curtin.distro import (
    get_architecture,
    install_packages,
    lsb_release,
    )

REQUIRED_IMPORTS = [
    # import string to execute, python2 package, python3 package
    ('import yaml', 'python-yaml', 'python3-yaml'),
    ('import pyudev', 'python-pyudev', 'python3-pyudev'),
]

REQUIRED_EXECUTABLES = [
    # executable in PATH, package
    ('file', 'file'),
    ('lvcreate', 'lvm2'),
    ('mdadm', 'mdadm'),
    ('mkfs.vfat', 'dosfstools'),
    ('mkfs.btrfs', '^btrfs-(progs|tools)$'),
    ('mkfs.ext4', 'e2fsprogs'),
    ('mkfs.xfs', 'xfsprogs'),
    ('partprobe', 'parted'),
    ('sgdisk', 'gdisk'),
    ('udevadm', 'udev'),
    ('make-bcache', 'bcache-tools'),
    ('iscsiadm', 'open-iscsi'),
]

REQUIRED_KERNEL_MODULES = [
    # kmod name
]

if lsb_release()['codename'] == "precise":
    REQUIRED_IMPORTS.append(
        ('import oauth.oauth', 'python-oauth', None),)
else:
    REQUIRED_IMPORTS.append(
        ('import oauthlib.oauth1', 'python-oauthlib', 'python3-oauthlib'),)

# zfs is > trusty only
if not lsb_release()['codename'] in ["precise", "trusty"]:
    REQUIRED_EXECUTABLES.append(('zfs', 'zfsutils-linux'))
    REQUIRED_KERNEL_MODULES.append('zfs')

if not is_uefi_bootable() and 'arm' in get_architecture():
    REQUIRED_EXECUTABLES.append(('flash-kernel', 'flash-kernel'))


class MissingDeps(Exception):
    def __init__(self, message, deps):
        self.message = message
        if isinstance(deps, str) or deps is None:
            deps = [deps]
        self.deps = [d for d in deps if d is not None]
        self.fatal = None in deps

    def __str__(self):
        if self.fatal:
            if not len(self.deps):
                return self.message + " Unresolvable."
            return (self.message +
                    " Unresolvable.  Partially resolvable with packages: %s" %
                    ' '.join(self.deps))
        else:
            return self.message + " Install packages: %s" % ' '.join(self.deps)


def check_import(imports, py2pkgs, py3pkgs, message=None):
    import_group = imports
    if isinstance(import_group, str):
        import_group = [import_group]

    for istr in import_group:
        try:
            exec(istr)
            return
        except ImportError:
            pass

    if not message:
        if isinstance(imports, str):
            message = "Failed '%s'." % imports
        else:
            message = "Unable to do any of %s." % import_group

    if sys.version_info[0] == 2:
        pkgs = py2pkgs
    else:
        pkgs = py3pkgs

    raise MissingDeps(message, pkgs)


def check_executable(cmdname, pkg):
    if not which(cmdname):
        raise MissingDeps("Missing program '%s'." % cmdname, pkg)


def check_executables(executables=None):
    if executables is None:
        executables = REQUIRED_EXECUTABLES
    mdeps = []
    for exe, pkg in executables:
        try:
            check_executable(exe, pkg)
        except MissingDeps as e:
            mdeps.append(e)
    return mdeps


def check_imports(imports=None):
    if imports is None:
        imports = REQUIRED_IMPORTS

    mdeps = []
    for import_str, py2pkg, py3pkg in imports:
        try:
            check_import(import_str, py2pkg, py3pkg)
        except MissingDeps as e:
            mdeps.append(e)
    return mdeps


def check_kernel_modules(modules=None):
    if modules is None:
        modules = REQUIRED_KERNEL_MODULES

    # if we're missing any modules, install the full
    # linux-image package for this environment
    for kmod in modules:
        try:
            subp(['modinfo', '--filename', kmod], capture=True)
        except ProcessExecutionError:
            kernel_pkg = 'linux-image-%s' % os.uname()[2]
            return [MissingDeps('missing kernel module %s' % kmod, kernel_pkg)]

    return []


def find_missing_deps():
    return check_executables() + check_imports() + check_kernel_modules()


def install_deps(verbosity=False, dry_run=False, allow_daemons=True):
    errors = find_missing_deps()
    if len(errors) == 0:
        if verbosity:
            sys.stderr.write("No missing dependencies\n")
        return 0

    missing_pkgs = []
    for e in errors:
        missing_pkgs += e.deps

    deps_string = ' '.join(sorted(missing_pkgs))

    if dry_run:
        sys.stderr.write("Missing dependencies: %s\n" % deps_string)
        return 0

    if os.geteuid() != 0:
        sys.stderr.write("Missing dependencies: %s\n" % deps_string)
        sys.stderr.write("Package installation is not possible as non-root.\n")
        return 2

    if verbosity:
        sys.stderr.write("Installing %s\n" % deps_string)

    ret = 0
    try:
        install_packages(missing_pkgs, allow_daemons=allow_daemons,
                         opts=["--no-install-recommends"])
    except ProcessExecutionError as e:
        sys.stderr.write("%s\n" % e)
        ret = e.exit_code

    return ret

# vi: ts=4 expandtab syntax=python
