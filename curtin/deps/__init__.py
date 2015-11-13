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
import sys
import subprocess

from curtin.util import which

REQUIRED_IMPORTS = [
    # import string to execute, python2 package, python3 package
    ('import yaml', 'python-yaml', 'python3-yaml'),
]

REQUIRED_EXECUTABLES = [
    # executable in PATH, package
    ('sgdisk', 'gdisk'),
    ('mdadm', 'mdadm'),
    ('lvcreate', 'lvm2'),
]

try:
    __lsb_rel = subprocess.check_output(['lsb_release', '-sc']).strip()
    if __lsb_rel != 'precise':
        REQUIRED_EXECUTABLES.append(('make-bcache', 'bcache-utils',))
except:
    pass


class MissingDeps(Exception):
    def __init__(self, message, deps):
        self.message = message
        if isinstance(deps, str):
            deps = [deps]
        self.deps = deps

    def __str__(self):
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
        raise MissingDeps("Missing program '%s' from '%s'.", pkg)


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


# vi: ts=4 expandtab syntax=python
