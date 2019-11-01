# This file is part of curtin. See LICENSE file for copyright and license info.

import argparse
import collections
from contextlib import contextmanager
import errno
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import stat
import sys
import tempfile
import time

# avoid the dependency to python3-six as used in cloud-init
try:
    from urlparse import urlparse
except ImportError:
    # python3
    # avoid triggering pylint, https://github.com/PyCQA/pylint/issues/769
    # pylint:disable=import-error,no-name-in-module
    from urllib.parse import urlparse

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)

try:
    numeric_types = (int, float, long)
except NameError:
    # python3 does not have a long type.
    numeric_types = (int, float)

try:
    FileMissingError = FileNotFoundError
except NameError:
    FileMissingError = IOError

from . import paths
from .log import LOG, log_call

binary_type = bytes
if sys.version_info[0] < 3:
    binary_type = str

_INSTALLED_HELPERS_PATH = 'usr/lib/curtin/helpers'
_INSTALLED_MAIN = 'usr/bin/curtin'

_USES_SYSTEMD = None
_HAS_UNSHARE_PID = None


_DNS_REDIRECT_IP = None

# matcher used in template rendering functions
BASIC_MATCHER = re.compile(r'\$\{([A-Za-z0-9_.]+)\}|\$([A-Za-z0-9_.]+)')


def _subp(args, data=None, rcs=None, env=None, capture=False,
          combine_capture=False, shell=False, logstring=False,
          decode="replace", target=None, cwd=None, log_captured=False,
          unshare_pid=None):
    if rcs is None:
        rcs = [0]
    devnull_fp = None

    tpath = paths.target_path(target)
    chroot_args = [] if tpath == "/" else ['chroot', target]
    sh_args = ['sh', '-c'] if shell else []
    if isinstance(args, string_types):
        args = [args]

    try:
        unshare_args = _get_unshare_pid_args(unshare_pid, tpath)
    except RuntimeError as e:
        raise RuntimeError("Unable to unshare pid (cmd=%s): %s" % (args, e))

    args = unshare_args + chroot_args + sh_args + list(args)

    if not logstring:
        LOG.debug(
            "Running command %s with allowed return codes %s (capture=%s)",
            args, rcs, 'combine' if combine_capture else capture)
    else:
        LOG.debug(("Running hidden command to protect sensitive "
                   "input/output logstring: %s"), logstring)
    try:
        stdin = None
        stdout = None
        stderr = None
        if capture:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
        if combine_capture:
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
        if data is None:
            devnull_fp = open(os.devnull)
            stdin = devnull_fp
        else:
            stdin = subprocess.PIPE
        sp = subprocess.Popen(args, stdout=stdout,
                              stderr=stderr, stdin=stdin,
                              env=env, shell=False, cwd=cwd)
        # communicate in python2 returns str, python3 returns bytes
        (out, err) = sp.communicate(data)

        # Just ensure blank instead of none.
        if capture or combine_capture:
            if not out:
                out = b''
            if not err:
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

    if capture and log_captured:
        LOG.debug("Command returned stdout=%s, stderr=%s", out, err)

    rc = sp.returncode  # pylint: disable=E1101
    if rc not in rcs:
        raise ProcessExecutionError(stdout=out, stderr=err,
                                    exit_code=rc,
                                    cmd=args)
    return (out, err)


def _has_unshare_pid():
    global _HAS_UNSHARE_PID
    if _HAS_UNSHARE_PID is not None:
        return _HAS_UNSHARE_PID

    if not which('unshare'):
        _HAS_UNSHARE_PID = False
        return False
    out, err = subp(["unshare", "--help"], capture=True, decode=False,
                    unshare_pid=False)
    joined = b'\n'.join([out, err])
    _HAS_UNSHARE_PID = b'--fork' in joined and b'--pid' in joined
    return _HAS_UNSHARE_PID


