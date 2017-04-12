from curtin import __version__ as old_version
import os
import subprocess

_PACKAGED_VERSION = '@@PACKAGED_VERSION@@'
_PACKED_VERSION = '@@PACKED_VERSION@@'


def version_string():
    """ Extract a version string from curtin source or version file"""

    if not _PACKAGED_VERSION.startswith('@@'):
        return _PACKAGED_VERSION

    if not _PACKED_VERSION.startswith('@@'):
        return _PACKED_VERSION

    revno = None
    version = old_version
    bzrdir = os.path.abspath(os.path.join(__file__, '..', '..', '.bzr'))
    if os.path.isdir(bzrdir):
        try:
            out = subprocess.check_output(['bzr', 'revno'], cwd=bzrdir)
            revno = out.decode('utf-8').strip()
            if revno:
                version += "~bzr%s" % revno
        except subprocess.CalledProcessError:
            pass

    return version
