# This file is part of curtin. See LICENSE file for copyright and license info.

# This module wraps calls to the iscsiadm utility for examining iSCSI
# devices.  Functions prefixed with 'iscsiadm_' involve executing
# the 'iscsiadm' command in a subprocess.  The remaining functions handle
# manipulation of the iscsiadm output.

import os
import re
import shutil

from curtin import (util, udev)
from curtin.block import (get_device_slave_knames,
                          path_to_kname)

from curtin.log import LOG

_ISCSI_DISKS = {}
RFC4173_AUTH_REGEX = re.compile(r'''^
    (?P<user>[^:]*?):(?P<password>[^:]*?)
        (?::(?P<initiatoruser>[^:]*?):(?P<initiatorpassword>[^:]*?))?
    $
    ''', re.VERBOSE)

RFC4173_TARGET_REGEX = re.compile(r'''^
    (?P<host>[^@:\[\]]*|\[[^@]*\]): # greedy so ipv6 IPs are matched
    (?P<proto>[^:]*):
    (?P<port>[^:]*):
    (?P<lun>[^:]*):
    (?P<targetname>\S*) # greedy so entire suffix is matched
    $''', re.VERBOSE)

ISCSI_PORTAL_REGEX = re.compile(r'^(?P<host>\S*):(?P<port>\d+)$')


# @portal is of the form: HOST:PORT
def assert_valid_iscsi_portal(portal):
    if not isinstance(portal, util.string_types):
        raise ValueError("iSCSI portal (%s) is not a string" % portal)

    m = re.match(ISCSI_PORTAL_REGEX, portal)
    if m is None:
        raise ValueError("iSCSI portal (%s) is not in the format "
                         "(HOST:PORT)" % portal)

    host = m.group('host')
    if host.startswith('[') and host.endswith(']'):
        host = host[1:-1]
        if not util.is_valid_ipv6_address(host):
            raise ValueError("Invalid IPv6 address (%s) in iSCSI portal (%s)" %
                             (host, portal))

    try:
        port = int(m.group('port'))
    except ValueError:
        raise ValueError("iSCSI portal (%s) port (%s) is not an integer" %
                         (portal, m.group('port')))

    return host, port


def iscsiadm_sessions():
    cmd = ["iscsiadm", "--mode=session", "--op=show"]
    # rc 21 indicates no sessions currently exist, which is not
    # inherently incorrect (if not logged in yet)
    out, _ = util.subp(cmd, rcs=[0, 21], capture=True, log_captured=True)
    return out


def iscsiadm_discovery(portal):
    # only supported type for now
    type = 'sendtargets'

    if not portal:
        raise ValueError("Portal must be specified for discovery")

    cmd = ["iscsiadm", "--mode=discovery", "--type=%s" % type,
           "--portal=%s" % portal]

    try:
        util.subp(cmd, capture=True, log_captured=True)
    except util.ProcessExecutionError as e:
        LOG.warning("iscsiadm_discovery to %s failed with exit code %d",
                    portal, e.exit_code)
        raise


def iscsiadm_login(target, portal):
    LOG.debug('iscsiadm_login: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s' % portal, '--login']
    util.subp(cmd, capture=True, log_captured=True)


def iscsiadm_set_automatic(target, portal):
    LOG.debug('iscsiadm_set_automatic: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s' % portal, '--op=update',
           '--name=node.startup', '--value=automatic']

    util.subp(cmd, capture=True, log_captured=True)


def iscsiadm_authenticate(target, portal, user=None, password=None,
                          iuser=None, ipassword=None):
    LOG.debug('iscsiadm_authenticate: target=%s portal=%s '
              'user=%s password=%s iuser=%s ipassword=%s',
              target, portal, user, "HIDDEN" if password else None,
              iuser, "HIDDEN" if ipassword else None)

    if iuser or ipassword:
        cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
               '--portal=%s' % portal, '--op=update',
               '--name=node.session.auth.authmethod', '--value=CHAP']
        util.subp(cmd, capture=True, log_captured=True)

        if iuser:
            cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
                   '--portal=%s' % portal, '--op=update',
                   '--name=node.session.auth.username_in',
                   '--value=%s' % iuser]
            util.subp(cmd, capture=True, log_captured=True)

        if ipassword:
            cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
                   '--portal=%s' % portal, '--op=update',
                   '--name=node.session.auth.password_in',
                   '--value=%s' % ipassword]
            util.subp(cmd, capture=True, log_captured=True,
                      logstring='iscsiadm --mode=node --targetname=%s '
                                '--portal=%s --op=update '
                                '--name=node.session.auth.password_in '
                                '--value=HIDDEN' % (target, portal))

    if user or password:
        cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
               '--portal=%s' % portal, '--op=update',
               '--name=node.session.auth.authmethod', '--value=CHAP']
        util.subp(cmd, capture=True, log_captured=True)

        if user:
            cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
                   '--portal=%s' % portal, '--op=update',
                   '--name=node.session.auth.username',
                   '--value=%s' % user]
            util.subp(cmd, capture=True, log_captured=True)

        if password:
            cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
                   '--portal=%s' % portal, '--op=update',
                   '--name=node.session.auth.password',
                   '--value=%s' % password]
            util.subp(cmd, capture=True, log_captured=True,
                      logstring='iscsiadm --mode=node --targetname=%s '
                                '--portal=%s --op=update '
                                '--name=node.session.auth.password '
                                '--value=HIDDEN' % (target, portal))


