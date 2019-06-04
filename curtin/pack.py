# This file is part of curtin. See LICENSE file for copyright and license info.

import errno
import os
import shutil
import tempfile

from . import util
from . import version

CALL_ENTRY_POINT_SH_HEADER = """
#!/bin/sh
PY3OR2_MAIN="%(ep_main)s"
PY3OR2_MCHECK="%(ep_mcheck)s"
PY3OR2_PYTHONS=${PY3OR2_PYTHONS:-"%(python_exe_list)s"}
PYTHON=${PY3OR2_PYTHON}
PY3OR2_DEBUG=${PY3OR2_DEBUG:-0}
""".strip()

CALL_ENTRY_POINT_SH_BODY = """
debug() {
   [ "${PY3OR2_DEBUG}" != "0" ] || return 0
   echo "$@" 1>&2
}
fail() { echo "$@" 1>&2; exit 1; }

# if $0 is is bin/ and dirname($0)/../module exists, then prepend PYTHONPATH
mydir=${0%/*}
updir=${mydir%/*}
if [ "${mydir#${updir}/}" = "bin" -a -d "$updir/${PY3OR2_MCHECK%%.*}" ]; then
    updir=$(cd "$mydir/.." && pwd)
    case "$PYTHONPATH" in
        *:$updir:*|$updir:*|*:$updir) :;;
        *) export PYTHONPATH="$updir${PYTHONPATH:+:$PYTHONPATH}"
           debug "adding '$updir' to PYTHONPATH"
            ;;
    esac
fi

if [ ! -n "$PYTHON" ]; then
    first_exe=""
    oifs="$IFS"; IFS=":"
    best=0
    best_exe=""
    [ "${PY3OR2_DEBUG}" = "0" ] && _v="" || _v="-v"
    for p in $PY3OR2_PYTHONS; do
        command -v "$p" >/dev/null 2>&1 ||
            { debug "$p: not in path"; continue; }
        [ -z "$PY3OR2_MCHECK" ] && PYTHON=$p && break
        out=$($p -m "$PY3OR2_MCHECK" $_v -- "$@" 2>&1) && PYTHON="$p" &&
            { debug "$p is good [$p -m $PY3OR2_MCHECK $_v -- $*]"; break; }
        ret=$?
        debug "$p [$ret]: $out"
        # exit code of 1 is unuseable
        [ $ret -eq 1 ] && continue
        [ -n "$first_exe" ] || first_exe="$p"
        # higher non-zero exit values indicate more plausible usability
        [ $best -lt $ret ] && best_exe="$p" && best=$ret &&
            debug "current best: $best_exe"
    done
    IFS="$oifs"
    [ -z "$best_exe" -a -n "$first_exe" ] && best_exe="$first_exe"
    [ -n "$PYTHON" ] || PYTHON="$best_exe"
    [ -n "$PYTHON" ] ||
        fail "no availble python? [PY3OR2_DEBUG=1 for more info]"
fi
debug "executing: $PYTHON -m \\"$PY3OR2_MAIN\\" $*"
exec $PYTHON -m "$PY3OR2_MAIN" "$@"
"""


def write_exe_wrapper(entrypoint, path=None, interpreter=None,
                      deps_check_entry=None, mode=0o755):
    if not interpreter:
        interpreter = "python3:python"

    subs = {
        'ep_main': entrypoint,
        'ep_mcheck': deps_check_entry if deps_check_entry else "",
        'python_exe_list': interpreter,
    }

    content = '\n'.join(
        (CALL_ENTRY_POINT_SH_HEADER % subs, CALL_ENTRY_POINT_SH_BODY))

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

    try:
        from probert import prober
        psource = os.path.dirname(prober.__file__)
        copy_files.append(('probert', psource),)
    except Exception:
        pass

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
        write_exe_wrapper(entrypoint='curtin.commands.main',
                          path=os.path.join(bindir, 'curtin'),
                          deps_check_entry="curtin.deps.check")

        packed_version = version.version_string()
        ver_file = os.path.join(exdir, 'curtin', 'version.py')
        util.write_file(
            ver_file,
            util.load_file(ver_file).replace("@@PACKED_VERSION@@",
                                             packed_version))

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
                 add_files=None, copy_files=None, args=None,
                 install_deps=True):

    if configs is None:
        configs = []

    if add_files is None:
        add_files = []

    if args is None:
        args = []

    if install_deps:
        dep_flags = ["--install-deps"]
    else:
        dep_flags = []

    command = ["curtin"] + dep_flags + ["install"]

    my_files = []
    for n, config in enumerate(configs):
        apath = "configs/config-%03d.cfg" % n
        my_files.append((apath, config),)
        command.append("--config=%s" % apath)

    command += args

    return pack(fdout=fdout, command=command, paths=paths,
                add_files=add_files + my_files, copy_files=copy_files)

# vi: ts=4 expandtab syntax=python
