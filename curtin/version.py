from curtin import __version__ as old_version
import os
import subprocess

_PACKAGED_VERSION = '@@PACKAGED_VERSION@@'


def version_string():
    """ Extract a version string from curtin source or version file"""
    def _find_path(pathfile):
        """ Check for file existance and return dirpath
            Search PYTHONPATH, as curtin is typically
            launched with PYTHONPATH set, as with curtin pack
            executables.
        """
        if os.path.exists(pathfile):
            return os.getcwd()
        else:
            path = os.path.abspath(os.path.join(
                                   __file__, '..', '..'))
            curpath = os.path.join(path, pathfile)
            if os.path.exists(curpath):
                return os.path.dirname(curpath)

        return None

    if not _PACKAGED_VERSION.startswith('@@'):
        return _PACKAGED_VERSION

    bzrdir = _find_path('.bzr')
    revno = dpkg_version = None
    if bzrdir:
        try:
            out = subprocess.check_output(['bzr', 'revno'], cwd=bzrdir)
            revno = "bzr%s" % out.decode('utf-8').strip()
        except subprocess.CalledProcessError:
            pass
    else:
        try:
            out = subprocess.check_output(['dpkg-query', '--show',
                                           '--showformat', '${Version}',
                                           'curtin-common'])
            dpkg_version = out.decode('utf-8').strip()
        except subprocess.CalledProcessError:
            pass
    version = old_version
    if revno:
        version += "~%s" % revno
    if dpkg_version:
        version = dpkg_version

    return version
