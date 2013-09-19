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
import shutil
import sys
import tempfile
import time

from .log import LOG

_INSTALLED_HELPERS_PATH = "/usr/lib/curtin/helpers"
_INSTALLED_LIB_PATH = "/usr/share/pyshared"


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
               'interfaces': 'OUTPUT_INTERFACES', 'config': 'CONFIG',
               'target': 'TARGET_MOUNT_POINT'}

    if strict:
        missing = [k for k in mapping if k not in env]
        if len(missing):
            raise KeyError("missing environment vars: %s" % missing)

    return {k: env.get(v) for k, v in mapping.items()}


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


def get_curtin_paths(source=None, curtin_exe=None):
    if source is None:
        mydir = os.path.dirname(os.path.realpath(__file__))
        if mydir.startswith("/usr"):
            source = "INSTALLED"
        else:
            source = os.path.dirname(mydir)
            if curtin_exe is None:
                curtin_exe = os.path.join(source, "bin", "curtin")

    if curtin_exe is None:
        curtin_exe = os.path.realpath(sys.argv[0])

    ret = {'curtin_exe': curtin_exe}

    if source == "INSTALLED":
        ret.update({'helpers': _INSTALLED_HELPERS_PATH,
                    'lib': _INSTALLED_LIB_PATH})
    else:
        ret.update({'helpers': os.path.join(source, 'helpers'),
                    'lib': os.path.join(source, 'curtin')})

    return ret


def pack(fdout=None, command=None, paths=None, copy_files=None,
         add_files=None):
    # write to 'fdout' a self extracting file to execute 'command'
    # if fdout is None, return content that would be written to fdout.
    # add_files is a list of (archive_path, file_content) tuples.
    # copy_files is a list of (archive_path, file_path) tuples.
    if paths is None:
        paths = get_curtin_paths()

    if add_files is None:
        add_files = []

    if copy_files is None:
        copy_files = []

    tmpd = None
    try:
        tmpd = tempfile.mkdtemp()
        exdir = os.path.join(tmpd, 'curtin')

        os.mkdir(exdir)
        bindir = os.path.join(exdir, 'bin')
        os.mkdir(bindir)

        def not_dot_py(input_d, flist):
            # include .py files and directories other than __pycache__
            return [f for f in flist if not
                    (f.endswith(".py") or
                     (f != "__pycache__" and
                      os.path.isdir(os.path.join(input_d, f))))]

        shutil.copytree(paths['helpers'], os.path.join(exdir, "helpers"))
        shutil.copytree(paths['lib'], os.path.join(exdir, "curtin"),
                        ignore=not_dot_py)
        shutil.copy(paths['curtin_exe'], os.path.join(bindir, 'curtin'))

        for archpath, filepath in copy_files:
            target = os.path.abspath(os.path.join(exdir, archpath))
            if not target.startswith(exdir + os.path.sep):
                raise ValueError("'%s' resulted in path outside archive" %
                                 archpath)
            try:
                os.mkdir(os.path.dirname(target))
            except OSError as e:
                if e.errno == errno.EEXIST:
                    pass

            if os.path.isfile(filepath):
                shutil.copy(filepath, target)
            else:
                shutil.copytree(filepath, target)

        for archpath, content in add_files:
            target = os.path.abspath(os.path.join(exdir, archpath))
            if not target.startswith(exdir + os.path.sep):
                raise ValueError("'%s' resulted in path outside archive" %
                                 archpath)
            try:
                os.mkdir(os.path.dirname(target))
            except OSError as e:
                if e.errno == errno.EEXIST:
                    pass

            with open(target, "w") as fp:
                fp.write(content)

        archcmd = os.path.join(paths['helpers'], 'shell-archive')

        archout = None

        args = [archcmd]
        if fdout is not None:
            archout = os.path.join(tmpd, 'output')
            args.append("--output=%s" % archout)

        args.extend(["--bin-path=_pwd_/bin", "--python-path=_pwd_", exdir,
                     "curtin", "--"])
        if command is not None:
            args.extend(command)

        (out, _err) = subp(args, capture=True)

        if fdout is None:
            if isinstance(out, bytes):
                out = out.decode()
            return out

        else:
            with open(archout, "r") as fp:
                while True:
                    buf = fp.read(4096)
                    fdout.write(buf)
                    if len(buf) != 4096:
                        break
    finally:
        if tmpd:
            shutil.rmtree(tmpd)


def pack_install(fdout=None, configs=None, paths=None,
                 add_files=None, copy_files=None, args=None):

    if configs is None:
        configs = []

    if add_files is None:
        add_files = []

    if args is None:
        args = []

    command = ["curtin", "install"]

    my_files = []
    for n, config in enumerate(configs):
        apath = "configs/config-%03d.cfg" % n
        my_files.append((apath, config),)
        command.append("--config=%s" % apath)

    command += args

    return pack(fdout=fdout, command=command, paths=paths,
                add_files=add_files + my_files, copy_files=copy_files)


# vi: ts=4 expandtab syntax=python
