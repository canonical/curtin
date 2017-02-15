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
    (?:(?P<user>[^:]*?):(?P<password>[^:]*?)
        (?::(?P<initiatoruser>[^:]*?):(?P<initiatorpassword>[^:]*?))?
    @)?                 # optional authentication
    (?P<ip>\S*):        # greedy so ipv6 IPs are matched
    (?P<proto>[^:]*):
    (?P<port>[^:]*):
    (?P<lun>[^:]*):
    (?P<targetname>\S*) # greedy so entire suffix is matched
    ''', re.VERBOSE)

ISCSI_PORTAL_REGEX = re.compile(
    r'(\[(?P<ip6>\S*)\]|(?P<ip4>[^:]*)):(?P<port>[\d]+)')


# @portal is of the form: (IPV4|[IPV6]):PORT
def assert_valid_iscsi_portal(portal):
    if not isinstance(portal, util.string_types):
        raise ValueError("iSCSI portal (%s) is not a string" % portal)

    m = re.match(ISCSI_PORTAL_REGEX, portal)
    if m is None:
        raise ValueError("iSCSI portal (%s) is not in the format "
                         "(IPV4|[IPV6]):PORT", portal)

    if not m.group('ip6') and not m.group('ip4'):
        raise ValueError("Unable to determine IP from iSCSI portal (%s)" %
                         portal)

    if m.group('ip6'):
        if util.is_valid_ipv6_address(m.group('ip6')):
            ip = m.group('ip6')
        else:
            raise ValueError("Invalid IPv6 address (%s) in iSCSI portal (%s)" %
                             (m.group('ip6'), portal))

    if m.group('ip4'):
        if util.is_valid_ipv4_address(m.group('ip4')):
            ip = m.group('ip4')
        else:
            raise ValueError("Invalid IPv4 address (%s) in iSCSI portal (%s)" %
                             (m.group('ip4'), portal))

    try:
        port = int(m.group('port'))
    except ValueError:
        raise ValueError("iSCSI portal (%s) port (%s) is not an integer" %
                         (portal, m.group('port')))

    return ip, port


def iscsiadm_sessions():
    cmd = ["iscsiadm", "--mode=session", "--op=show"]
    # rc 21 indicates no sessions currently exist, which is not
    # inherently incorrect (if not logged in yet)
    out, _ = util.subp(cmd, rcs=[0, 21], capture=True)
    return out


def iscsiadm_discovery(portal):
    # only supported type for now
    type = 'sendtargets'

    if not portal:
        raise ValueError("Portal must be specified for discovery")

    cmd = ["iscsiadm", "--mode=discovery", "--type=%s" % type,
           "--portal=%s" % portal]

    try:
        util.subp(cmd)
    except util.ProcessExecutionError as e:
        LOG.warning("iscsiadm_discovery to %s failed with exit code %d",
                    portal, e.exit_code)
        raise


def iscsiadm_login(target, portal):
    LOG.debug('iscsiadm_login: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s' % portal, '--login']
    util.subp(cmd)


def iscsiadm_set_automatic(target, portal):
    LOG.debug('iscsiadm_set_automatic: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s' % portal, '--op=update',
           '--name=node.startup', '--value=automatic']

    util.subp(cmd)


def iscsiadm_logout(target, portal=None):
    LOG.debug('iscsiadm_logout: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--logout']
    # no portal implies logout of all portals
    if portal:
        cmd += ['--portal=%s' % portal]
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


def disconnect_target_disks(target_root_path=None):
    target_nodes_path = util.target_path(target_root_path, '/etc/iscsi/nodes')
    fails = []
    if os.path.exists(target_nodes_path):
        for target in os.listdir(target_nodes_path):
            try:
                iscsiadm_logout(target)
            except util.ProcessExecutionError as e:
                fails.append(target)
                LOG.warn("Unable to logout of iSCSI target %s: %s", target, e)

    if fails:
        raise RuntimeError(
            "Unable to logout of iSCSI targets: %s" % ', '.join(fails))


# Verifies that a /dev/disk/by-path symlink matching the udev pattern
# for iSCSI disks is pointing at @kname
def kname_is_iscsi(kname):
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
        if not util.is_valid_ip_address(m.group('ip')):
            raise ValueError('Specified iSCSI IP (%s) is not valid' %
                             m.group('ip'))
        self.ip = m.group('ip')
        self.proto = '6'
        try:
            self.port = int(m.group('port')) if m.group('port') else 3260
        except ValueError:
            raise ValueError('Specified iSCSI port (%s) is not an integer' %
                             m.group('port'))
        self.lun = int(m.group('lun')) if m.group('lun') else 0
        self.target = m.group('targetname')

        # put IPv6 addresses in [] to disambiguate
        if util.is_valid_ipv4_address(self.ip):
            portal = '%s:%s' % (self.ip, self.port)
        else:
            portal = '[%s]:%s' % (self.ip, self.port)
        assert_valid_iscsi_portal(portal)
        self.portal = portal

    def __str__(self):
        rep = 'iscsi'
        if self.user:
            rep += ':%s:PASSWORD' % self.user
        if self.iuser:
            rep += ':%s:IPASSWORD' % self.iuser
        rep += ':%s:%s:%s:%s:%s' % (self.ip, self.proto, self.port,
                                    self.lun, self.target)
        return rep

    @property
    def etciscsi_nodefile(self):
        return '/etc/iscsi/nodes/%s/%s,%s,%s/default' % (
            self.target, self.ip, self.port, self.lun)

    @property
    def devdisk_path(self):
        return '/dev/disk/by-path/ip-%s-iscsi-%s-lun-%s' % (
            self.portal, self.target, self.lun)

    def connect(self):
        if self.target in iscsiadm_sessions():
            return

        iscsiadm_discovery(self.portal)

        iscsiadm_login(self.target, self.portal)

        udev.udevadm_settle(self.devdisk_path)

        iscsiadm_set_automatic(self.target, self.portal)

    def disconnect(self):
        if self.target not in iscsiadm_sessions():
            return

        iscsiadm_logout(self.target, self.portal)

# vi: ts=4 expandtab syntax=python