def iscsiadm_logout(target, portal):
    LOG.debug('iscsiadm_logout: target=%s portal=%s', target, portal)

    cmd = ['iscsiadm', '--mode=node', '--targetname=%s' % target,
           '--portal=%s' % portal, '--logout']
    util.subp(cmd, capture=True, log_captured=True)

    udev.udevadm_settle()


def target_nodes_directory(state, iscsi_disk):
    # we just want to copy in the nodes portion
    target_nodes_location = os.path.dirname(
        os.path.join(os.path.split(state['fstab'])[0],
                     iscsi_disk.etciscsi_nodefile[len('/etc/iscsi/'):]))
    os.makedirs(target_nodes_location)
    return target_nodes_location


def restart_iscsi_service():
    LOG.info('restarting iscsi service')
    if util.uses_systemd():
        cmd = ['systemctl', 'reload-or-restart', 'open-iscsi']
    else:
        cmd = ['service', 'open-iscsi', 'restart']
    util.subp(cmd, capture=True)


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


def get_iscsi_disks_from_config(cfg):
    """Parse a curtin storage config and return a list
       of iscsi disk objects for each configuration present
    """
    if not cfg:
        cfg = {}

    sconfig = cfg.get('storage', {}).get('config', {})
    if not sconfig:
        LOG.warning('Configuration dictionary did not contain'
                    ' a storage configuration')
        return []

    # Construct IscsiDisk objects for each iscsi volume present
    iscsi_disks = [IscsiDisk(disk['path']) for disk in sconfig
                   if disk['type'] == 'disk' and
                   disk.get('path', "").startswith('iscsi:')]
    LOG.debug('Found %s iscsi disks in storage config', len(iscsi_disks))
    return iscsi_disks


def disconnect_target_disks(target_root_path=None):
    target_nodes_path = util.target_path(target_root_path, '/etc/iscsi/nodes')
    fails = []
    if os.path.isdir(target_nodes_path):
        for target in os.listdir(target_nodes_path):
            if target not in iscsiadm_sessions():
                LOG.debug('iscsi target %s not active, skipping', target)
                continue
            # conn is "host,port,lun"
            for conn in os.listdir(
                            os.path.sep.join([target_nodes_path, target])):
                host, port, _ = conn.split(',')
                try:
                    util.subp(['sync'])
                    iscsiadm_logout(target, '%s:%s' % (host, port))
                except util.ProcessExecutionError as e:
                    fails.append(target)
                    LOG.warn("Unable to logout of iSCSI target %s: %s",
                             target, e)
    else:
        LOG.warning('Skipping disconnect: failed to find iscsi nodes path: %s',
                    target_nodes_path)
    if fails:
        raise RuntimeError(
            "Unable to logout of iSCSI targets: %s" % ', '.join(fails))


# Determines if a /dev/disk/by-path symlink matching the udev pattern
# for iSCSI disks is pointing at @kname
def kname_is_iscsi(kname):
    by_path = "/dev/disk/by-path"
    if os.path.isdir(by_path):
        for path in os.listdir(by_path):
            path_target = os.path.realpath(os.path.sep.join([by_path, path]))
            if kname in path_target and 'iscsi' in path:
                LOG.debug('kname_is_iscsi: '
                          'found by-path link %s for kname %s', path, kname)
                return True
    LOG.debug('kname_is_iscsi: no iscsi disk found for kname %s' % kname)
    return False


def volpath_is_iscsi(volume_path):
    """ Determine if the volume_path's kname is backed by iSCSI.
        Recursively check volume_path's slave devices as well in
        case volume_path is a stacked block device (like LVM/MD)

        returns a boolean
    """
    if not volume_path:
        raise ValueError("Invalid input for volume_path: '%s'", volume_path)

    volume_path_slaves = get_device_slave_knames(volume_path)
    LOG.debug('volume_path=%s found slaves: %s', volume_path,
              volume_path_slaves)
    knames = [path_to_kname(volume_path)] + volume_path_slaves
    return any([kname_is_iscsi(kname) for kname in knames])


