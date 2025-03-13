# This file is part of curtin. See LICENSE file for copyright and license info.

import logging
from unittest import mock
import os
import random
import shutil
import string
import sys
import tempfile
from unittest import TestCase, skipIf
from contextlib import contextmanager
from curtin import util

_real_subp = util.subp


@contextmanager
def simple_mocked_open(content=None):
    if not content:
        content = ''
    m_open = mock.mock_open(read_data=content)
    with mock.patch('builtins.open', m_open, create=True):
        yield m_open


try:
    import jsonschema
    assert jsonschema  # avoid pyflakes error F401: import unused
    _missing_jsonschema_dep = False
except ImportError:
    _missing_jsonschema_dep = True


def skipUnlessJsonSchema():
    return skipIf(
        _missing_jsonschema_dep, "No python-jsonschema dependency present.")


class CiTestCase(TestCase):
    """Common testing class which all curtin unit tests subclass."""

    with_logs = False
    allowed_subp = False
    SUBP_SHELL_TRUE = "shell=True"

    @contextmanager
    def allow_subp(self, allowed_subp):
        orig = self.allowed_subp
        try:
            self.allowed_subp = allowed_subp
            yield
        finally:
            self.allowed_subp = orig

    def setUp(self):
        super(CiTestCase, self).setUp()
        if self.with_logs:
            # Create a log handler so unit tests can search expected logs.
            self.logger = logging.getLogger()
            if sys.version_info[0] == 2:
                import StringIO
                self.logs = StringIO.StringIO()
            else:
                import io
                self.logs = io.StringIO()
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            handler = logging.StreamHandler(self.logs)
            handler.setFormatter(formatter)
            self.old_handlers = self.logger.handlers
            self.logger.setLevel(logging.DEBUG)
            self.logger.handlers = [handler]

        if self.allowed_subp is True:
            util.subp = _real_subp
        else:
            util.subp = self._fake_subp

    def _fake_subp(self, *args, **kwargs):
        if 'args' in kwargs:
            cmd = kwargs['args']
        else:
            cmd = args[0]

        if not isinstance(cmd, str):
            cmd = cmd[0]
        pass_through = False
        if not isinstance(self.allowed_subp, (list, bool)):
            raise TypeError("self.allowed_subp supports list or bool.")
        if isinstance(self.allowed_subp, bool):
            pass_through = self.allowed_subp
        else:
            pass_through = (
                (cmd in self.allowed_subp) or
                (self.SUBP_SHELL_TRUE in self.allowed_subp and
                 kwargs.get('shell')))
        if pass_through:
            return _real_subp(*args, **kwargs)
        raise Exception(
            "called subp. set self.allowed_subp=True to allow\n subp(%s)" %
            ', '.join([str(repr(a)) for a in args] +
                      ["%s=%s" % (k, repr(v)) for k, v in kwargs.items()]))

    def tearDown(self):
        util.subp = _real_subp
        super(CiTestCase, self).tearDown()

    def add_patch(self, target, attr=None, **kwargs):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        if 'autospec' not in kwargs and 'new' not in kwargs:
            kwargs['autospec'] = True
        m = mock.patch(target, **kwargs)
        p = m.start()
        self.addCleanup(m.stop)
        if attr is not None:
            setattr(self, attr, p)

    def tmp_dir(self, dir=None, cleanup=True):
        """Return a full path to a temporary directory for the test run."""
        if dir is None:
            tmpd = tempfile.mkdtemp(
                prefix="curtin-ci-%s." % self.__class__.__name__)
        else:
            tmpd = tempfile.mkdtemp(dir=dir)
        self.addCleanup(shutil.rmtree, tmpd)
        return tmpd

    def tmp_path(self, path, _dir=None):
        # return an absolute path to 'path' under dir.
        # if dir is None, one will be created with tmp_dir()
        # the file is not created or modified.
        if _dir is None:
            _dir = self.tmp_dir()

        return os.path.normpath(
            os.path.abspath(os.path.sep.join((_dir, path))))

    @staticmethod
    def random_string(length=8):
        """ return a random lowercase string with default length of 8"""
        return ''.join(
            random.choice(string.ascii_lowercase) for _ in range(length))


def dir2dict(startdir, prefix=None):
    flist = {}
    if prefix is None:
        prefix = startdir
    for root, dirs, files in os.walk(startdir):
        for fname in files:
            fpath = os.path.join(root, fname)
            key = fpath[len(prefix):]
            with open(fpath, "r") as fp:
                flist[key] = fp.read()
    return flist


def populate_dir(path, files):
    if not os.path.exists(path):
        os.makedirs(path)
    ret = []
    for (name, content) in files.items():
        p = os.path.sep.join([path, name])
        util.ensure_dir(os.path.dirname(p))
        with open(p, "wb") as fp:
            if isinstance(content, util.binary_type):
                fp.write(content)
            else:
                fp.write(content.encode('utf-8'))
            fp.close()
        ret.append(p)

    return ret


def raise_pexec_error(*args, **kwargs):
    raise util.ProcessExecutionError()


# vi: ts=4 expandtab syntax=python
