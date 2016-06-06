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

import argparse
import errno
import glob
import json
import os
import platform
import shutil
import subprocess
import stat
import sys
import tempfile
import time

from .log import LOG

_INSTALLED_HELPERS_PATH = '/usr/lib/curtin/helpers'
_INSTALLED_MAIN = '/usr/bin/curtin'

_LSB_RELEASE = {}


def _subp(args, data=None, rcs=None, env=None, capture=False, shell=False,
          logstring=False, decode="replace"):
    if rcs is None:
        rcs = [0]

    devnull_fp = None
    try:
        if not logstring:
            LOG.debug(("Running command %s with allowed return codes %s"
                       " (shell=%s, capture=%s)"), args, rcs, shell, capture)
        else:
            LOG.debug(("Running hidden command to protect sensitive "
                       "input/output logstring: %s"), logstring)
        stdin = None
        stdout = None
        stderr = None
        if capture:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
        if data is None:
            devnull_fp = open(os.devnull)
            stdin = devnull_fp
        else:
            stdin = subprocess.PIPE
        sp = subprocess.Popen(args, stdout=stdout,
                              stderr=stderr, stdin=stdin,
                              env=env, shell=shell)
        (out, err) = sp.communicate(data)

        # Just ensure blank instead of none.
        if not out and capture:
            out = b''
        if not err and capture:
            err = b''
        if decode:
            def ldecode(data, m='utf-8'):
                if not isinstance(data, bytes):
                    return data
                return data.decode(m, errors=decode)

            out = ldecode(out)
            err = ldecode(err)
    except OSError as e:
        raise ProcessExecutionError(cmd=args, reason=e)
    finally:
        if devnull_fp:
            devnull_fp.close()

    rc = sp.returncode  # pylint: disable=E1101
    if rc not in rcs:
        raise ProcessExecutionError(stdout=out, stderr=err,
                                    exit_code=rc,
                                    cmd=args)
    return (out, err)


def subp(*args, **kwargs):
    """Run a subprocess.

    :param args: command to run in a list. [cmd, arg1, arg2...]
    :param data: input to the command, made available on its stdin.
    :param rcs:
        a list of allowed return codes.  If subprocess exits with a value not
        in this list, a ProcessExecutionError will be raised.  By default,
        data is returned as a string.  See 'decode' parameter.
    :param env: a dictionary for the command's environment.
    :param capture:
        boolean indicating if output should be captured.  If True, then stderr
        and stdout will be returned.  If False, they will not be redirected.
    :param shell: boolean indicating if this should be run with a shell.
    :param logstring:
        the command will be logged to DEBUG.  If it contains info that should
        not be logged, then logstring will be logged instead.
    :param decode:
        if False, no decoding will be done and returned stdout and stderr will
        be bytes.  Other allowed values are 'strict', 'ignore', and 'replace'.
        These values are passed through to bytes().decode() as the 'errors'
        parameter.  There is no support for decoding to other than utf-8.
    :param retries:
        a list of times to sleep in between retries.  After each failure
        subp will sleep for N seconds and then try again.  A value of [1, 3]
        means to run, sleep 1, run, sleep 3, run and then return exit code.
    """
    retries = []
    if "retries" in kwargs:
        retries = kwargs.pop("retries")

    if args:
        cmd = args[0]
    if 'args' in kwargs:
        cmd = kwargs['args']

    # Retry with waits between the retried command.
    for num, wait in enumerate(retries):
        try:
            return _subp(*args, **kwargs)
        except ProcessExecutionError as e:
            LOG.debug("try %s: command %s failed, rc: %s", num,
                      cmd, e.exit_code)
            time.sleep(wait)
    # Final try without needing to wait or catch the error. If this
    # errors here then it will be raised to the caller.
    return _subp(*args, **kwargs)


def load_command_environment(env=os.environ, strict=False):

    mapping = {'scratch': 'WORKING_DIR', 'fstab': 'OUTPUT_FSTAB',
               'interfaces': 'OUTPUT_INTERFACES', 'config': 'CONFIG',
               'target': 'TARGET_MOUNT_POINT',
               'network_state': 'OUTPUT_NETWORK_STATE',
               'network_config': 'OUTPUT_NETWORK_CONFIG',
               'report_stack_prefix': 'CURTIN_REPORTSTACK'}

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


