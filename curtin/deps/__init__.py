#   Copyright (C) 2015 Canonical Ltd.
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
import os
import sys

from curtin.util import (which, install_packages, lsb_release,
                         ProcessExecutionError)

REQUIRED_IMPORTS = [
    # import string to execute, python2 package, python3 package
    ('import yaml', 'python-yaml', 'python3-yaml'),
]

REQUIRED_EXECUTABLES = [
    # executable in PATH, package
    ('file', 'file'),
    ('lvcreate', 'lvm2'),
    ('mdadm', 'mdadm'),
    ('mkfs.btrfs', 'btrfs-tools'),
    ('mkfs.ext4', 'e2fsprogs'),
    ('mkfs.xfs', 'xfsprogs'),
    ('partprobe', 'parted'),
    ('sgdisk', 'gdisk'),
    ('udevadm', 'udev'),
]

if lsb_release()['codename'] == "precise":
    REQUIRED_IMPORTS.append(
        ('import oauth.oauth', 'python-oauth', None),)
else:
    REQUIRED_EXECUTABLES.append(('make-bcache', 'bcache-tools',))
    REQUIRED_IMPORTS.append(
        ('import oauthlib.oauth1', 'python-oauthlib', 'python3-oauthlib'),)


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


def find_missing_deps():
    return check_executables() + check_imports()


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
        install_packages(missing_pkgs, allow_daemons=allow_daemons)
    except ProcessExecutionError as e:
        sys.stderr.write("%s\n" % e)
        ret = e.exit_code

    return ret


# vi: ts=4 expandtab syntax=python
