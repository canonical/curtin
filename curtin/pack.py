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
import tempfile

from . import util

CALL_ENTRY_POINT_PY = """
def call_entry_point(name):
    import os, sys

    (istr, dot, ent)  = name.rpartition('.')
    try:
        __import__(istr)
    except ImportError as e:
        # if that import failed, check dirname(__file__/..)
        # to support ./bin/curtin with modules in .
        _tdir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sys.path.append(_tdir)
        try:
            __import__(istr)
        except ImportError as e:
            sys.stderr.write("Unable to find %s\\n" % name)
            sys.exit(2)

    sys.exit(getattr(sys.modules[istr], ent)())
"""

MAIN_FOOTER = """
if __name__ == '__main__':
    call_entry_point("%s")
"""


def write_exe_wrapper(entrypoint, path=None, interpreter="/usr/bin/python",
                      mode=0o755):
    content = '\n'.join((
        "#! %s" % interpreter,
        CALL_ENTRY_POINT_PY,
        MAIN_FOOTER % entrypoint,
    ))

    if path is not None:
        with open(path, "w") as fp:
            fp.write(content)
        if mode is not None:
            os.chmod(path, mode)
    else:
        return content


def pack(fdout=None, command=None, paths=None, copy_files=None,
         add_files=None):
    # write to 'fdout' a self extracting file to execute 'command'
    # if fdout is None, return content that would be written to fdout.
    # add_files is a list of (archive_path, file_content) tuples.
    # copy_files is a list of (archive_path, file_path) tuples.
    if paths is None:
        paths = util.get_paths()

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
        write_exe_wrapper(entrypoint='curtin.commands.main.main',
                          path=os.path.join(bindir, 'curtin'))

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

        (out, _err) = util.subp(args, capture=True)

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
