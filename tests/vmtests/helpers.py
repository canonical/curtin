#! /usr/bin/env python
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
import subprocess
import signal
import threading
from unittest import TestLoader


class Command(object):
    """
    based on https://gist.github.com/kirpit/1306188
    """
    command = None
    process = None
    status = None
    exception = None
    returncode = -1

    def __init__(self, command, signal=signal.SIGTERM):
        self.command = command
        self.signal = signal

    def run(self, timeout=None, **kwargs):
        """ Run a command then return: (status, output, error). """
        def target(**kwargs):
            try:
                self.process = subprocess.Popen(self.command, **kwargs)
                self.process.communicate()
                self.status = self.process.returncode
            except subprocess.CalledProcessError as e:
                self.exception = e
                self.returncode = e.returncode
            except Exception as e:
                self.exception = e
        # thread
        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.process.send_signal(self.signal)
            thread.join()
            self.exception = TimeoutExpired(
                cmd=self.command, timeout=timeout)

        if self.exception:
            raise self.exception

        if self.status != 0:
            raise subprocess.CalledProcessError(cmd=self.command,
                                                returncode=self.status)

        return 0

try:
    TimeoutExpired = subprocess.TimeoutExpired
except AttributeError:
    class TimeoutExpired(subprocess.CalledProcessError):
        def __init__(self, *args, **kwargs):
            if not kwargs:
                kwargs = {}
            if len(args):
                # if args are given, convert them to kwargs.
                # *args is a tuple, convert it to a list to use pop
                args = list(args)
                for arg in ('cmd', 'output', 'timeout'):
                    kwargs[arg] = args.pop(0)
                    if not len(args):
                        break

            returncode = -1
            if 'timeout' in kwargs:
                self.timeout = kwargs.pop('timeout')
            else:
                self.timeout = -1

            # do not use super here as it confuses pylint
            # https://github.com/PyCQA/pylint/issues/773
            subprocess.CalledProcessError.__init__(self, returncode, **kwargs)


def check_call(cmd, signal=signal.SIGTERM, **kwargs):
    # provide a 'check_call' like interface, but kill with a nice signal
    return Command(cmd, signal).run(**kwargs)


def find_releases():
    """Return a sorted list of releases defined in test cases."""
    # Use the TestLoader to load all tests cases defined within
    # tests/vmtests/ and figure out which releases they are testing.
    loader = TestLoader()
    # dir with the vmtest modules (i.e. tests/vmtests/)
    tests_dir = os.path.dirname(__file__)
    # The root_dir for the curtin branch. (i.e. curtin/)
    root_dir = os.path.split(os.path.split(tests_dir)[0])[0]
    # Find all test modules defined in curtin/tests/vmtests/
    module_test_suites = loader.discover(tests_dir, top_level_dir=root_dir)
    releases = set()
    for mts in module_test_suites:
        for class_test_suite in mts:
            for test_case in class_test_suite:
                if getattr(test_case, 'release', ''):
                    releases.add(getattr(test_case, 'release'))
    return sorted(releases)
