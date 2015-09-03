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
import os.path
import sys


class MissingDeps(Exception):
    def __init__(self, message, deps):
        self.message = message
        if isinstance(deps, str):
            deps = [deps]
        self.deps = deps

    def __str__(self):
        return self.message + " Install packages: %s" % ' '.join(self.deps)


def which(program):
    # Return path of program for execution if found in path
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    _fpath, _ = os.path.split(program)
    if _fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ.get("PATH", "").split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def check_imports(imports, py2pkgs, py3pkgs, message=None):
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


def check_yaml():
    check_imports('import yaml', py2pkgs='python-yaml', py3pkgs='python3-yaml')


def check_sgdisk():
    if not which('sgdisk'):
        raise MissingDeps("Missing program 'sgdisk'.", 'gdisk')


def find_missing_deps():
    mdeps = []
    for checker in CHECKS:
        try:
            checker()
        except MissingDeps as e:
            mdeps.append(e)

    return mdeps


CHECKS = [check_yaml, check_sgdisk]

# vi: ts=4 expandtab syntax=python
