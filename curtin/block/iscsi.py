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
RFC4173_REGEX = re.compile(r'''
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


def iscsiadm_sessions():
    cmd = ["iscsiadm", "--mode=session", "--op=show"]
    # rc 21 indicates no sessions currently exist, which is not
    # inherently incorrect (if not logged in yet)
    out, _ = util.subp(cmd, rcs=[0, 21])
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
    except util.ProcessExecutionError as e:
        LOG.warning("iscsiadm_discovery to %s:%s failed with exit code %d",
                    portal, port, e.exit_code)
        raise


def iscsiadm_login(target, portal, port):
    LOG.debug('iscsiadm_login: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s:%s' % (portal, port), '--login']
    util.subp(cmd)


def iscsiadm_set_automatic(target, portal, port):
    LOG.debug('iscsiadm_set_automatic: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s:%s' % (portal, port), '--op=update',
           '--name=node.startup', '--value=automatic']

    util.subp(cmd)


def iscsiadm_logout(target, portal=None, port=None):
    LOG.debug('iscsiadm_logout: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--logout']
    if portal:
        cmd += ['--portal=%s:%s' % (portal, port)]
    util.subp(cmd)

    udev.udevadm_settle()


def target_nodes_directory(state, iscsi_disk):
    # we just want to copy in the nodes portion
    target_nodes_location = os.path.dirname(
        os.path.join(os.path.split(state['fstab'])[0],
                     iscsi_disk.etciscsi_nodefile[len('/etc/iscsi/'):]))
    os.makedirs(target_nodes_location)
    return target_nodes_location


def save_iscsi_config(iscsi_disk):
    state = util.load_command_environment()
    # A nodes directory will be created in the same directory as the
    # fstab in the configuration. This will then be copied onto the
    # system later
    if state['fstab']:
        target_nodes_location = target_nodes_directory(state, iscsi_disk)
        shutil.copy(iscsi_disk.etciscsi_nodefile, target_nodes_location)
    else:
        LOG.info("fstab configuration is not present in environment, "
                 "so cannot locate an appropriate directory to write "
                 "iSCSI node file in so not writing iSCSI node file")


def ensure_disk_connected(rfc4173, write_config=True):
    global _ISCSI_DISKS
    iscsi_disk = _ISCSI_DISKS.get(rfc4173)
    if not iscsi_disk:
        iscsi_disk = IscsiDisk(rfc4173)
        try:
            iscsi_disk.connect()
        except util.ProcessExecutionError:
            LOG.error('Unable to connect to iSCSI disk (%s)' % rfc4173)
            # what should we do in this case?
            raise
        if write_config:
            save_iscsi_config(iscsi_disk)
        _ISCSI_DISKS.update({rfc4173: iscsi_disk})

    # this is just a sanity check that the disk is actually present and
    # the above did what we expected
    if not os.path.exists(iscsi_disk.devdisk_path):
        LOG.warn('Unable to find iSCSI disk for target (%s) by path (%s)',
                 iscsi_disk.target, iscsi_disk.devdisk_path)

    return iscsi_disk


def connected_disks():
    global _ISCSI_DISKS
    return _ISCSI_DISKS


def disconnect_target_disks(target_root_path):
    target_nodes_path = os.path.sep.join([target_root_path, 'etc/iscsi/nodes'])
    failed = False
    if os.path.exists(target_nodes_path):
        for target in os.listdir(target_nodes_path):
            try:
                iscsiadm_logout(target)
            except util.ProcessExecutionError:
                failed = True
                LOG.warn("Unable to logout of iSCSI target %s", target)

    if failed:
        raise util.ProcessExecutionError(
            "Unable to logout of all iSCSI targets")


# Verifies that a /dev/disk/by-path symlink matching the udev pattern
# for iSCSI disks is pointing at @kname
def kname_is_iscsi(kname):
    LOG.debug('kname_is_iscsi: '
              'looking up kname %s', kname)
    by_path = "/dev/disk/by-path"
    for path in os.listdir(by_path):
        path_target = os.path.realpath(os.path.sep.join([by_path, path]))
        if kname in path_target and 'iscsi' in path:
            LOG.debug('kname_is_iscsi: '
                      'found by-path link %s for kname %s', path, kname)
            return True
    LOG.debug('kname_is_iscsi: no iscsi disk found for kname %s' % kname)
    return False


class IscsiDisk(object):
    # Per Debian bug 804162, the iscsi specifier looks like
    # TARGETSPEC=ip:proto:port:lun:targetname
    # root=iscsi:$TARGETSPEC
    # root=iscsi:user:password@$TARGETSPEC
    # root=iscsi:user:password:initiatoruser:initiatorpassword@$TARGETSPEC
    def __init__(self, rfc4173):
        m = RFC4173_REGEX.match(rfc4173)
        if m is None:
            raise ValueError('iSCSI disks must be specified as '
                             'iscsi:[user:password[:initiatoruser:'
                             'initiatorpassword]@]'
                             'ip:proto:port:lun:targetname')

        if m.group('proto') and m.group('proto') != '6':
            LOG.warn('Specified protocol for iSCSI (%s) is unsupported, '
                     'assuming 6 (TCP)', m.group('proto'))

        if not m.group('ip') or not m.group('targetname'):
            raise ValueError('Both IP and targetname must be specified for '
                             'iSCSI disks')

        self.user = m.group('user')
        self.password = m.group('password')
        self.iuser = m.group('initiatoruser')
        self.ipassword = m.group('initiatorpassword')
        self.portal = m.group('ip')
        self.proto = '6'
        self.port = m.group('port') if m.group('port') else 3260
        self.lun = int(m.group('lun')) if m.group('lun') else 0
        self.target = m.group('targetname')

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

        iscsiadm_discovery(self.portal, self.port)

        iscsiadm_login(self.target, self.portal, self.port)

        udev.udevadm_settle(self.devdisk_path)

        iscsiadm_set_automatic(self.target, self.portal, self.port)

    def disconnect(self):
        if self.target not in iscsiadm_sessions():
            return

        iscsiadm_logout(self.target, self.portal, self.port)

# vi: ts=4 expandtab syntax=python
