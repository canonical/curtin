# This file is part of curtin. See LICENSE file for copyright and license info.

import contextlib
import imp
import importlib
import mock
import os
import shutil
import tempfile
from unittest import TestCase


def builtin_module_name():
    options = ('builtins', '__builtin__')
    for name in options:
        try:
            imp.find_module(name)
        except ImportError:
            continue
        else:
            print('importing and returning: %s' % name)
            importlib.import_module(name)
            return name


@contextlib.contextmanager
def simple_mocked_open(content=None):
    if not content:
        content = ''
    m_open = mock.mock_open(read_data=content)
    mod_name = builtin_module_name()
    m_patch = '{}.open'.format(mod_name)
    with mock.patch(m_patch, m_open, create=True):
        yield m_open


class CiTestCase(TestCase):
    """Common testing class which all curtin unit tests subclass."""

    def add_patch(self, target, attr, **kwargs):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        if 'autospec' not in kwargs:
            kwargs['autospec'] = True
        m = mock.patch(target, **kwargs)
        p = m.start()
        self.addCleanup(m.stop)
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

# vi: ts=4 expandtab syntax=python
