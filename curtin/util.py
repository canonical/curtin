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
import subprocess
import time

from .log import LOG

INSTALLED_HELPERS_PATH = "/usr/lib/curtin/helpers"


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
               'interfaces': 'INTERFACES', 'config': 'CONFIG',
               'target': 'TARGET_MOUNT_POINT'}

    if strict:
        missing = [k for k in mapping if k not in env]
        if len(missing):
            raise KeyError("missing environment vars: %s" % missing)

    return {k: env.get(v) for k, v in mapping.items()}


def find_helpers(env=os.environ):

    def checkd(path):
        if not os.path.isdir(path):
            raise ValueError("not a directory")
        if not os.path.isfile(os.path.join(path, 'partition')):
            raise ValueError("did not find 'partition' in dir")
        return os.path.abspath(path)

    envname = 'CURTIN_HELPERS'

    if envname in env:
        val = env[envname]
        try:
            return checkd(val)
        except ValueError as e:
            raise ValueError("env[%s]='%s': %s" (envname, val, e))

    search = (os.path.join(os.path.dirname(__file__), "..", "helpers"),
              INSTALLED_HELPERS_PATH)

    for curd in search:
        try:
            return checkd(curd)
        except ValueError:
            pass

    raise Exception("Unable to find helpers dir, searched: %s" % str(search))


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

    print("do_mount(%s, %s, opts=%s)" % (src, target, opts))
    if is_mounted(target, src, opts):
        return False

    ensure_dir(target)
    cmd = ['mount'] + opts + [src, target]
    subp(cmd)
    return True


def do_umount(mountpoint):
    if not is_mounted:
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


def disable_daemons_in_root(target):
    contents = "\n".join(
        ['#!/bin/sh',
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


def undisable_daemons_in_root(target, needed=True):
    if not needed:
        return False
    try:
        os.unlink(os.path.join(target, "/usr/sbin/policy-rc.d"))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        return False
    return True


class ChrootableTarget(object):
    def __init__(self, target, allow_daemons=False):
        self.target = target
        self.mounts = ["/dev", "/proc", "/sys"]
        self.umounts = []
        self.disabled_daemons = False
        self.allow_daemons = allow_daemons

    def __enter__(self):
        for p in self.mounts:
            tpath = os.path.join(self.target, p[1:])
            if do_mount(p, tpath, opts='--bind'):
                self.umounts.append(tpath)

        if not self.allow_daemons:
            self.disabled_daemons = disable_daemons_in_root(self.target)

    def __exit__(self, etype, value, trace):
        if self.disabled_daemons:
            undisable_daemons_in_root(self.target)

        for p in reversed(self.umounts):
            do_umount(p)


# vi: ts=4 expandtab syntax=python