class IscsiDisk(object):
    # Per Debian bug 804162, the iscsi specifier looks like
    # TARGETSPEC=host:proto:port:lun:targetname
    # root=iscsi:$TARGETSPEC
    # root=iscsi:user:password@$TARGETSPEC
    # root=iscsi:user:password:initiatoruser:initiatorpassword@$TARGETSPEC
    def __init__(self, rfc4173):
        auth_m = None
        _rfc4173 = rfc4173
        if not rfc4173.startswith('iscsi:'):
            raise ValueError('iSCSI specification (%s) did not start with '
                             'iscsi:. iSCSI disks must be specified as '
                             'iscsi:[user:password[:initiatoruser:'
                             'initiatorpassword]@]'
                             'host:proto:port:lun:targetname' % _rfc4173)
        rfc4173 = rfc4173[6:]
        if '@' in rfc4173:
            if rfc4173.count('@') != 1:
                raise ValueError('Only one @ symbol allowed in iSCSI disk '
                                 'specification (%s). iSCSI disks must be '
                                 'specified as'
                                 'iscsi:[user:password[:initiatoruser:'
                                 'initiatorpassword]@]'
                                 'host:proto:port:lun:targetname' % _rfc4173)
            auth, target = rfc4173.split('@')
            auth_m = RFC4173_AUTH_REGEX.match(auth)
            if auth_m is None:
                raise ValueError('Invalid authentication specified for iSCSI '
                                 'disk (%s). iSCSI disks must be specified as '
                                 'iscsi:[user:password[:initiatoruser:'
                                 'initiatorpassword]@]'
                                 'host:proto:port:lun:targetname' % _rfc4173)
        else:
            target = rfc4173

        target_m = RFC4173_TARGET_REGEX.match(target)
        if target_m is None:
            raise ValueError('Invalid target specified for iSCSI disk (%s). '
                             'iSCSI disks must be specified as '
                             'iscsi:[user:password[:initiatoruser:'
                             'initiatorpassword]@]'
                             'host:proto:port:lun:targetname' % _rfc4173)

        if target_m.group('proto') and target_m.group('proto') != '6':
            LOG.warn('Specified protocol for iSCSI (%s) is unsupported, '
                     'assuming 6 (TCP)', target_m.group('proto'))

        if not target_m.group('host') or not target_m.group('targetname'):
            raise ValueError('Both host and targetname must be specified for '
                             'iSCSI disks')

        if auth_m:
            self.user = auth_m.group('user')
            self.password = auth_m.group('password')
            self.iuser = auth_m.group('initiatoruser')
            self.ipassword = auth_m.group('initiatorpassword')
        else:
            self.user = None
            self.password = None
            self.iuser = None
            self.ipassword = None

        self.host = target_m.group('host')
        self.proto = '6'
        self.lun = int(target_m.group('lun')) if target_m.group('lun') else 0
        self.target = target_m.group('targetname')

        try:
            self.port = int(target_m.group('port')) if target_m.group('port') \
                 else 3260

        except ValueError:
            raise ValueError('Specified iSCSI port (%s) is not an integer' %
                             target_m.group('port'))

        portal = '%s:%s' % (self.host, self.port)
        if self.host.startswith('[') and self.host.endswith(']'):
            self.host = self.host[1:-1]
            if not util.is_valid_ipv6_address(self.host):
                raise ValueError('Specified iSCSI IPv6 address (%s) is not '
                                 'valid' % self.host)
            portal = '[%s]:%s' % (self.host, self.port)
        assert_valid_iscsi_portal(portal)
        self.portal = portal

    def __str__(self):
        rep = 'iscsi'
        if self.user:
            rep += ':%s:PASSWORD' % self.user
        if self.iuser:
            rep += ':%s:IPASSWORD' % self.iuser
        rep += ':%s:%s:%s:%s:%s' % (self.host, self.proto, self.port,
                                    self.lun, self.target)
        return rep

    @property
    def etciscsi_nodefile(self):
        return '/etc/iscsi/nodes/%s/%s,%s,%s/default' % (
            self.target, self.host, self.port, self.lun)

    @property
    def devdisk_path(self):
        return '/dev/disk/by-path/ip-%s-iscsi-%s-lun-%s' % (
            self.portal, self.target, self.lun)

    def connect(self):
        if self.target not in iscsiadm_sessions():
            iscsiadm_discovery(self.portal)

            iscsiadm_authenticate(self.target, self.portal, self.user,
                                  self.password, self.iuser, self.ipassword)

            iscsiadm_login(self.target, self.portal)

            udev.udevadm_settle(self.devdisk_path)

        # always set automatic mode
        iscsiadm_set_automatic(self.target, self.portal)

    def disconnect(self):
        if self.target not in iscsiadm_sessions():
            LOG.warning('Iscsi target %s not in active iscsi sessions',
                        self.target)
            return

        try:
            util.subp(['sync'])
            iscsiadm_logout(self.target, self.portal)
        except util.ProcessExecutionError as e:
            LOG.warn("Unable to logout of iSCSI target %s from portal %s: %s",
                     self.target, self.portal, e)

# vi: ts=4 expandtab syntax=python
