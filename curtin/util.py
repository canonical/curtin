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

import errno
import os
import shutil
import subprocess
import sys
import tempfile
import time

from .log import LOG
from . import config

_INSTALLED_HELPERS_PATH = "/usr/lib/curtin/helpers"
_INSTALLED_MAIN = "/usr/bin/curtin"


def subp(args, data=None, rcs=None, env=None, capture=False, shell=False,
         logstring=False):
    if rcs is None:
        rcs = [0]
    try:

        if not logstring:
            LOG.debug(("Running command %s with allowed return codes %s"
                       " (shell=%s, capture=%s)"), args, rcs, shell, capture)
        else:
            LOG.debug(("Running hidden command to protect sensitive "
                       "input/output logstring: %s"), logstring)

        if not capture:
            stdout = None
            stderr = None
        else:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
        stdin = subprocess.PIPE
        sp = subprocess.Popen(args, stdout=stdout,
                              stderr=stderr, stdin=stdin,
                              env=env, shell=shell)
        (out, err) = sp.communicate(data)
        if isinstance(out, bytes):
            out = out.decode()
        if isinstance(err, bytes):
            err = err.decode()

    except OSError as e:
        raise ProcessExecutionError(cmd=args, reason=e)
    rc = sp.returncode  # pylint: disable=E1101
    if rc not in rcs:
        raise ProcessExecutionError(stdout=out, stderr=err,
                                    exit_code=rc,
                                    cmd=args)
    # Just ensure blank instead of none?? (iff capturing)
    if not out and capture:
        out = ''
    if not err and capture:
        err = ''
    return (out, err)


def load_command_environment(env=os.environ, strict=False):

    mapping = {'scratch': 'WORKING_DIR', 'fstab': 'OUTPUT_FSTAB',
               'interfaces': 'OUTPUT_INTERFACES', 'config': 'CONFIG',
               'target': 'TARGET_MOUNT_POINT'}

    if strict:
        missing = [k for k in mapping if k not in env]
        if len(missing):
            raise KeyError("missing environment vars: %s" % missing)

    return {k: env.get(v) for k, v in mapping.items()}


def load_command_config(args, state):
    if hasattr(args, 'config') and args.config is not None:
        cfg_file = args.config
    else:
        cfg_file = state.get('config', {})

    if not cfg_file:
        LOG.debug("config file was none!")
        cfg = {}
    else:
        cfg = config.load_config(cfg_file)
    return cfg


class BadUsage(Exception):
    pass


class ProcessExecutionError(IOError):

    MESSAGE_TMPL = ('%(description)s\n'
                    'Command: %(cmd)s\n'
                    'Exit code: %(exit_code)s\n'
                    'Reason: %(reason)s\n'
                    'Stdout: %(stdout)r\n'
                    'Stderr: %(stderr)r')

    def __init__(self, stdout=None, stderr=None,
                 exit_code=None, cmd=None,
                 description=None, reason=None):
        if not cmd:
            self.cmd = '-'
        else:
            self.cmd = cmd

        if not description:
            self.description = 'Unexpected error while running command.'
        else:
            self.description = description

        if not isinstance(exit_code, int):
            self.exit_code = '-'
        else:
            self.exit_code = exit_code

        if not stderr:
            self.stderr = ''
        else:
            self.stderr = stderr

        if not stdout:
            self.stdout = ''
        else:
            self.stdout = stdout

        if reason:
            self.reason = reason
        else:
            self.reason = '-'

        message = self.MESSAGE_TMPL % {
            'description': self.description,
            'cmd': self.cmd,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'reason': self.reason,
        }
        IOError.__init__(self, message)


class LogTimer(object):
    def __init__(self, logfunc, msg):
        self.logfunc = logfunc
        self.msg = msg

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, etype, value, trace):
        self.logfunc("%s took %0.3f seconds" %
                     (self.msg, time.time() - self.start))


def is_mounted(target, src=None, opts=None):
    # return whether or not src is mounted on target
    mounts = ""
    with open("/proc/mounts", "r") as fp:
        mounts = fp.read()

    for line in mounts.splitlines():
        if line.split()[1] == os.path.abspath(target):
            return True
    return False


def do_mount(src, target, opts=None):
    # mount src at target with opts and return True
    # if already mounted, return False
    if opts is None:
        opts = []
    if isinstance(opts, str):
        opts = [opts]

    if is_mounted(target, src, opts):
        return False

    ensure_dir(target)
    cmd = ['mount'] + opts + [src, target]
    subp(cmd)
    return True


def do_umount(mountpoint):
    if not is_mounted(mountpoint):
        return False
    subp(['umount', mountpoint])
    return True


def ensure_dir(path, mode=None):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    if mode is not None:
        os.chmod(path, mode)


def write_file(filename, content, mode=0o644, omode="w"):
    ensure_dir(os.path.dirname(filename))
    with open(filename, omode) as fp:
        fp.write(content)
    os.chmod(filename, mode)


def load_file(path, mode="r"):
    with open(path, mode) as fp:
        return fp.read()


def disable_daemons_in_root(target):
    contents = "\n".join(
        ['#!/bin/sh',
         '# see invoke-rc.d for exit codes. 101 is "do not run"',
         'while true; do',
         '   case "$1" in',
         '      -*) shift;;',
         '      makedev|x11-common) exit 0;;',
         '      *) exit 101;;',
         '   esac',
         'done',
         ''])

    fpath = os.path.join(target, "usr/sbin/policy-rc.d")

    if os.path.isfile(fpath):
        return False

    write_file(fpath, mode=0o755, content=contents)
    return True


