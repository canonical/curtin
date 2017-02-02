#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#           Christian Ehrhardt <christian.ehrhardt@canonical.com>
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
""" gpg.py
gpg related utilities to get raw keys data by their id
"""

from curtin import util

from .log import LOG


def export_armour(key):
    """Export gpg key, armoured key gets returned"""
    try:
        (armour, _) = util.subp(["gpg", "--export", "--armour", key],
                                capture=True)
    except util.ProcessExecutionError as error:
        # debug, since it happens for any key not on the system initially
        LOG.debug('Failed to export armoured key "%s": %s', key, error)
        armour = None
    return armour


def recv_key(key, keyserver, retries=None):
    """Receive gpg key from the specified keyserver"""
    LOG.debug('Receive gpg key "%s"', key)
    try:
        util.subp(["gpg", "--keyserver", keyserver, "--recv", key],
                  capture=True, retries=retries)
    except util.ProcessExecutionError as error:
        raise ValueError(('Failed to import key "%s" '
                          'from server "%s" - error %s') %
                         (key, keyserver, error))


def delete_key(key):
    """Delete the specified key from the local gpg ring"""
    try:
        util.subp(["gpg", "--batch", "--yes", "--delete-keys", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        LOG.warn('Failed delete key "%s": %s', key, error)


def getkeybyid(keyid, keyserver='keyserver.ubuntu.com', retries=None):
    """get gpg keyid from keyserver"""
    armour = export_armour(keyid)
    if not armour:
        try:
            recv_key(keyid, keyserver=keyserver, retries=retries)
            armour = export_armour(keyid)
        except ValueError:
            LOG.exception('Failed to obtain gpg key %s', keyid)
            raise
        finally:
            # delete just imported key to leave environment as it was before
            delete_key(keyid)

    return armour
