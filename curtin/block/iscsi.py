#   Copyright (C) 2017 Canonical Ltd.
#
#   Author: Nishanth Aravamudan <nish.aravamudan@canonical.com>
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


# This module wraps calls to the iscsiadm utility for examining iSCSI
# devices.  Functions prefixed with 'iscsiadm_' involve executing
# the 'iscsiadm' command in a subprocess.  The remaining functions handle
# manipulation of the iscsiadm output.


import os
import re
import shutil

from curtin import (util, udev)
from curtin.log import LOG

_ISCSI_DISKS = {}


def iscsiadm_sessions():
    cmd = ["iscsiadm", "--mode=session", "--op=show"]
    # rc 21 indicates no sessions currently exist, which is not
    # inherently incorrect (if not logged in yet)
    out, _ = util.subp(cmd, rcs=[0, 21], capture=True)
    return out


def iscsiadm_discovery(portal, port):
    # only supported type for now
    type = 'sendtargets'

    if not portal:
        raise ValueError("Portal must be specified for discovery")

    cmd = ["iscsiadm", "--mode=discovery", "--type=%s" % type,
           "--portal=%s:%s" % (portal, port)]

    try:
        util.subp(cmd, capture=True)
    except util.ProcessExecutionError:
        LOG.warning("iscsiadm_discovery had unexpected return code")
        raise


def iscsiadm_login(target, portal, port):
    LOG.debug('iscsiadm_login: ' +
              'target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s:%s' % (portal, port), '--login']
    util.subp(cmd)

    udev.udevadm_settle()


def iscsiadm_set_automatic(target, portal, port):
    LOG.debug('iscsiadm_set_automatic: ' +
              'target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s:%s' % (portal, port), '--op=update',
           '--name=node.startup', '--value=automatic']

    util.subp(cmd)


def iscsiadm_logout(target, portal=None, port=None):
    LOG.debug('iscsiadm_logout: ' +
              'target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--logout']
    if portal:
        cmd += ['--portal=%s:%s' % (portal, port)]
    util.subp(cmd)

    udev.udevadm_settle()


def ensure_disk_connected(rfc4173, write_config=True):
    global _ISCSI_DISKS
    if rfc4173 not in _ISCSI_DISKS:
        i = IscsiDisk(rfc4173)
        i.connect()
        if write_config:
            state = util.load_command_environment()
            # A nodes directory will be created in the same directory as the
            # fstab in the configuration. This will then be copied onto the
            # system later
            if state['fstab']:
                # we just want to copy in the nodes portion
                target_nodes_location = os.path.dirname(
                    os.path.join(os.path.split(state['fstab'])[0],
                                 i.etciscsi_nodefile[len('/etc/iscsi/'):]))
                os.makedirs(target_nodes_location)
                shutil.copy(i.etciscsi_nodefile, target_nodes_location)
            else:
                LOG.info("fstab configuration is not present in environment, \
                          so cannot locate an appropriate directory to write \
                          iSCSI node file in so not writing iSCSI node file")
        _ISCSI_DISKS.update({rfc4173: i})

    i = _ISCSI_DISKS[rfc4173]

    if not os.path.exists(i.devdisk_path):
        LOG.warn('Unable to find iSCSI disk for target (%s) by path (%s)',
                 i.target, i.devdisk_path)

    return i


def connected_disks():
    global _ISCSI_DISKS
    return _ISCSI_DISKS


def disconnect_target_disks(target_root_path):
    target_nodes_path = os.path.sep.join([target_root_path, 'etc/iscsi/nodes'])
    if os.path.exists(target_nodes_path):
        for target in os.listdir(target_nodes_path):
            iscsiadm_logout(target)


def kname_is_iscsi(kname):
    LOG.debug('kname_is_iscsi: ' +
              'looking up kname %s', kname)
    by_path = "/dev/disk/by-path"
    for path in os.listdir(by_path):
        path_link = os.path.sep.join([by_path, path])
        if os.path.islink(path_link):
            path_target = os.path.realpath(
                os.path.sep.join([by_path, os.readlink(path_link)]))
            if kname in path_target and 'iscsi' in path:
                LOG.debug('kname_is_iscsi: ' +
                          'found by-path link %s for kname %s', path, kname)
                return True
    LOG.debug('kname_is_iscsi: no iscsi disk found for kname %s' % kname)
    return False


class IscsiDisk:
    # Per Debian bug 804162, the iscsi specifier looks like
    # TARGETSPEC=ip:proto:port:lun:targetname
    # root=iscsi:$TARGETSPEC
    # root=iscsi:user:password@$TARGETSPEC
    # root=iscsi:user:password:initiatoruser:initiatorpassword@$TARGETSPEC
    def __init__(self, rfc4173):
        r = re.compile(r'''
               iscsi:
               (?:(?P<user>\S*?):(?P<password>\S*?)
                   (?::(?P<initiatoruser>\S*?):(?P<initiatorpassword>\S*?))?
               @)?                 # optional authentication
               (?P<ip>\S*):        # greedy so ipv6 IPs are matched
               (?P<proto>\S*?):
               (?P<port>\S*?):
               (?P<lun>\S*?):
               (?P<targetname>\S*) # greedy so entire suffix is matched
               ''', re.VERBOSE)
        m = r.match(rfc4173)
        if m is None:
            raise ValueError('iSCSI disks must be specified as ' +
                             'iscsi:[user:password[:initiatoruser:' +
                             'initiatorpassword]@]' +
                             'ip:proto:port:lun:targetname')

        if m.group('proto') and m.group('proto') != '6':
            LOG.warn('Specified protocol for iSCSI (%s) is unsupported, ' +
                     'assuming 6 (TCP)', m.group('proto'))

        if not m.group('ip') or not m.group('targetname'):
            raise ValueError('Both IP and targetname must be specified for ' +
                             'iSCSI disks')

        self._user = m.group('user')
        self._password = m.group('password')
        self._iuser = m.group('initiatoruser')
        self._ipassword = m.group('initiatorpassword')
        self._portal = m.group('ip')
        self._proto = '6'
        self._port = m.group('port') if m.group('port') else 3260
        self._lun = int(m.group('lun')) if m.group('lun') else 0
        self._target = m.group('targetname')

    # could have other class methods to obtain an object from a dict,
    # e.g.

    @property
    def user(self):
        return self._user

    @property
    def password(self):
        return self._password

    @property
    def initiatoruser(self):
        return self._iuser

    @property
    def initiatorpassword(self):
        return self._ipassword

    @property
    def portal(self):
        return self._portal

    @property
    def proto(self):
        return self._proto

    @property
    def port(self):
        return self._port

    @property
    def lun(self):
        return self._lun

    @property
    def target(self):
        return self._target

    @property
    def etciscsi_nodefile(self):
        return '/etc/iscsi/nodes/%s/%s,%s,%s/default' % (
            self.target, self.portal, self.port, self.lun)

    @property
    def devdisk_path(self):
        return '/dev/disk/by-path/ip-%s:%s-iscsi-%s-lun-%s' % (
            self.portal, self.port, self.target, self.lun)

    def connect(self):
        if self.target in iscsiadm_sessions():
            return

        iscsiadm_discovery(self._portal, self._port)

        iscsiadm_login(self._target, self._portal, self._port)

        iscsiadm_set_automatic(self._target, self._portal, self._port)

    def disconnect(self):
        if self.target not in iscsiadm_sessions():
            return

        iscsiadm_logout(self._target, self._portal, self._port)

# vi: ts=4 expandtab syntax=python