def _get_unshare_pid_args(unshare_pid=None, target=None, euid=None):
    """Get args for calling unshare for a pid.

    If unshare_pid is False, return empty list.
    If unshare_pid is True, check if it is usable.  If not, raise exception.
    if unshare_pid is None, then unshare if
       * euid is 0
       * 'unshare' with '--fork' and '--pid' is available.
       * target != /
    """
    if unshare_pid is not None and not unshare_pid:
        # given a false-ish other than None means no.
        return []

    if euid is None:
        euid = os.geteuid()

    tpath = paths.target_path(target)

    unshare_pid_in = unshare_pid
    if unshare_pid is None:
        unshare_pid = False
        if tpath != "/" and euid == 0:
            if _has_unshare_pid():
                unshare_pid = True

    if not unshare_pid:
        return []

    # either unshare was passed in as True, or None and turned to True.
    if euid != 0:
        raise RuntimeError(
            "given unshare_pid=%s but euid (%s) != 0." %
            (unshare_pid_in, euid))

    if not _has_unshare_pid():
        raise RuntimeError(
            "given unshare_pid=%s but no unshare command." % unshare_pid_in)

    return ['unshare', '--fork', '--pid', '--']


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
    :param combine_capture:
        boolean indicating if stderr should be redirected to stdout. When True,
        interleaved stderr and stdout will be returned as the first element of
        a tuple.
        if combine_capture is True, then output is captured independent of
        the value of capture.
    :param log_captured:
        boolean indicating if output should be logged on capture.  If
        True, then stderr and stdout will be logged at DEBUG level.  If
        False, they will not be logged.
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
    :param target:
        run the command as 'chroot target <args>'
    :param unshare_pid:
        unshare the pid namespace.
        default value (None) is to unshare pid namespace if possible
        and target != /

    :return
        if not capturing, return is (None, None)
        if capturing, stdout and stderr are returned.
            if decode:
                python2 unicode or python3 string
            if not decode:
                python2 string or python3 bytes
    """
    retries = []
    if "retries" in kwargs:
        retries = kwargs.pop("retries")
        if not retries:
            # allow retries=None
            retries = []

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


def wait_for_removal(path, retries=[1, 3, 5, 7]):
    if not path:
        raise ValueError('wait_for_removal: missing path parameter')

    # Retry with waits between checking for existence
    LOG.debug('waiting for %s to be removed', path)
    for num, wait in enumerate(retries):
        if not os.path.exists(path):
            LOG.debug('%s has been removed', path)
            return
        LOG.debug('sleeping %s', wait)
        time.sleep(wait)

    # final check
    if not os.path.exists(path):
        LOG.debug('%s has been removed', path)
        return

    raise OSError('Timeout exceeded for removal of %s', path)


def load_command_environment(env=os.environ, strict=False):

    mapping = {'scratch': 'WORKING_DIR', 'fstab': 'OUTPUT_FSTAB',
               'interfaces': 'OUTPUT_INTERFACES', 'config': 'CONFIG',
               'target': 'TARGET_MOUNT_POINT',
               'network_state': 'OUTPUT_NETWORK_STATE',
               'network_config': 'OUTPUT_NETWORK_CONFIG',
               'report_stack_prefix': 'CURTIN_REPORTSTACK'}

    if strict:
        missing = [k for k in mapping.values() if k not in env]
        if len(missing):
            raise KeyError("missing environment vars: %s" % missing)

    return {k: env.get(v) for k, v in mapping.items()}


def is_kmod_loaded(module):
    """Test if kernel module 'module' is current loaded by checking sysfs"""

    if not module:
        raise ValueError('is_kmod_loaded: invalid module: "%s"', module)

    return os.path.isdir('/sys/module/%s' % module)


def load_kernel_module(module, check_loaded=True):
    """Install kernel module via modprobe.  Optionally check if it's already
       loaded .
    """

    if not module:
        raise ValueError('load_kernel_module: invalid module: "%s"', module)

    if check_loaded:
        if is_kmod_loaded(module):
            LOG.debug('Skipping kernel module load, %s already loaded', module)
            return

    LOG.debug('Loading kernel module %s via modprobe', module)
    subp(['modprobe', '--use-blacklist', module])


class BadUsage(Exception):
    pass


class ProcessExecutionError(IOError):

    MESSAGE_TMPL = ('%(description)s\n'
                    'Command: %(cmd)s\n'
                    'Exit code: %(exit_code)s\n'
                    'Reason: %(reason)s\n'
                    'Stdout: %(stdout)s\n'
                    'Stderr: %(stderr)s')
    stdout_indent_level = 8

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
            self.stderr = "''"
        else:
            self.stderr = self._indent_text(stderr)

        if not stdout:
            self.stdout = "''"
        else:
            self.stdout = self._indent_text(stdout)

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

    def _indent_text(self, text):
        if type(text) == bytes:
            text = text.decode()
        return text.replace('\n', '\n' + ' ' * self.stdout_indent_level)


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


def list_device_mounts(device):
    # return mount entry if device is in /proc/mounts
    mounts = ""
    with open("/proc/mounts", "r") as fp:
        mounts = fp.read()

    dev_mounts = []
    for line in mounts.splitlines():
        if line.split()[0] == device:
            dev_mounts.append(line)
    return dev_mounts


def fuser_mount(path):
    """ Execute fuser to determine open file handles from mountpoint path

        Use verbose mode and then combine stdout, stderr from fuser into
        a dictionary:

        {pid: "fuser-details"}

        path may also be a kernel devpath (e.g. /dev/sda)

    """
    fuser_output = {}
    try:
        stdout, stderr = subp(['fuser', '--verbose', '--mount', path],
                              capture=True)
    except ProcessExecutionError as e:
        LOG.debug('fuser returned non-zero: %s', e.stderr)
        return None

    pidlist = stdout.split()

    """
    fuser writes a header in verbose mode, we'll ignore that but the
    order if the input is <mountpoint> <user> <pid*> <access> <command>

    note that <pid> is not present in stderr, it's only in stdout.  Also
    only the entry with pid=kernel entry will contain the mountpoint

    # Combined stdout and stderr look like:
    #                      USER        PID ACCESS COMMAND
    # /home:               root     kernel mount /
    #                      root          1 .rce. systemd
    #
    # This would return
    #
    {
        'kernel': ['/home', 'root', 'mount', '/'],
        '1': ['root', '1', '.rce.', 'systemd'],
    }
    """
    # Note that fuser only writes PIDS to stdout. Each PID value is
    # 'kernel' or an integer and indicates a process which has an open
    # file handle against the path specified path. All other output
    # is sent to stderr.  This code below will merge the two as needed.
    for (pid, status) in zip(pidlist, stderr.splitlines()[1:]):
        fuser_output[pid] = status.split()

    return fuser_output


@contextmanager
def chdir(dirname):
    curdir = os.getcwd()
    try:
        os.chdir(dirname)
        yield dirname
    finally:
        os.chdir(curdir)


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


def do_umount(mountpoint, recursive=False):
    # unmount mountpoint. if recursive, unmount all mounts under it.
    # return boolean indicating if mountpoint was previously mounted.
    mp = os.path.abspath(mountpoint)
    ret = False
    for line in reversed(load_file("/proc/mounts", decode=True).splitlines()):
        curmp = line.split()[1]
        if curmp == mp or (recursive and curmp.startswith(mp + os.path.sep)):
            subp(['umount', curmp])
        if curmp == mp:
            ret = True
    return ret


def ensure_dir(path, mode=None):
    if path == "":
        path = "."
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    if mode is not None:
        os.chmod(path, mode)


def write_file(filename, content, mode=0o644, omode="w"):
    """
    write 'content' to file at 'filename' using python open mode 'omode'.
    if mode is not set, then chmod file to mode. mode is 644 by default
    """
    ensure_dir(os.path.dirname(filename))
    with open(filename, omode) as fp:
        fp.write(content)
    if mode:
        os.chmod(filename, mode)


def load_file(path, read_len=None, offset=0, decode=True):
    with open(path, "rb") as fp:
        if offset:
            fp.seek(offset)
        contents = fp.read(read_len) if read_len else fp.read()

    if decode:
        return decode_binary(contents)
    else:
        return contents


def decode_binary(blob, encoding='utf-8', errors='replace'):
    # Converts a binary type into a text type using given encoding.
    return blob.decode(encoding, errors=errors)


def file_size(path):
    """get the size of a file"""
    with open(path, 'rb') as fp:
        fp.seek(0, 2)
        return fp.tell()


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

    fpath = paths.target_path(target, "/usr/sbin/policy-rc.d")

    if os.path.isfile(fpath):
        return False

    write_file(fpath, mode=0o755, content=contents)
    return True


def undisable_daemons_in_root(target):
    try:
        os.unlink(paths.target_path(target, "/usr/sbin/policy-rc.d"))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        return False
    return True


class ChrootableTarget(object):
    def __init__(self, target, allow_daemons=False, sys_resolvconf=True,
                 mounts=None):
        if target is None:
            target = "/"
        self.target = paths.target_path(target)
        if mounts is not None:
            self.mounts = mounts
        else:
            self.mounts = ["/dev", "/proc", "/run", "/sys"]
        self.umounts = []
        self.disabled_daemons = False
        self.allow_daemons = allow_daemons
        self.sys_resolvconf = sys_resolvconf
        self.rconf_d = None
        self.rc_tmp = None

    def __enter__(self):
        for p in self.mounts:
            tpath = paths.target_path(self.target, p)
            if do_mount(p, tpath, opts='--bind'):
                self.umounts.append(tpath)

        if not self.allow_daemons:
            self.disabled_daemons = disable_daemons_in_root(self.target)

        rconf = paths.target_path(self.target, "/etc/resolv.conf")
        target_etc = os.path.dirname(rconf)
        if self.target != "/" and os.path.isdir(target_etc):
            # never muck with resolv.conf on /
            rconf = os.path.join(target_etc, "resolv.conf")
            rtd = None
            try:
                rtd = tempfile.mkdtemp(dir=target_etc)
                if os.path.lexists(rconf):
                    self.rc_tmp = os.path.join(rtd, "resolv.conf")
                    os.rename(rconf, self.rc_tmp)
                self.rconf_d = rtd
                shutil.copy("/etc/resolv.conf", rconf)
            except Exception:
                if rtd:
                    # if we renamed, but failed later we need to restore
                    if self.rc_tmp and os.path.lexists(self.rc_tmp):
                        os.rename(os.path.join(self.rconf_d, "resolv.conf"),
                                  rconf)
                    shutil.rmtree(rtd)
                    self.rconf_d = None
                    self.rc_tmp = None
                raise

        return self

    def __exit__(self, etype, value, trace):
        if self.disabled_daemons:
            undisable_daemons_in_root(self.target)

        # if /dev is to be unmounted, udevadm settle (LP: #1462139)
        if paths.target_path(self.target, "/dev") in self.umounts:
            log_call(subp, ['udevadm', 'settle'])

        for p in reversed(self.umounts):
            do_umount(p)

        rconf = paths.target_path(self.target, "/etc/resolv.conf")
        if self.sys_resolvconf and self.rconf_d:
            if self.rc_tmp and os.path.lexists(self.rc_tmp):
                os.rename(os.path.join(self.rconf_d, "resolv.conf"), rconf)
            shutil.rmtree(self.rconf_d)

    def subp(self, *args, **kwargs):
        kwargs['target'] = self.target
        return subp(*args, **kwargs)

    def path(self, path):
        return paths.target_path(self.target, path)


def is_exe(fpath):
    # Return path of program for execution if found in path
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program, search=None, target=None):
    target = paths.target_path(target)

    if os.path.sep in program:
        # if program had a '/' in it, then do not search PATH
        # 'which' does consider cwd here. (cd / && which bin/ls) = bin/ls
        # so effectively we set cwd to / (or target)
        if is_exe(paths.target_path(target, program)):
            return program

    if search is None:
        candpaths = [p.strip('"') for p in
                     os.environ.get("PATH", "").split(os.pathsep)]
        if target == "/":
            search = candpaths
        else:
            search = [p for p in candpaths if p.startswith("/")]

    # normalize path input
    search = [os.path.abspath(p) for p in search]

    for path in search:
        ppath = os.path.sep.join((path, program))
        if is_exe(paths.target_path(target, ppath)):
            return ppath

    return None


def _installed_file_path(path, check_file=None):
    # check the install root for the file 'path'.
    #  if 'check_file', then path is a directory that contains file.
    # return absolute path or None.
    inst_pre = "/"
    if os.environ.get('SNAP'):
        inst_pre = os.path.abspath(os.environ['SNAP'])
    inst_path = os.path.join(inst_pre, path)
    if check_file:
        check_path = os.path.sep.join((inst_path, check_file))
    else:
        check_path = inst_path

    if os.path.isfile(check_path):
        return os.path.abspath(inst_path)
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

    if curtin_exe is None:
        curtin_exe = _installed_file_path(_INSTALLED_MAIN)

    # "common" is a file in helpers
    cfile = "common"
    if (helpers is None and
            os.path.isfile(os.path.join(tld, "helpers", cfile))):
        helpers = os.path.join(tld, "helpers")

    if helpers is None:
        helpers = _installed_file_path(_INSTALLED_HELPERS_PATH, cfile)

    return({'curtin_exe': curtin_exe, 'lib': mydir, 'helpers': helpers})


def get_architecture(target=None):
    out, _ = subp(['dpkg', '--print-architecture'], capture=True,
                  target=target)
    return out.strip()


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


def is_uefi_bootable():
    return os.path.exists('/sys/firmware/efi') is True


def parse_efibootmgr(content):
    efikey_to_dict_key = {
        'BootCurrent': 'current',
        'Timeout': 'timeout',
        'BootOrder': 'order',
    }

    output = {}
    for line in content.splitlines():
        split = line.split(':')
        if len(split) == 2:
            key = split[0].strip()
            output_key = efikey_to_dict_key.get(key, None)
            if output_key:
                output[output_key] = split[1].strip()
                if output_key == 'order':
                    output[output_key] = output[output_key].split(',')
    output['entries'] = {
        entry: {
            'name': name.strip(),
            'path': path.strip(),
        }
        for entry, name, path in re.findall(
            r"^Boot(?P<entry>[0-9a-fA-F]{4})\*?\s(?P<name>.+)\t"
            r"(?P<path>.*)$",
            content, re.MULTILINE)
    }
    if 'order' in output:
        new_order = [item for item in output['order']
                     if item in output['entries']]
        output['order'] = new_order
    return output


def get_efibootmgr(target):
    """Return mapping of EFI information.

    Calls `efibootmgr` inside the `target`.

    Example output:
        {
            'current': '0000',
            'timeout': '1 seconds',
            'order': ['0000', '0001'],
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': (
                        'HD(1,GPT,0,0x8,0x1)/File(\\EFI\\ubuntu\\shimx64.efi)'),
                },
                '0001': {
                    'name': 'UEFI:Network Device',
                    'path': 'BBS(131,,0x0)',
                }
            }
        }
    """
    with ChrootableTarget(target) as in_chroot:
        stdout, _ = in_chroot.subp(['efibootmgr', '-v'], capture=True)
        output = parse_efibootmgr(stdout)
        return output


def run_hook_if_exists(target, hook):
    """
    Look for "hook" in "target" and run it
    """
    target_hook = paths.target_path(target, '/curtin/' + hook)
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
    supported = ['tgz', 'dd-tgz', 'tbz', 'dd-tbz', 'txz', 'dd-txz', 'dd-tar',
                 'dd-bz2', 'dd-gz', 'dd-xz', 'dd-raw', 'fsimage',
                 'fsimage-layered']
    deftype = 'tgz'
    for i in supported:
        prefix = i + ":"
        if source.startswith(prefix):
            return {'type': i, 'uri': source[len(prefix):]}

    # translate squashfs: to fsimage type.
    if source.startswith("squashfs:"):
        return {'type': 'fsimage', 'uri': source[len("squashfs:")]}

    if source.endswith("squashfs") or source.endswith("squash"):
        return {'type': 'fsimage', 'uri': source}

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
            src.append(sources[i])
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


def bytes2human(size):
    """convert size in bytes to human readable"""
    if not isinstance(size, numeric_types):
        raise ValueError('size must be a numeric value, not %s', type(size))
    isize = int(size)
    if isize != size:
        raise ValueError('size "%s" is not a whole number.' % size)
    if isize < 0:
        raise ValueError('size "%d" < 0.' % isize)
    mpliers = {'B': 1, 'K': 2 ** 10, 'M': 2 ** 20, 'G': 2 ** 30, 'T': 2 ** 40}
    unit_order = sorted(mpliers, key=lambda x: -1 * mpliers[x])
    unit = next((u for u in unit_order if (isize / mpliers[u]) >= 1), 'B')
    return str(int(isize / mpliers[unit])) + unit


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
    return (isinstance(exc, (IOError, OSError)) and
            hasattr(exc, 'errno') and
            exc.errno in (errno.ENOENT, errno.EIO, errno.ENXIO))


class MergedCmdAppend(argparse.Action):
    """This appends to a list in order of appearence both the option string
       and the value"""
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).append((option_string, values,))


def json_dumps(data):
    return json.dumps(data, indent=1, sort_keys=True, separators=(',', ': '))


def get_platform_arch():
    platform2arch = {
        'i586': 'i386',
        'i686': 'i386',
        'x86_64': 'amd64',
        'ppc64le': 'ppc64el',
        'aarch64': 'arm64',
    }
    return platform2arch.get(platform.machine(), platform.machine())


def basic_template_render(content, params):
    """This does simple replacement of bash variable like templates.

    It identifies patterns like ${a} or $a and can also identify patterns like
    ${a.b} or $a.b which will look for a key 'b' in the dictionary rooted
    by key 'a'.
    """

    def replacer(match):
        """ replacer
            replacer used in regex match to replace content
        """
        # Only 1 of the 2 groups will actually have a valid entry.
        name = match.group(1)
        if name is None:
            name = match.group(2)
        if name is None:
            raise RuntimeError("Match encountered but no valid group present")
        path = collections.deque(name.split("."))
        selected_params = params
        while len(path) > 1:
            key = path.popleft()
            if not isinstance(selected_params, dict):
                raise TypeError("Can not traverse into"
                                " non-dictionary '%s' of type %s while"
                                " looking for subkey '%s'"
                                % (selected_params,
                                   selected_params.__class__.__name__,
                                   key))
            selected_params = selected_params[key]
        key = path.popleft()
        if not isinstance(selected_params, dict):
            raise TypeError("Can not extract key '%s' from non-dictionary"
                            " '%s' of type %s"
                            % (key, selected_params,
                               selected_params.__class__.__name__))
        return str(selected_params[key])

    return BASIC_MATCHER.sub(replacer, content)


def render_string(content, params):
    """ render_string
        render a string following replacement rules as defined in
        basic_template_render returning the string
    """
    if not params:
        params = {}
    return basic_template_render(content, params)


def is_resolvable(name):
    """determine if a url is resolvable, return a boolean
    This also attempts to be resilent against dns redirection.

    Note, that normal nsswitch resolution is used here.  So in order
    to avoid any utilization of 'search' entries in /etc/resolv.conf
    we have to append '.'.

    The top level 'invalid' domain is invalid per RFC.  And example.com
    should also not exist.  The random entry will be resolved inside
    the search list.
    """
    global _DNS_REDIRECT_IP
    if _DNS_REDIRECT_IP is None:
        badips = set()
        badnames = ("does-not-exist.example.com.", "example.invalid.")
        badresults = {}
        for iname in badnames:
            try:
                result = socket.getaddrinfo(iname, None, 0, 0,
                                            socket.SOCK_STREAM,
                                            socket.AI_CANONNAME)
                badresults[iname] = []
                for (_, _, _, cname, sockaddr) in result:
                    badresults[iname].append("%s: %s" % (cname, sockaddr[0]))
                    badips.add(sockaddr[0])
            except (socket.gaierror, socket.error):
                pass
        _DNS_REDIRECT_IP = badips
        if badresults:
            LOG.debug("detected dns redirection: %s", badresults)

    try:
        result = socket.getaddrinfo(name, None)
        # check first result's sockaddr field
        addr = result[0][4][0]
        if addr in _DNS_REDIRECT_IP:
            LOG.debug("dns %s in _DNS_REDIRECT_IP", name)
            return False
        LOG.debug("dns %s resolved to '%s'", name, result)
        return True
    except (socket.gaierror, socket.error):
        LOG.debug("dns %s failed to resolve", name)
        return False


def is_valid_ipv6_address(addr):
    try:
        socket.inet_pton(socket.AF_INET6, addr)
    except socket.error:
        return False
    return True


def is_resolvable_url(url):
    """determine if this url is resolvable (existing or ip)."""
    return is_resolvable(urlparse(url).hostname)


class RunInChroot(ChrootableTarget):
    """Backwards compatibility for RunInChroot (LP: #1617375).
    It needs to work like:
        with RunInChroot("/target") as in_chroot:
            in_chroot(["your", "chrooted", "command"])"""
    __call__ = ChrootableTarget.subp


def shlex_split(str_in):
    # shlex.split takes a string
    # but in python2 if input here is a unicode, encode it to a string.
    # http://stackoverflow.com/questions/2365411/
    #     python-convert-unicode-to-ascii-without-errors
    if sys.version_info.major == 2:
        try:
            if isinstance(str_in, unicode):
                str_in = str_in.encode('utf-8')
        except NameError:
            pass

        return shlex.split(str_in)
    else:
        return shlex.split(str_in)


def load_shell_content(content, add_empty=False, empty_val=None):
    """Given shell like syntax (key=value\nkey2=value2\n) in content
       return the data in dictionary form.  If 'add_empty' is True
       then add entries in to the returned dictionary for 'VAR='
       variables.  Set their value to empty_val."""

    data = {}
    for line in shlex_split(content):
        key, value = line.split("=", 1)
        if not value:
            value = empty_val
        if add_empty or value:
            data[key] = value

    return data


def uses_systemd():
    """ Check if current enviroment uses systemd by testing if
        /run/systemd/system is a directory; only present if
        systemd is available on running system.
    """

    global _USES_SYSTEMD
    if _USES_SYSTEMD is None:
        _USES_SYSTEMD = os.path.isdir('/run/systemd/system')

    return _USES_SYSTEMD

# vi: ts=4 expandtab syntax=python
