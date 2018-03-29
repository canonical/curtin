# This file is part of curtin. See LICENSE file for copyright and license info.

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

    version = old_version
    gitdir = os.path.abspath(os.path.join(__file__, '..', '..', '.git'))
    if os.path.exists(gitdir):
        try:
            out = subprocess.check_output(
                ['git', 'describe', '--long', '--abbrev=8',
                 "--match=[0-9][0-9]*"],
                cwd=os.path.dirname(gitdir))
            version = out.decode('utf-8').strip()
        except subprocess.CalledProcessError:
            pass

    return version

# vi: ts=4 expandtab syntax=python