def load_file(path, mode="r"):
    with open(path, mode) as fp:
        return fp.read()


def del_file(path):
    try:
        os.unlink(path)
        LOG.debug("del_file: removed %s", path)
    except OSError as e:
        LOG.exception("del_file: %s did not exist.", path)
        if e.errno != errno.ENOENT:
            raise e


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
        if target is None:
            target = "/"
        self.target = os.path.abspath(target)
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

        target_etc = os.path.join(self.target, "etc")
        if self.target != "/" and os.path.isdir(target_etc):
            # never muck with resolv.conf on /
            rconf = os.path.join(target_etc, "resolv.conf")
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

        # if /dev is to be unmounted, udevadm settle (LP: #1462139)
        if os.path.join(self.target, "dev") in self.umounts:
            subp(['udevadm', 'settle'])

        for p in reversed(self.umounts):
            do_umount(p)

        rconf = os.path.join(self.target, "etc", "resolv.conf")
        if self.sys_resolvconf and self.rconf_d:
            os.rename(os.path.join(self.rconf_d, "resolv.conf"), rconf)
            shutil.rmtree(self.rconf_d)


class RunInChroot(ChrootableTarget):
    def __call__(self, args, **kwargs):
        if self.target != "/":
            chroot = ["chroot", self.target]
        else:
            chroot = []
        return subp(chroot + args, **kwargs)


def is_exe(fpath):
    # Return path of program for execution if found in path
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program, search=None, target=None):
    if target is None or os.path.realpath(target) == "/":
        target = "/"

    if os.path.sep in program:
        # if program had a '/' in it, then do not search PATH
        # 'which' does consider cwd here. (cd / && which bin/ls) = bin/ls
        # so effectively we set cwd to / (or target)
        if is_exe(os.path.sep.join((target, program,))):
            return program

    if search is None:
        paths = [p.strip('"') for p in
                 os.environ.get("PATH", "").split(os.pathsep)]
        if target == "/":
            search = paths
        else:
            search = [p for p in paths if p.startswith("/")]

    # normalize path input
    search = [os.path.abspath(p) for p in search]

    for path in search:
        if is_exe(os.path.sep.join((target, path, program,))):
            return os.path.sep.join((path, program,))

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


def get_architecture(target=None):
    chroot = []
    if target is not None:
        chroot = ['chroot', target]
    out, _ = subp(chroot + ['dpkg', '--print-architecture'],
                  capture=True)
    return out.strip()


def has_pkg_available(pkg, target=None):
    chroot = []
    if target is not None:
        chroot = ['chroot', target]
    out, _ = subp(chroot + ['apt-cache', 'pkgnames'], capture=True)
    for item in out.splitlines():
        if pkg == item.strip():
            return True
    return False


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


def find_newer(src, files):
    mtime = os.stat(src).st_mtime
    return [f for f in files if
            os.path.exists(f) and os.stat(f).st_mtime > mtime]


def set_unexecutable(fname, strict=False):
    """set fname so it is not executable.

    if strict, raise an exception if the file does not exist.
    return the current mode, or None if no change is needed.
    """
    if not os.path.exists(fname):
        if strict:
            raise ValueError('%s: file does not exist' % fname)
        return None
    cur = stat.S_IMODE(os.lstat(fname).st_mode)
    target = cur & (~stat.S_IEXEC & ~stat.S_IXGRP & ~stat.S_IXOTH)
    if cur == target:
        return None
    os.chmod(fname, target)
    return cur


