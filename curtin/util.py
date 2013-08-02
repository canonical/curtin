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


# vi: ts=4 expandtab syntax=python