def undisable_daemons_in_root(target):
    try:
        os.unlink(os.path.join(target, "usr/sbin/policy-rc.d"))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        return False
    return True


class ChrootableTarget(object):
    def __init__(self, target, allow_daemons=False, sys_resolvconf=True):
        self.target = target
        self.mounts = ["/dev", "/proc", "/sys"]
        self.umounts = []
        self.disabled_daemons = False
        self.allow_daemons = allow_daemons
        self.sys_resolvconf = sys_resolvconf
        self.rconf_d = None

    def __enter__(self):
        for p in self.mounts:
            tpath = os.path.join(self.target, p[1:])
            if do_mount(p, tpath, opts='--bind'):
                self.umounts.append(tpath)

        if not self.allow_daemons:
            self.disabled_daemons = disable_daemons_in_root(self.target)

        rconf = os.path.join(self.target, "etc", "resolv.conf")
        if (self.sys_resolvconf and
                os.path.islink(rconf) or os.path.isfile(rconf)):
            rtd = None
            try:
                rtd = tempfile.mkdtemp(dir=os.path.dirname(rconf))
                tmp = os.path.join(rtd, "resolv.conf")
                os.rename(rconf, tmp)
                self.rconf_d = rtd
                shutil.copy("/etc/resolv.conf", rconf)
            except:
                if rtd:
                    shutil.rmtree(rtd)
                    self.rconf_d = None
                raise

        return self

    def __exit__(self, etype, value, trace):
        if self.disabled_daemons:
            undisable_daemons_in_root(self.target)

        for p in reversed(self.umounts):
            do_umount(p)

        rconf = os.path.join(self.target, "etc", "resolv.conf")
        if self.sys_resolvconf and self.rconf_d:
            os.rename(os.path.join(self.rconf_d, "resolv.conf"), rconf)
            shutil.rmtree(self.rconf_d)


class RunInChroot(ChrootableTarget):
    def __call__(self, args, **kwargs):
        return subp(['chroot', self.target] + args, **kwargs)


def which(program):
    # Return path of program for execution if found in path
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    _fpath, _ = os.path.split(program)
    if _fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def get_paths(curtin_exe=None, lib=None, helpers=None):
    # return a dictionary with paths for 'curtin_exe', 'helpers' and 'lib'
    # that represent where 'curtin' executable lives, where the 'curtin' module
    # directory is (containing __init__.py) and where the 'helpers' directory.
    mydir = os.path.realpath(os.path.dirname(__file__))
    tld = os.path.realpath(mydir + os.path.sep + "..")

    if curtin_exe is None:
        if os.path.isfile(os.path.join(tld, "bin", "curtin")):
            curtin_exe = os.path.join(tld, "bin", "curtin")

    if (curtin_exe is None and
            (os.path.basename(sys.argv[0]).startswith("curtin") and
             os.path.isfile(sys.argv[0]))):
        curtin_exe = os.path.realpath(sys.argv[0])

    if curtin_exe is None:
        found = which('curtin')
        if found:
            curtin_exe = found

    if (curtin_exe is None and os.path.exists(_INSTALLED_MAIN)):
        curtin_exe = _INSTALLED_MAIN

    cfile = "common"  # a file in 'helpers'
    if (helpers is None and
            os.path.isfile(os.path.join(tld, "helpers", cfile))):
        helpers = os.path.join(tld, "helpers")

    if (helpers is None and
            os.path.isfile(os.path.join(_INSTALLED_HELPERS_PATH, cfile))):
        helpers = _INSTALLED_HELPERS_PATH

    return({'curtin_exe': curtin_exe, 'lib': mydir, 'helpers': helpers})


def has_pkg_installed(pkg, target=None):
    chroot = []
    if target is not None:
        chroot = ['chroot', target]
    try:
        out, _ = subp(chroot + ['dpkg-query', '--show', '--showformat',
                                '${db:Status-Abbrev}', pkg],
                      capture=True)
        return out.rstrip() == "ii"
    except ProcessExecutionError:
        return False


def install_packages(pkglist, aptopts=None, target=None, env=None):
    emd = []
    apt_inst_cmd = ['apt-get', 'install', '--quiet', '--assume-yes',
                    '--option=Dpkg::options::=--force-unsafe-io']

    if aptopts is None:
        aptopts = []
    apt_inst_cmd.extend(aptopts)

    for ptok in os.environ["PATH"].split(os.pathsep):
        if target is None:
            fpath = os.path.join(ptok, 'eatmydata')
        else:
            fpath = os.path.join(target, ptok, 'eatmydata')
        if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
            emd = ['eatmydata']
            break

    if isinstance(pkglist, str):
        pkglist = [pkglist]

    if env is None:
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    marker = "/tmp/curtin.aptupdate"
    marker_text = ' '.join(pkglist) + "\n"
    apt_update = ['apt-get', 'update', '--quiet']
    if target is not None and target != "/":
        with RunInChroot(target) as inchroot:
            marker = os.path.join(target, marker)
            if not os.path.exists(marker):
                inchroot(apt_update)
            with open(marker, "w") as fp:
                fp.write(marker_text)
            return inchroot(emd + apt_inst_cmd + list(pkglist), env=env)
    else:
        if not os.path.exists(marker):
            subp(apt_update)
        with open(marker, "w") as fp:
            fp.write(marker_text)
        return subp(emd + apt_inst_cmd + list(pkglist), env=env)


# vi: ts=4 expandtab syntax=python