def apt_update(target=None, env=None, force=False, comment=None,
               retries=None):

    marker = "tmp/curtin.aptupdate"
    if target is None:
        target = "/"

    if env is None:
        env = os.environ.copy()

    if retries is None:
        # by default run apt-update up to 3 times to allow
        # for transient failures
        retries = (1, 2, 3)

    if comment is None:
        comment = "no comment provided"

    if comment.endswith("\n"):
        comment = comment[:-1]

    marker = os.path.join(target, marker)
    # if marker exists, check if there are files that would make it obsolete
    listfiles = [os.path.join(target, "etc/apt/sources.list")]
    listfiles += glob.glob(
        os.path.join(target, "etc/apt/sources.list.d/*.list"))

    if os.path.exists(marker) and not force:
        if len(find_newer(marker, listfiles)) == 0:
            return

    restore_perms = []

    abs_tmpdir = tempfile.mkdtemp(dir=os.path.join(target, 'tmp'))
    try:
        abs_slist = abs_tmpdir + "/sources.list"
        abs_slistd = abs_tmpdir + "/sources.list.d"
        ch_tmpdir = "/tmp/" + os.path.basename(abs_tmpdir)
        ch_slist = ch_tmpdir + "/sources.list"
        ch_slistd = ch_tmpdir + "/sources.list.d"

        # this file gets executed on apt-get update sometimes. (LP: #1527710)
        motd_update = os.path.join(
            target, "usr/lib/update-notifier/update-motd-updates-available")
        pmode = set_unexecutable(motd_update)
        if pmode is not None:
            restore_perms.append((motd_update, pmode),)

        # create tmpdir/sources.list with all lines other than deb-src
        # avoid apt complaining by using existing and empty dir for sourceparts
        os.mkdir(abs_slistd)
        with open(abs_slist, "w") as sfp:
            for sfile in listfiles:
                with open(sfile, "r") as fp:
                    contents = fp.read()
                for line in contents.splitlines():
                    line = line.lstrip()
                    if not line.startswith("deb-src"):
                        sfp.write(line + "\n")

        update_cmd = [
            'apt-get', '--quiet',
            '--option=Acquire::Languages=none',
            '--option=Dir::Etc::sourcelist=%s' % ch_slist,
            '--option=Dir::Etc::sourceparts=%s' % ch_slistd,
            'update']

        # do not using 'run_apt_command' so we can use 'retries' to subp
        with RunInChroot(target, allow_daemons=True) as inchroot:
            inchroot(update_cmd, env=env, retries=retries)
    finally:
        for fname, perms in restore_perms:
            os.chmod(fname, perms)
        if abs_tmpdir:
            shutil.rmtree(abs_tmpdir)

    with open(marker, "w") as fp:
        fp.write(comment + "\n")


def run_apt_command(mode, args=None, aptopts=None, env=None, target=None,
                    execute=True, allow_daemons=False):
    opts = ['--quiet', '--assume-yes',
            '--option=Dpkg::options::=--force-unsafe-io',
            '--option=Dpkg::Options::=--force-confold']

    if args is None:
        args = []

    if aptopts is None:
        aptopts = []

    if env is None:
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    if which('eatmydata', target=target):
        emd = ['eatmydata']
    else:
        emd = []

    cmd = emd + ['apt-get'] + opts + aptopts + [mode] + args
    if not execute:
        return env, cmd

    apt_update(target, env=env, comment=' '.join(cmd))
    ric = RunInChroot(target, allow_daemons=allow_daemons)
    with ric as inchroot:
        return inchroot(cmd, env=env)


def system_upgrade(aptopts=None, target=None, env=None, allow_daemons=False):
    LOG.debug("Upgrading system in %s", target)
    for mode in ('dist-upgrade', 'autoremove'):
        ret = run_apt_command(
            mode, aptopts=aptopts, target=target,
            env=env, allow_daemons=allow_daemons)
    return ret


def install_packages(pkglist, aptopts=None, target=None, env=None,
                     allow_daemons=False):
    if isinstance(pkglist, str):
        pkglist = [pkglist]
    return run_apt_command(
        'install', args=pkglist,
        aptopts=aptopts, target=target, env=env, allow_daemons=allow_daemons)


def is_uefi_bootable():
    return os.path.exists('/sys/firmware/efi') is True


def run_hook_if_exists(target, hook):
    """
    Look for "hook" in "target" and run it
    """
    target_hook = os.path.join(target, 'curtin', hook)
    if os.path.isfile(target_hook):
        LOG.debug("running %s" % target_hook)
        subp([target_hook])
        return True
    return False


def sanitize_source(source):
    """
    Check the install source for type information
    If no type information is present or it is an invalid
    type, we default to the standard tgz format
    """
    if type(source) is dict:
        # already sanitized?
        return source
    supported = ['tgz', 'dd-tgz']
    deftype = 'tgz'
    for i in supported:
        prefix = i + ":"
        if source.startswith(prefix):
            return {'type': i, 'uri': source[len(prefix):]}

    LOG.debug("unknown type for url '%s', assuming type '%s'", source, deftype)
    # default to tgz for unknown types
    return {'type': deftype, 'uri': source}


def get_dd_images(sources):
    """
    return all disk images in sources list
    """
    src = []
    if type(sources) is not dict:
        return src
    for i in sources:
        if type(sources[i]) is not dict:
            continue
        if sources[i]['type'].startswith('dd-'):
            src.append(sources[i]['uri'])
    return src


def get_meminfo(meminfo="/proc/meminfo", raw=False):
    mpliers = {'kB': 2**10, 'mB': 2 ** 20, 'B': 1, 'gB': 2 ** 30}
    kmap = {'MemTotal:': 'total', 'MemFree:': 'free',
            'MemAvailable:': 'available'}
    ret = {}
    with open(meminfo, "r") as fp:
        for line in fp:
            try:
                key, value, unit = line.split()
            except ValueError:
                key, value = line.split()
                unit = 'B'
            if raw:
                ret[key] = int(value) * mpliers[unit]
            elif key in kmap:
                ret[kmap[key]] = int(value) * mpliers[unit]

    return ret


def get_fs_use_info(path):
    # return some filesystem usage info as tuple of (size_in_bytes, free_bytes)
    statvfs = os.statvfs(path)
    return (statvfs.f_frsize * statvfs.f_blocks,
            statvfs.f_frsize * statvfs.f_bfree)


def human2bytes(size):
    # convert human 'size' to integer
    size_in = size

    if isinstance(size, int):
        return size
    elif isinstance(size, float):
        if int(size) != size:
            raise ValueError("'%s': resulted in non-integer (%s)" %
                             (size_in, int(size)))
        return size
    elif not isinstance(size, str):
        raise TypeError("cannot convert type %s ('%s')." % (type(size), size))

    if size.endswith("B"):
        size = size[:-1]

    mpliers = {'B': 1, 'K': 2 ** 10, 'M': 2 ** 20, 'G': 2 ** 30, 'T': 2 ** 40}

    num = size
    mplier = 'B'
    for m in mpliers:
        if size.endswith(m):
            mplier = m
            num = size[0:-len(m)]

    try:
        num = float(num)
    except ValueError:
        raise ValueError("'%s' is not valid input." % size_in)

    if num < 0:
        raise ValueError("'%s': cannot be negative" % size_in)

    val = num * mpliers[mplier]
    if int(val) != val:
        raise ValueError("'%s': resulted in non-integer (%s)" % (size_in, val))

    return val


def import_module(import_str):
    """Import a module."""
    __import__(import_str)
    return sys.modules[import_str]


def try_import_module(import_str, default=None):
    """Try to import a module."""
    try:
        return import_module(import_str)
    except ImportError:
        return default


def is_file_not_found_exc(exc):
    return (isinstance(exc, IOError) and exc.errno == errno.ENOENT)


def lsb_release():
    fmap = {'Codename': 'codename', 'Description': 'description',
            'Distributor ID': 'id', 'Release': 'release'}
    global _LSB_RELEASE
    if not _LSB_RELEASE:
        data = {}
        try:
            out, err = subp(['lsb_release', '--all'], capture=True)
            for line in out.splitlines():
                fname, tok, val = line.partition(":")
                if fname in fmap:
                    data[fmap[fname]] = val.strip()
            missing = [k for k in fmap.values() if k not in data]
            if len(missing):
                LOG.warn("Missing fields in lsb_release --all output: %s",
                         ','.join(missing))

        except ProcessExecutionError as e:
            LOG.warn("Unable to get lsb_release --all: %s", e)
            data = {v: "UNAVAILABLE" for v in fmap.values()}

        _LSB_RELEASE.update(data)
    return _LSB_RELEASE


class MergedCmdAppend(argparse.Action):
    """This appends to a list in order of appearence both the option string
       and the value"""
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).append((option_string, values,))


def json_dumps(data):
    return json.dumps(data, indent=1, sort_keys=True,
                      separators=(',', ': ')).encode('utf-8')


def get_platform_arch():
    platform2arch = {
        'i586': 'i386',
        'i686': 'i386',
        'x86_64': 'amd64',
        'ppc64le': 'ppc64el',
        'aarch64': 'arm64',
    }
    return platform2arch.get(platform.machine(), platform.machine())

# vi: ts=4 expandtab syntax=python
