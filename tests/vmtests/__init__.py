import atexit
import datetime
import errno
import logging
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import uuid
import yaml
import curtin.net as curtin_net
import curtin.util as util
from curtin.block import iscsi

from .report_webhook_logger import CaptureReporting
from curtin.commands.install import INSTALL_PASS_MSG

from .image_sync import query as imagesync_query
from .image_sync import mirror as imagesync_mirror
from .image_sync import (IMAGE_SRC_URL, IMAGE_DIR, ITEM_NAME_FILTERS)
from .helpers import check_call, TimeoutExpired, ip_a_to_dict
from unittest import TestCase, SkipTest

try:
    IMAGES_TO_KEEP = int(os.environ.get("IMAGES_TO_KEEP", 1))
except ValueError:
    raise ValueError("IMAGES_TO_KEEP in environment was not an integer")

DEFAULT_SSTREAM_OPTS = [
    '--keyring=/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg']

DEVNULL = open(os.devnull, 'w')
KEEP_DATA = {"pass": "none", "fail": "all"}
CURTIN_VMTEST_IMAGE_SYNC = os.environ.get("CURTIN_VMTEST_IMAGE_SYNC", "1")
IMAGE_SYNCS = []
TARGET_IMAGE_FORMAT = "raw"
TAR_DISKS = bool(int(os.environ.get("CURTIN_VMTEST_TAR_DISKS", "0")))


DEFAULT_BRIDGE = os.environ.get("CURTIN_VMTEST_BRIDGE", "user")
OUTPUT_DISK_NAME = 'output_disk.img'
BOOT_TIMEOUT = int(os.environ.get("CURTIN_VMTEST_BOOT_TIMEOUT", 300))
INSTALL_TIMEOUT = int(os.environ.get("CURTIN_VMTEST_INSTALL_TIMEOUT", 3000))
REUSE_TOPDIR = bool(int(os.environ.get("CURTIN_VMTEST_REUSE_TOPDIR", 0)))

_TOPDIR = None

UC16_IMAGE = os.path.join(IMAGE_DIR,
                          'ubuntu-core-16/amd64/20170217/root-image.xz')


def remove_empty_dir(dirpath):
    if os.path.exists(dirpath):
        try:
            os.rmdir(dirpath)
        except OSError as e:
            if e.errno == errno.ENOTEMPTY:
                pass


def remove_dir(dirpath):
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)


def _topdir():
    global _TOPDIR
    if _TOPDIR:
        return _TOPDIR

    envname = 'CURTIN_VMTEST_TOPDIR'
    envdir = os.environ.get(envname)
    if envdir:
        if not os.path.exists(envdir):
            os.mkdir(envdir)
            _TOPDIR = envdir
        elif not os.path.isdir(envdir):
            raise ValueError("%s=%s exists but is not a directory" %
                             (envname, envdir))
        else:
            _TOPDIR = envdir
    else:
        tdir = os.environ.get('TMPDIR', '/tmp')
        for i in range(0, 10):
            try:
                ts = datetime.datetime.now().isoformat()
                # : in path give grief at least to tools/launch
                ts = ts.replace(":", "")
                outd = os.path.join(tdir, 'vmtest-{}'.format(ts))
                os.mkdir(outd)
                _TOPDIR = outd
                break
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                time.sleep(random.random()/10)

        if not _TOPDIR:
            raise Exception("Unable to initialize topdir in TMPDIR [%s]" %
                            tdir)

    atexit.register(remove_empty_dir, _TOPDIR)
    return _TOPDIR


def _initialize_logging(name=None):
    # Configure logging module to save output to disk and present it on
    # sys.stderr
    if not name:
        name = __name__

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    envlog = os.environ.get('CURTIN_VMTEST_LOG')
    if envlog:
        logfile = envlog
    else:
        logfile = _topdir() + ".log"
    fh = logging.FileHandler(logfile, mode='w', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("Logfile: %s .  Working dir: %s", logfile, _topdir())
    return logger


def get_env_var_bool(envname, default=False):
    """get a boolean environment variable.

    If environment variable is not set, use default.
    False values are case insensitive 'false', '0', ''."""
    if not isinstance(default, bool):
        raise ValueError("default '%s' for '%s' is not a boolean" %
                         (default, envname))
    val = os.environ.get(envname)
    if val is None:
        return default

    return val.lower() not in ("false", "0", "")


def sync_images(src_url, base_dir, filters, verbosity=0):
    # do a sync with provided filters

    # only sync once per set of filters.  global IMAGE_SYNCS manages that.
    global IMAGE_SYNCS
    sfilters = ','.join(sorted(filters))

    if sfilters in IMAGE_SYNCS:
        logger.debug("already synced for filters: %s", sfilters)
        return

    logger.info('Syncing images from %s with filters=%s', src_url, filters)
    imagesync_mirror(output_d=base_dir, source=src_url,
                     mirror_filters=filters,
                     max_items=IMAGES_TO_KEEP, verbosity=verbosity)

    IMAGE_SYNCS.append(sfilters)
    logger.debug("now done syncs: %s" % IMAGE_SYNCS)
    return


def get_images(src_url, local_d, distro, release, arch, krel=None, sync="1",
               kflavor=None, subarch=None, ftypes=None):
    # ensure that the image items (roottar, kernel, initrd)
    # we need for release and arch are available in base_dir.
    #
    # returns ftype dictionary with path to each ftype as values
    # {ftype: item_url}
    logger.debug("distro=%s release=%s krel=%s subarch=%s ftypes=%s",
                 distro, release, krel, subarch, ftypes)
    if not ftypes:
        ftypes = {
            'vmtest.root-image': '',
            'vmtest.root-tgz': '',
            'squashfs': '',
            'boot-kernel': '',
            'boot-initrd': ''
        }
    elif isinstance(ftypes, (list, tuple)):
        ftypes = dict().fromkeys(ftypes, '')

    common_filters = ['release=%s' % release,
                      'arch=%s' % arch, 'os=%s' % distro]
    if kflavor:
        common_filters.append('kflavor=%s' % kflavor)
    if krel:
        common_filters.append('krel=%s' % krel)
    if subarch:
        common_filters.append('subarch=%s' % subarch)
    filters = ['ftype~(%s)' % ("|".join(ftypes.keys()))] + common_filters

    if sync == "1":
        # sync with the default items + common filters to ensure we get
        # everything in one go.
        sync_filters = common_filters + ITEM_NAME_FILTERS
        logger.debug('Syncing images from %s with filters=%s', src_url,
                     sync_filters)
        imagesync_mirror(output_d=local_d, source=src_url,
                         mirror_filters=sync_filters,
                         max_items=IMAGES_TO_KEEP, verbosity=1)
    query_cmd = 'python3 tests/vmtests/image_sync.py'
    query_str = '%s query %s %s' % (query_cmd, local_d, ' '.join(filters))
    logger.debug('Query %s for image. %s', local_d, query_str)
    fail_msg = None

    try:
        results = imagesync_query(local_d, max_items=IMAGES_TO_KEEP,
                                  filter_list=filters)
        logger.debug("Query '%s' returned: %s", query_str, results)
        fail_msg = "Empty result returned."
    except Exception as e:
        logger.debug("Query '%s' failed: %s", query_str, e)
        results = None
        fail_msg = str(e)

    if not results and sync == "1":
        # try to fix this with a sync
        logger.info(fail_msg + "  Attempting to fix with an image sync. (%s)",
                    query_str)
        return get_images(src_url, local_d, distro, release, arch,
                          krel=krel, sync="1", kflavor=kflavor,
                          subarch=subarch, ftypes=ftypes)
    elif not results:
        raise ValueError("Required images not found and "
                         "syncing disabled:\n%s" % query_str)

    missing = []
    found = sorted(f.get('ftype') for f in results)
    for ftype in ftypes.keys():
        if ftype not in found:
            raise ValueError("Expected ftype '{}' but not in results"
                             .format(ftype))
    for item in results:
        ftypes[item['ftype']] = item['item_url']
        last_item = item

    missing = [(ftype, path) for ftype, path in ftypes.items()
               if not os.path.exists(path)]

    if len(missing):
        raise ValueError("missing files for ftypes: %s" % missing)

    # trusty amd64/hwe-p 20150101
    version_info = ('%(release)s %(arch)s/%(subarch)s %(version_name)s' %
                    last_item)

    return version_info, ftypes


class TempDir(object):
    boot = None
    collect = None
    disks = None
    install = None
    logs = None
    output_disk = None

    def __init__(self, name, user_data):
        self.restored = REUSE_TOPDIR
        # Create tmpdir
        self.tmpdir = os.path.join(_topdir(), name)

        # make subdirs
        self.collect = os.path.join(self.tmpdir, "collect")
        self.install = os.path.join(self.tmpdir, "install")
        self.boot = os.path.join(self.tmpdir, "boot")
        self.logs = os.path.join(self.tmpdir, "logs")
        self.disks = os.path.join(self.tmpdir, "disks")

        self.dirs = (self.collect, self.install, self.boot, self.logs,
                     self.disks)

        self.success_file = os.path.join(self.logs, "success")
        self.errors_file = os.path.join(self.logs, "errors.json")
        self.target_disk = os.path.join(self.disks, "install_disk.img")
        self.seed_disk = os.path.join(self.boot, "seed.img")
        self.output_disk = os.path.join(self.boot, OUTPUT_DISK_NAME)

        if self.restored:
            if os.path.exists(self.tmpdir):
                logger.info('Reusing existing TempDir: %s', self.tmpdir)
                return
            else:
                raise ValueError("REUSE_TOPDIR set, but TempDir not found:"
                                 " %s" % self.tmpdir)

        os.mkdir(self.tmpdir)
        for d in self.dirs:
            os.mkdir(d)

        # write cloud-init for installed system
        meta_data_file = os.path.join(self.install, "meta-data")
        with open(meta_data_file, "w") as fp:
            fp.write("instance-id: inst-123\n")
        user_data_file = os.path.join(self.install, "user-data")
        with open(user_data_file, "w") as fp:
            fp.write(user_data)

        # create target disk
        logger.debug('Creating target disk')
        subprocess.check_call(["qemu-img", "create", "-f", TARGET_IMAGE_FORMAT,
                              self.target_disk, "10G"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create seed.img for installed system's cloud init
        logger.debug('Creating seed disk')
        subprocess.check_call(["cloud-localds", self.seed_disk,
                              user_data_file, meta_data_file],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create output disk, mount ro
        logger.debug('Creating output disk')
        subprocess.check_call(["qemu-img", "create", "-f", TARGET_IMAGE_FORMAT,
                              self.output_disk, "10M"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.check_call(["mkfs.ext2", "-F", self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def collect_output(self):
        logger.debug('extracting output disk')
        subprocess.check_call(['tar', '-C', self.collect, '-xf',
                               self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)
        # make sure collect output dir is usable by non-root
        subprocess.check_call(['chmod', '-R', 'u+rwX', self.collect],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)


class VMBaseClass(TestCase):
    __test__ = False
    arch_skip = []
    boot_timeout = BOOT_TIMEOUT
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        dpkg-query --show \
            --showformat='${db:Status-Abbrev}\t${Package}\t${Version}\n' \
            > debian-packages.txt 2> debian-packages.txt.err
    """)]
    conf_file = "examples/tests/basic.yaml"
    nr_cpus = None
    dirty_disks = False
    dirty_disk_config = "examples/tests/dirty_disks_config.yaml"
    disk_block_size = 512
    disk_driver = 'virtio-blk'
    disk_to_check = {}
    extra_disks = []
    extra_kern_args = None
    fstab_expected = {}
    boot_cloudconf = None
    install_timeout = INSTALL_TIMEOUT
    interactive = False
    logger = None
    multipath = False
    multipath_num_paths = 2
    nvme_disks = []
    iscsi_disks = []
    recorded_errors = 0
    recorded_failures = 0
    conf_replace = {}
    uefi = False
    proxy = None

    # these get set from base_vm_classes
    release = None
    arch = None
    kflavor = None
    krel = None
    distro = None
    subarch = None
    ephemeral_ftype = "squashfs"
    target_distro = None
    target_release = None
    target_krel = None
    target_ftype = "squashfs"

    _debian_packages = None

    def shortDescription(self):
        return None

    @classmethod
    def collect_output(cls):
        cls.td.collect_output()

    @classmethod
    def get_test_files(cls):
        # get local absolute filesystem paths for each of the needed file types
        logger.debug('cls.ephemeral_ftype: %s', cls.ephemeral_ftype)
        logger.debug('cls.target_ftype: %s', cls.target_ftype)
        eph_img_verstr, ftypes = get_images(
            IMAGE_SRC_URL, IMAGE_DIR, cls.distro, cls.release, cls.arch,
            krel=cls.krel if cls.krel else cls.release,
            kflavor=cls.kflavor if cls.kflavor else None,
            subarch=cls.subarch if cls.subarch else None,
            sync=CURTIN_VMTEST_IMAGE_SYNC,
            ftypes=('boot-initrd', 'boot-kernel', cls.ephemeral_ftype))
        logger.debug("Install Image %s\n, ftypes: %s\n",
                     eph_img_verstr, ftypes)
        if not cls.target_krel and cls.krel:
            cls.target_krel = cls.krel

        # get local absolute filesystem paths for the OS tarball to be
        # installed
        if cls.target_ftype in ["vmtest.root-tgz", "squashfs"]:
            target_img_verstr, found = get_images(
                IMAGE_SRC_URL, IMAGE_DIR,
                cls.target_distro if cls.target_distro else cls.distro,
                cls.target_release if cls.target_release else cls.release,
                cls.arch, subarch=cls.subarch if cls.subarch else None,
                kflavor=cls.kflavor if cls.kflavor else None,
                krel=cls.target_krel, sync=CURTIN_VMTEST_IMAGE_SYNC,
                ftypes=(cls.target_ftype,))
            logger.debug("Target Tarball %s\n, ftypes: %s\n",
                         target_img_verstr, found)
        elif cls.target_ftype in ["root-image.xz"]:
            logger.info('get-testfiles UC16 hack!')
            found = {'root-image.xz': UC16_IMAGE}
            target_img_verstr = "UbuntuCore 16"
        logger.info("Ephemeral Image Version:[%s] Target Image Version:[%s]",
                    eph_img_verstr, target_img_verstr)
        ftypes.update(found)
        return ftypes

    @classmethod
    def load_conf_file(cls):
        logger.info('Loading testcase config file: %s', cls.conf_file)
        confdata = util.load_file(cls.conf_file)
        # replace rootfs file system format with class value
        if cls.conf_replace:
            logger.debug('Rendering conf template: %s', cls.conf_replace)
            for k, v in cls.conf_replace.items():
                confdata = confdata.replace(k, v)
            suffix = ".yaml"
            prefix = (cls.td.tmpdir + '/' +
                      os.path.basename(cls.conf_file).replace(suffix, "-"))
            temp_yaml = tempfile.NamedTemporaryFile(prefix=prefix,
                                                    suffix=suffix, mode='w+t',
                                                    delete=False)
            shutil.copyfile(cls.conf_file, temp_yaml.name)
            cls.conf_file = temp_yaml.name
            logger.info('Updating class conf file %s', cls.conf_file)
            with open(cls.conf_file, 'w+t') as fh:
                fh.write(confdata)

        return confdata

    @classmethod
    def build_iscsi_disks(cls):
        cls._iscsi_disks = list()
        disks = []
        if len(cls.iscsi_disks) == 0:
            return disks

        portal = os.environ.get("CURTIN_VMTEST_ISCSI_PORTAL", False)
        if not portal:
            raise SkipTest("No iSCSI portal specified in the "
                           "environment (CURTIN_VMTEST_ISCSI_PORTAL). "
                           "Skipping iSCSI tests.")

        # note that TGT_IPC_SOCKET also needs to be set for
        # successful communication

        try:
            cls.tgtd_ip, cls.tgtd_port = \
                iscsi.assert_valid_iscsi_portal(portal)
        except ValueError as e:
            raise ValueError("CURTIN_VMTEST_ISCSI_PORTAL is invalid: %s", e)

        # copy testcase YAML to a temporary file in order to replace
        # placeholders
        temp_yaml = tempfile.NamedTemporaryFile(prefix=cls.td.tmpdir + '/',
                                                mode='w+t', delete=False)
        logger.debug("iSCSI YAML is at %s" % temp_yaml.name)
        shutil.copyfile(cls.conf_file, temp_yaml.name)
        cls.conf_file = temp_yaml.name

        # we implicitly assume testcase YAML is in the same order as
        # iscsi_disks in the testcase
        # path:size:block_size:serial=,port=,cport=
        for (disk_no, disk_dict) in enumerate(cls.iscsi_disks):
            try:
                disk_sz = disk_dict['size']
            except KeyError:
                raise ValueError('No size specified for iSCSI disk')
            try:
                disk_user, disk_password = disk_dict['auth'].split(':')
                if len(disk_user) == 0 and len(disk_password) > 0:
                    raise ValueError('Specifying iSCSI target password '
                                     'without user is invalid')
            except KeyError:
                disk_user = ''
                disk_password = ''

            try:
                disk_iuser, disk_ipassword = disk_dict['iauth'].split(':')
                if len(disk_iuser) == 0 and len(disk_ipassword) > 0:
                    raise ValueError('Specifying iSCSI initiator password '
                                     'without user is invalid')
            except KeyError:
                disk_iuser = ''
                disk_ipassword = ''

            target = 'curtin-%s' % uuid.uuid1()
            cls._iscsi_disks.append(target)
            dpath = os.path.join(cls.td.disks, '%s.img' % (target))
            iscsi_disk = '{}:{}:iscsi:{}:{}:{}:{}:{}:{}'.format(
                dpath, disk_sz, cls.disk_block_size, target,
                disk_user, disk_password, disk_iuser, disk_ipassword)
            disks.extend(['--disk', iscsi_disk])

            # replace next __RFC4173__ placeholder in YAML
            rfc4173 = get_rfc4173(cls.tgtd_ip, cls.tgtd_port, target,
                                  user=disk_user, pword=disk_password,
                                  iuser=disk_iuser, ipword=disk_ipassword)
            with tempfile.NamedTemporaryFile(mode='w+t') as temp_yaml:
                shutil.copyfile(cls.conf_file, temp_yaml.name)
                with open(cls.conf_file, 'w+t') as conf:
                    replaced = False
                    for line in temp_yaml:
                        if not replaced and '__RFC4173__' in line:
                            line = line.replace('__RFC4173__', rfc4173)
                            replaced = True
                        conf.write(line)
        return disks

    @classmethod
    def skip_by_date(cls, clsname, release, bugnum, fixby, removeby):
        if datetime.date.today() < datetime.date(*fixby):
            raise SkipTest(
                "LP: #%s not expected to be fixed in %s yet" % (bugnum,
                                                                release))
        if datetime.date.today() > datetime.date(*removeby):
            raise RuntimeError(
                "Please remove the LP: #%s workaround in %s",
                bugnum, clsname)

    @classmethod
    def get_config_smp(cls):
        """Get number of cpus to use for guest"""

        nr_cpus = None
        if cls.nr_cpus:
            nr_cpus = cls.nr_cpus
            logger.debug('Setting cpus from class value: %s', nr_cpus)

        env_cpus = os.environ.get("CURTIN_VMTEST_NR_CPUS", None)
        if env_cpus:
            nr_cpus = env_cpus
            logger.debug('Setting cpus from '
                         ' env["CURTIN_VMTEST_NR_CPUS"] value: %s', nr_cpus)
        if not nr_cpus:
            nr_cpus = 1
            logger.debug('Setting cpus to default value: %s', nr_cpus)

        return str(nr_cpus)

    @classmethod
    def get_kernel_package(cls):
        """ Return the kernel package name for this class """
        package = 'linux-image-' + cls.kflavor
        if cls.subarch is None or cls.subarch.startswith('ga'):
            return package

        return package + '-' + cls.subarch

    @classmethod
    def get_kernel_config(cls):
        """Return a kernel config dictionary to install the same
           kernel subarch into the target for hwe, hwe-edge classes

           Returns: config dictionary only for hwe, or edge subclass
           """
        if cls.subarch is None or cls.subarch.startswith('ga'):
            return None

        # -hwe-version or -hwe-version-edge packages
        package = cls.get_kernel_package()
        return {'kernel': {'fallback-package': package}}

    @classmethod
    def setUpClass(cls):
        # initialize global logger with class name to help make sense of
        # parallel vmtest runs which intermingle output.
        global logger
        logger = _initialize_logging(name=cls.__name__)
        cls.logger = logger

        # check if we should skip due to host arch
        if cls.arch in cls.arch_skip:
            reason = "{} is not supported on arch {}".format(cls.__name__,
                                                             cls.arch)
            raise SkipTest(reason)

        setup_start = time.time()
        logger.info('Starting setup for testclass: {}'.format(cls.__name__))
        # set up tempdir
        cls.td = TempDir(
            name=cls.__name__,
            user_data=generate_user_data(collect_scripts=cls.collect_scripts,
                                         boot_cloudconf=cls.boot_cloudconf))
        logger.info('Using tempdir: %s', cls.td.tmpdir)
        cls.install_log = os.path.join(cls.td.logs, 'install-serial.log')
        cls.boot_log = os.path.join(cls.td.logs, 'boot-serial.log')
        logger.debug('Install console log: {}'.format(cls.install_log))
        logger.debug('Boot console log: {}'.format(cls.boot_log))

        # if interactive, launch qemu without 'background & wait'
        if cls.interactive:
            dowait = "--no-dowait"
        else:
            dowait = "--dowait"

        # create launch cmd
        cmd = ["tools/launch", "--arch=" + cls.arch, "-v", dowait,
               "--smp=" + cls.get_config_smp()]
        if not cls.interactive:
            cmd.extend(["--silent", "--power=off"])

        cmd.extend(["--serial-log=" + cls.install_log])

        if cls.extra_kern_args:
            cmd.extend(["--append=" + cls.extra_kern_args])

        ftypes = cls.get_test_files()
        # trusty can't yet use root=URL due to LP:#1735046
        if cls.release in ['trusty']:
            root_url = "/dev/disk/by-id/virtio-boot-disk"
        else:
            root_url = "squash:PUBURL/%s" % (
                os.path.basename(ftypes[cls.ephemeral_ftype]))
        # configure ephemeral boot environment
        cmd.extend([
            "--root-arg=root=%s" % root_url,
            "--append=overlayroot=tmpfs",
            "--append=ip=dhcp",        # enable networking
            "--append=rc-initrd-dns",  # carry DNS from initramfs into
                                       # real-root (LP: #1735225)
        ])
        # getting resolvconf configured is only fixed in bionic
        # the iscsi_auto handles resolvconf setup via call to
        # configure_networking in initramfs
        if cls.release in ('precise', 'trusty', 'xenial', 'zesty', 'artful'):
            cmd.extend(["--append=iscsi_auto"])

        # publish the ephemeral image (used in root=URL)
        cmd.append("--publish=%s" % ftypes[cls.ephemeral_ftype])
        logger.info("Publishing ephemeral image as %s", cmd[-1])
        # publish the target image
        cmd.append("--publish=%s" % ftypes[cls.target_ftype])
        logger.info("Publishing target image as %s", cmd[-1])

        # set curtin install source
        install_src = cls.get_install_source(ftypes)

        logger.info("Curtin install source URI: %s", install_src)

        # check for network configuration
        cls.network_state = curtin_net.parse_net_config(cls.conf_file)
        logger.debug("Network state: {}".format(cls.network_state))

        # build -n arg list with macaddrs from net_config physical config
        macs = []
        interfaces = {}
        if cls.network_state:
            interfaces = cls.network_state.get('interfaces')
        for ifname in interfaces:
            logger.debug("Interface name: {}".format(ifname))
            iface = interfaces.get(ifname)
            hwaddr = iface.get('mac_address')
            if iface['type'] == 'physical' and hwaddr:
                macs.append(hwaddr)
        netdevs = []
        if len(macs) > 0:
            # take first mac and mark it as the boot interface to prevent DHCP
            # on multiple interfaces which can hang the install.
            cmd.extend(["--append=BOOTIF=01-%s" % macs[0].replace(":", "-")])
            for mac in macs:
                netdevs.extend(["--netdev=" + DEFAULT_BRIDGE +
                                ",mac={}".format(mac)])
        else:
            netdevs.extend(["--netdev=" + DEFAULT_BRIDGE])

        # build disk arguments
        disks = []
        sc = cls.load_conf_file()
        storage_config = yaml.load(sc).get('storage', {}).get('config', {})
        cls.disk_wwns = ["wwn=%s" % x.get('wwn') for x in storage_config
                         if 'wwn' in x]
        cls.disk_serials = ["serial=%s" % x.get('serial')
                            for x in storage_config if 'serial' in x]

        target_disk = "{}:{}:{}:{}:".format(cls.td.target_disk,
                                            "",
                                            cls.disk_driver,
                                            cls.disk_block_size)
        if len(cls.disk_wwns):
            target_disk += cls.disk_wwns[0]

        if len(cls.disk_serials):
            target_disk += cls.disk_serials[0]

        disks.extend(['--disk', target_disk])

        # --disk source:size:driver:block_size:devopts
        for (disk_no, disk_sz) in enumerate(cls.extra_disks):
            dpath = os.path.join(cls.td.disks, 'extra_disk_%d.img' % disk_no)
            extra_disk = '{}:{}:{}:{}:'.format(dpath, disk_sz,
                                               cls.disk_driver,
                                               cls.disk_block_size)
            if len(cls.disk_wwns):
                w_index = disk_no + 1
                if w_index < len(cls.disk_wwns):
                    extra_disk += cls.disk_wwns[w_index]

            if len(cls.disk_serials):
                w_index = disk_no + 1
                if w_index < len(cls.disk_serials):
                    extra_disk += cls.disk_serials[w_index]

            disks.extend(['--disk', extra_disk])

        # build nvme disk args if needed
        for (disk_no, disk_sz) in enumerate(cls.nvme_disks):
            dpath = os.path.join(cls.td.disks, 'nvme_disk_%d.img' % disk_no)
            nvme_disk = '{}:{}:nvme:{}:{}'.format(dpath, disk_sz,
                                                  cls.disk_block_size,
                                                  "serial=nvme-%d" % disk_no)
            disks.extend(['--disk', nvme_disk])

        # build iscsi disk args if needed
        disks.extend(cls.build_iscsi_disks())

        # proxy config
        configs = [cls.conf_file]
        cls.proxy = get_apt_proxy()
        if cls.proxy is not None and not cls.td.restored:
            proxy_config = os.path.join(cls.td.install, 'proxy.cfg')
            if not os.path.exists(proxy_config):
                with open(proxy_config, "w") as fp:
                    fp.write(json.dumps({'apt_proxy': cls.proxy}) + "\n")
            configs.append(proxy_config)

        uefi_flags = []
        if cls.uefi:
            logger.debug("Testcase requested launching with UEFI")
            nvram = os.path.join(cls.td.disks, "ovmf_vars.fd")
            uefi_flags = ["--uefi-nvram=%s" % nvram]

            # always attempt to update target nvram (via grub)
            grub_config = os.path.join(cls.td.install, 'grub.cfg')
            if not os.path.exists(grub_config) and not cls.td.restored:
                with open(grub_config, "w") as fp:
                    fp.write(json.dumps({'grub': {'update_nvram': True}}))
            configs.append(grub_config)

        if cls.dirty_disks and storage_config:
            logger.debug("Injecting early_command to dirty storage devices")
            configs.append(cls.dirty_disk_config)

        excfg = os.environ.get("CURTIN_VMTEST_EXTRA_CONFIG", False)
        if excfg:
            configs.append(excfg)
            logger.debug('Added extra config {}'.format(excfg))

        if cls.target_distro == "centos":
            centos_default = 'examples/tests/centos_defaults.yaml'
            configs.append(centos_default)
            logger.info('Detected centos, adding default config %s',
                        centos_default)

        # set reporting logger
        cls.reporting_log = os.path.join(cls.td.logs, 'webhooks-events.json')
        reporting_logger = CaptureReporting(cls.reporting_log)

        # write reporting config
        reporting_config = os.path.join(cls.td.install, 'reporting.cfg')
        localhost_url = ('http://' + get_lan_ip() +
                         ':{:d}/'.format(reporting_logger.port))
        if not os.path.exists(reporting_config) and not cls.td.restored:
            with open(reporting_config, 'w') as fp:
                fp.write(json.dumps({
                    'install': {
                        'log_file': '/tmp/install.log',
                        'post_files': ['/tmp/install.log'],
                    },
                    'reporting': {
                        'maas': {
                            'level': 'DEBUG',
                            'type': 'webhook',
                            'endpoint': localhost_url,
                        },
                    },
                }))
        configs.append(reporting_config)

        # For HWE/Edge subarch tests, add a kernel config specifying
        # the same kernel package to install to validate subarch kernel is
        # installable and bootable.
        kconfig = cls.get_kernel_config()
        if kconfig:
            kconf = os.path.join(cls.td.logs, 'kernel.cfg')
            if not os.path.exists(kconf) and not cls.td.restored:
                logger.debug('Injecting kernel cfg for hwe/edge subarch: %s',
                             kconfig)
                with open(kconf, 'w') as fp:
                    fp.write(json.dumps(kconfig))
                configs.append(kconf)

        # pass the ephemeral_ftype image as the boot-able image if trusty
        # until LP: #1735046 is fixed.
        root_disk = []
        if cls.release in ["trusty"]:
            root_disk = ['--boot-image', ftypes.get(cls.ephemeral_ftype)]
            if not root_disk[1]:
                raise ValueError('No root disk for %s: ephemeral_ftype "%s"',
                                 cls.__name__, cls.ephemeral_ftype)
        logger.info('Using root_disk: %s', root_disk)

        cmd.extend(uefi_flags + netdevs + cls.mpath_diskargs(disks) +
                   root_disk + [
                    "--kernel=%s" % ftypes['boot-kernel'],
                    "--initrd=%s" % ftypes['boot-initrd'],
                    "--", "curtin", "-vv", "install"] +
                   ["--config=%s" % f for f in configs] +
                   [install_src])

        # don't run the vm stages if we're just re-running testcases on output
        if cls.td.restored:
            logger.info('Using existing outputdata, skipping install/boot')
            return

        # run vm with installer
        lout_path = os.path.join(cls.td.logs, "install-launch.log")
        logger.info('Running curtin installer: {}'.format(cls.install_log))
        try:
            with open(lout_path, "wb") as fpout:
                with reporting_logger:
                    cls.boot_system(cmd, timeout=cls.install_timeout,
                                    console_log=cls.install_log,
                                    proc_out=fpout, purpose="install")
        except TimeoutExpired:
            logger.error('Curtin installer failed with timeout')
            cls.tearDownClass()
            raise
        finally:
            if os.path.exists(cls.install_log):
                with open(cls.install_log, 'rb') as lfh:
                    content = lfh.read().decode('utf-8', errors='replace')
                logger.debug('install serial console output:\n%s', content)
            else:
                logger.warn("Boot for install did not produce a console log.")

        logger.debug('')
        try:
            if os.path.exists(cls.install_log):
                with open(cls.install_log, 'rb') as lfh:
                    install_log = lfh.read().decode('utf-8', errors='replace')
                errmsg, errors = check_install_log(install_log)
                if errmsg:
                    logger.error('Found error: ' + errmsg)
                    for e in errors:
                        logger.error('Context:\n' + e)
                    raise Exception(cls.__name__ + ":" + errmsg +
                                    '\n'.join(errors))
                else:
                    logger.info('Install OK')
            else:
                logger.info('Install Failed')
                raise Exception("No install log was produced")
        except Exception:
            cls.tearDownClass()
            raise

        # create --disk params for nvme disks
        bsize_args = "logical_block_size={}".format(cls.disk_block_size)
        bsize_args += ",physical_block_size={}".format(cls.disk_block_size)
        bsize_args += ",min_io_size={}".format(cls.disk_block_size)

        target_disks = []
        for (disk_no, disk) in enumerate([cls.td.target_disk]):
            disk = '--disk={},driver={},format={},{}'.format(
                disk, cls.disk_driver, TARGET_IMAGE_FORMAT, bsize_args)
            if len(cls.disk_wwns):
                disk += ",%s" % cls.disk_wwns[0]
            if len(cls.disk_serials):
                disk += ",%s" % cls.disk_serials[0]

            target_disks.extend([disk])

        extra_disks = []
        for (disk_no, disk_sz) in enumerate(cls.extra_disks):
            dpath = os.path.join(cls.td.disks, 'extra_disk_%d.img' % disk_no)
            disk = '--disk={},driver={},format={},{}'.format(
                dpath, cls.disk_driver, TARGET_IMAGE_FORMAT, bsize_args)
            if len(cls.disk_wwns):
                w_index = disk_no + 1
                if w_index < len(cls.disk_wwns):
                    disk += ",%s" % cls.disk_wwns[w_index]

            if len(cls.disk_serials):
                w_index = disk_no + 1
                if w_index < len(cls.disk_serials):
                    disk += ",%s" % cls.disk_serials[w_index]

            extra_disks.extend([disk])

        nvme_disks = []
        disk_driver = 'nvme'
        for (disk_no, disk_sz) in enumerate(cls.nvme_disks):
            dpath = os.path.join(cls.td.disks, 'nvme_disk_%d.img' % disk_no)
            disk = '--disk={},driver={},format={},{}'.format(
                dpath, disk_driver, TARGET_IMAGE_FORMAT, bsize_args)
            nvme_disks.extend([disk])

        # unlike NVMe disks, we do not want to configure the iSCSI disks
        # via KVM, which would use qemu's iSCSI target layer.

        # output disk is always virtio-blk, with serial of output_disk.img
        output_disk = '--disk={},driver={},format={},{},{}'.format(
            cls.td.output_disk, 'virtio-blk',
            TARGET_IMAGE_FORMAT, bsize_args,
            'serial=%s' % os.path.basename(cls.td.output_disk))
        target_disks.extend([output_disk])

        # create xkvm cmd
        cmd = (["tools/xkvm", "-v", dowait] +
               uefi_flags + netdevs +
               cls.mpath_diskargs(target_disks + extra_disks + nvme_disks) +
               ["--disk=file=%s,if=virtio,media=cdrom" % cls.td.seed_disk] +
               ["--", "-smp",  cls.get_config_smp(), "-m", "1024"])

        if not cls.interactive:
            if cls.arch == 's390x':
                cmd.extend([
                    "-nographic", "-nodefaults", "-chardev",
                    "file,path=%s,id=charconsole0" % cls.boot_log,
                    "-device",
                    "sclpconsole,chardev=charconsole0,id=console0"])
            else:
                cmd.extend(["-nographic", "-serial", "file:" + cls.boot_log])

        # run vm with installed system, fail if timeout expires
        try:
            logger.info('Booting target image: {}'.format(cls.boot_log))
            logger.debug('{}'.format(" ".join(cmd)))
            xout_path = os.path.join(cls.td.logs, "boot-xkvm.log")
            with open(xout_path, "wb") as fpout:
                cls.boot_system(cmd, console_log=cls.boot_log, proc_out=fpout,
                                timeout=cls.boot_timeout, purpose="first_boot")
        except Exception as e:
            logger.error('Booting after install failed: %s', e)
            cls.tearDownClass()
            raise e
        finally:
            if os.path.exists(cls.boot_log):
                with open(cls.boot_log, 'rb') as lfh:
                    content = lfh.read().decode('utf-8', errors='replace')
                logger.debug('boot serial console output:\n%s', content)
            else:
                    logger.warn("Booting after install not produce"
                                " a console log.")

        # mount output disk
        try:
            cls.collect_output()
        except Exception as e:
            cls.tearDownClass()
            raise

        # capture curtin install log and webhook timings
        try:
            util.subp(["tools/curtin-log-print", "--dumpfiles", cls.td.logs,
                      cls.reporting_log], capture=True)
        except util.ProcessExecutionError as error:
            logger.debug('tools/curtin-log-print failed: %s', error)

        logger.info(
            "%s: setUpClass finished. took %.02f seconds. Running testcases.",
            cls.__name__, time.time() - setup_start)

    @classmethod
    def cleanIscsiState(cls, result, keep_pass, keep_fail):
        if result:
            keep = keep_pass
        else:
            keep = keep_fail

        if 'disks' in keep or (len(keep) == 1 and keep[0] == 'all'):
            logger.info('Not removing iSCSI disks from tgt, they will '
                        'need to be removed manually.')
        else:
            for target in cls._iscsi_disks:
                logger.debug('Removing iSCSI target %s', target)
                tgtadm_out, _ = util.subp(
                    ['tgtadm', '--lld=iscsi', '--mode=target', '--op=show'],
                    capture=True)

                # match target name to TID, e.g.:
                # Target 4: curtin-59b5507d-1a6d-4b15-beda-3484f2a7d399
                tid = None
                for line in tgtadm_out.splitlines():
                    # new target stanza
                    m = re.match(r'Target (\d+): (\S+)', line)
                    if m and target in m.group(2):
                        tid = m.group(1)
                        break

                if tid:
                    util.subp(['tgtadm', '--lld=iscsi', '--mode=target',
                               '--tid=%s' % tid, '--op=delete'])
                else:
                    logger.warn('Unable to determine target ID for '
                                'target %s. It will need to be manually '
                                'removed.', target)

    @classmethod
    def get_install_source(cls, ftypes):
        if cls.target_ftype == 'squashfs':
            # If we're installing from squashfs source then direct
            # curtin to install from the read-only undermount
            install_src = "cp:///media/root-ro"
        else:
            if cls.target_ftype == 'root-image.xz':
                stype = "dd-xz"
            else:
                stype = "tgz"
            src = os.path.basename(ftypes[cls.target_ftype])
            install_src = "%s:PUBURL/%s" % (stype, src)

        return install_src

    @classmethod
    def tearDownClass(cls):
        success = False
        sfile = os.path.exists(cls.td.success_file)
        efile = os.path.exists(cls.td.errors_file)
        if not (sfile or efile):
            logger.warn("class %s had no status.  Possibly no tests run.",
                        cls.__name__)
        elif (sfile and efile):
            logger.warn("class %s had success and fail.", cls.__name__)
        elif sfile:
            success = True

        clean_working_dir(cls.td.tmpdir, success,
                          keep_pass=KEEP_DATA['pass'],
                          keep_fail=KEEP_DATA['fail'])
        if TAR_DISKS:
            tar_disks(cls.td.tmpdir)
        cls.cleanIscsiState(success,
                            keep_pass=KEEP_DATA['pass'],
                            keep_fail=KEEP_DATA['fail'])

    @classmethod
    def expected_interfaces(cls):
        expected = []
        interfaces = {}
        if cls.network_state:
            interfaces = cls.network_state.get('interfaces')
        # handle interface aliases when subnets have multiple entries
        for iface in interfaces.values():
            subnets = iface.get('subnets', {})
            if subnets:
                for index, subnet in zip(range(0, len(subnets)), subnets):
                    if index == 0:
                        expected.append(iface)
                    else:
                        expected.append("{}:{}".format(iface, index))
            else:
                expected.append(iface)
        return expected

    @classmethod
    def parse_deb_config(cls, path):
        return curtin_net.parse_deb_config(path)

    @classmethod
    def get_network_state(cls):
        return cls.network_state

    @classmethod
    def get_expected_etc_network_interfaces(cls):
        return curtin_net.render_interfaces(cls.network_state)

    @classmethod
    def get_expected_etc_resolvconf(cls):
        ifaces = {}
        eni = curtin_net.render_interfaces(cls.network_state)
        curtin_net.parse_deb_config_data(ifaces, eni, None, None)
        return ifaces

    @classmethod
    def boot_system(cls, cmd, console_log, proc_out, timeout, purpose):
        # this is separated for easy override in Psuedo classes
        def myboot():
            check_call(cmd, timeout=timeout, stdout=proc_out,
                       stderr=subprocess.STDOUT)
            return True

        return boot_log_wrap(cls.__name__, myboot, cmd, console_log, timeout,
                             purpose)

    @classmethod
    def collect_path(cls, path):
        # return a full path to the collected file
        # prepending ./ makes '/root/file' or 'root/file' work as expected.
        return os.path.normpath(os.path.join(cls.td.collect, "./" + path))

    @classmethod
    def mpath_diskargs(cls, disks):
        """make multipath versions of --disk args in disks."""
        if not cls.multipath:
            return disks
        opt = ",file.locking=off"
        return ([d if d == "--disk" else d + opt for d in disks] *
                cls.multipath_num_paths)

    # Misc functions that are useful for many tests
    def output_files_exist(self, files):
        logger.debug('checking files exist: %s', files)
        results = {f: os.path.exists(os.path.join(self.td.collect, f))
                   for f in files}
        logger.debug('results: %s', results)
        self.assertTrue(False not in results.values(),
                        msg="expected collected files do not exist.")

    def output_files_dont_exist(self, files):
        logger.debug('checking files dont exist: %s', files)
        results = {f: os.path.exists(os.path.join(self.td.collect, f))
                   for f in files}
        logger.debug('results: %s', results)
        self.assertTrue(True not in results.values(),
                        msg="Collected files exist that should not.")

    def load_collect_file(self, filename, mode="r"):
        with open(self.collect_path(filename), mode) as fp:
            return fp.read()

    def load_collect_file_shell_content(self, filename, mode="r"):
        with open(self.collect_path(filename), mode) as fp:
            return util.load_shell_content(content=fp.read())

    def load_log_file(self, filename):
        with open(filename, 'rb') as fp:
            return fp.read().decode('utf-8', errors='replace')

    def get_install_log_curtin_version(self):
        # curtin: Installation started. (%s)
        startre = re.compile(
            r'curtin: Installation started.[^(]*\((?P<version>[^)]*)\).*')
        version = None
        for line in self.load_log_file(self.install_log).splitlines():
            vermatch = startre.search(line)
            if vermatch:
                version = vermatch.group('version')
                break
        return version

    def get_curtin_version(self):
        curtin_exe = os.environ.get('CURTIN_VMTEST_CURTIN_EXE', 'bin/curtin')
        # use shell=True to allow for CURTIN_VMTEST_CURTIN_EXE to have
        # spaces in it ("lxc exec container curtin").  That could cause
        # issues for non shell-friendly chars.
        vercmd = ' '.join([curtin_exe, "version"])
        out, _err = util.subp(vercmd, shell=True, capture=True)
        return out.strip()

    def check_file_strippedline(self, filename, search):
        lines = self.load_collect_file(filename).splitlines()
        self.assertIn(search, [i.strip() for i in lines])

    def check_file_regex(self, filename, regex):
        self.assertRegex(self.load_collect_file(filename), regex)

    # To get rid of deprecation warning in python 3.
    def assertRegex(self, s, r):
        try:
            # Python 3.
            super(VMBaseClass, self).assertRegex(s, r)
        except AttributeError:
            # Python 2.
            self.assertRegexpMatches(s, r)

    def get_blkid_data(self, blkid_file):
        data = self.load_collect_file(blkid_file)
        ret = {}
        for line in data.splitlines():
            if line == "":
                continue
            val = line.split('=')
            ret[val[0]] = val[1]
        return ret

    def test_fstab(self):
        if self.fstab_expected is None:
            return
        path = self.collect_path("fstab")
        if not os.path.exists(path):
            return
        fstab_entry = None
        for line in util.load_file(path).splitlines():
            for device, mntpoint in self.fstab_expected.items():
                    if device in line:
                        fstab_entry = line
                        self.assertIsNotNone(fstab_entry)
                        self.assertEqual(fstab_entry.split(' ')[1],
                                         mntpoint)

    def test_dname(self):
        if self.disk_to_check is None:
            return
        path = self.collect_path("ls_dname")
        if not os.path.exists(path):
            return
        contents = util.load_file(path)
        for diskname, part in self.disk_to_check:
            if part is not 0:
                link = diskname + "-part" + str(part)
                self.assertIn(link, contents)
            self.assertIn(diskname, contents)

    def test_reporting_data(self):
        with open(self.reporting_log, 'r') as fp:
            data = json.load(fp)
        self.assertTrue(len(data) > 0)
        first_event = data[0]
        self.assertEqual(first_event['event_type'], 'start')
        next_event = data[1]
        # make sure we don't have that timestamp bug
        self.assertNotEqual(first_event['timestamp'], next_event['timestamp'])
        final_event = data[-1]
        self.assertEqual(final_event['event_type'], 'finish')
        self.assertEqual(final_event['name'], 'cmd-install')
        # check for install log
        [events_with_files] = [ev for ev in data if 'files' in ev]
        self.assertIn('files',  events_with_files)
        [files] = events_with_files.get('files', [])
        self.assertIn('path', files)
        self.assertEqual('/tmp/install.log', files.get('path', ''))

    def test_interfacesd_eth0_removed(self):
        """ Check that curtin has removed /etc/network/interfaces.d/eth0.cfg
            by examining the output of a find /etc/network > find_interfaces.d
        """
        interfacesd = self.load_collect_file("find_interfacesd")
        self.assertNotIn("/etc/network/interfaces.d/eth0.cfg",
                         interfacesd.split("\n"))

    def test_installed_correct_kernel_package(self):
        """ Test curtin installs the correct kernel package.  """

        # target_distro is set for non-ubuntu targets
        if self.target_distro is not None:
            raise SkipTest("Can't check non-ubuntu kernel packages")

        kpackage = self.get_kernel_package()
        self.assertIn(kpackage, self.debian_packages)

    def run(self, result):
        super(VMBaseClass, self).run(result)
        self.record_result(result)

    def record_result(self, result):
        # record the result of this test to the class log dir
        # 'passed' gets False on failure, None (not set) on success.
        passed = result.test.passed in (True, None)
        all_good = passed and not os.path.exists(self.td.errors_file)

        if all_good:
            with open(self.td.success_file, "w") as fp:
                fp.write("all good\n")

        if not passed:
            data = {'errors': 1}
            if os.path.exists(self.td.success_file):
                os.unlink(self.td.success_file)
            if os.path.exists(self.td.errors_file):
                with open(self.td.errors_file, "r") as fp:
                    data = json.loads(fp.read())
                data['errors'] += 1

            with open(self.td.errors_file, "w") as fp:
                fp.write(json.dumps(data, indent=2, sort_keys=True,
                                    separators=(',', ': ')) + "\n")

    @property
    def debian_packages(self):
        if self._debian_packages is None:
            data = self.load_collect_file("debian-packages.txt")
            pkgs = {}
            for line in data.splitlines():
                # lines are <status>\t<
                status, pkg, ver = line.split('\t')
                pkgs[pkg] = {'status': status, 'version': ver}
            self._debian_packages = pkgs
        return self._debian_packages


class PsuedoVMBaseClass(VMBaseClass):
    # This mimics much of the VMBaseClass just with faster setUpClass
    # The tests here will fail only if CURTIN_VMTEST_DEBUG_ALLOW_FAIL
    # is set to a true value.  This allows the code to mostly run
    # during a 'make vmtest' (keeping it running) but not to break test.
    #
    # boot_timeouts is a dict of {'purpose': 'mesg'}
    # boot_results controls what happens when boot_system is called
    # a dictionary with key of the 'purpose'
    # inside each dictionary:
    #   timeout_msg: a message for a TimeoutException to raise.
    #   timeout: the value to pass as timeout to exception
    #   exit: the exit value of a CalledProcessError to raise
    #   console_log: what to write into the console log for that boot
    boot_results = {
        'install': {'timeout': 0, 'exit': 0},
        'first_boot': {'timeout': 0, 'exit': 0},
    }
    console_log_pass = '\n'.join([
        'Psuedo console log', INSTALL_PASS_MSG])
    allow_test_fails = get_env_var_bool('CURTIN_VMTEST_DEBUG_ALLOW_FAIL',
                                        False)

    @classmethod
    def collect_output(cls):
        logger.debug('Psuedo extracting output disk')
        with open(cls.collect_path("fstab"), "w") as fp:
            fp.write('\n'.join(("# psuedo fstab",
                                "LABEL=root / ext4 defaults 0 1")))

        logger.debug('Psudeo webhooks-events.json')
        webhooks = os.path.join(cls.td.logs, 'webhooks-events.json')
        with open(webhooks, "w") as fp:
            fp.write('[]')

    @classmethod
    def get_test_files(cls):
        """Return tuple of version info, and paths for root image,
           kernel, initrd, tarball."""

        def get_psuedo_path(name):
            return os.path.join(IMAGE_DIR, cls.release, cls.arch, name)

        return {
            'vmtest.root-image': get_psuedo_path('psuedo-root-image'),
            'squashfs': get_psuedo_path('psuedo-squashfs'),
            'boot-kernel': get_psuedo_path('psuedo-kernel'),
            'boot-initrd': get_psuedo_path('psuedo-initrd'),
            'vmtest.root-tgz': get_psuedo_path('psuedo-root-tgz')
        }

    @classmethod
    def boot_system(cls, cmd, console_log, proc_out, timeout, purpose):
        # this is separated for easy override in Psuedo classes
        data = {'timeout_msg': None, 'timeout': 0,
                'exit': 0, 'log': cls.console_log_pass}
        data.update(cls.boot_results.get(purpose, {}))

        def myboot():
            with open(console_log, "w") as fpout:
                fpout.write(data['log'])

            if data['timeout_msg']:
                raise TimeoutExpired(data['timeout_msg'],
                                     timeout=data['timeout'])

            if data['exit'] != 0:
                raise subprocess.CalledProcessError(cmd=cmd,
                                                    returncode=data['exit'])
            return True

        return boot_log_wrap(cls.__name__, myboot, cmd, console_log, timeout,
                             purpose)

    def test_fstab(self):
        pass

    def test_dname(self):
        pass

    def test_interfacesd_eth0_removed(self):
        pass

    def test_reporting_data(self):
        pass

    def test_installed_correct_kernel_package(self):
        pass

    def _maybe_raise(self, exc):
        if self.allow_test_fails:
            raise exc


def get_rfc4173(ip, port, target, user=None, pword=None,
                iuser=None, ipword=None, lun=1):

    rfc4173 = ''
    if user:
        rfc4173 += '%s:%s' % (user, pword)
    if iuser:
        # empty target user/password
        if not rfc4173:
            rfc4173 += ':'
        rfc4173 += ':%s:%s' % (iuser, ipword)
    # any auth specified?
    if rfc4173:
        rfc4173 += '@'
    rfc4173 += '%s::%s:%d:%s' % (ip, port, lun, target)
    return rfc4173


def find_error_context(err_match, contents, nrchars=200):
    context_start = err_match.start() - nrchars
    context_end = err_match.end() + nrchars
    # extract contents, split into lines, drop the first and last partials
    # recombine and return
    return "\n".join(contents[context_start:context_end].splitlines()[1:-1])


def check_install_log(install_log):
    # look if install is OK via curtin 'Installation ok"
    # if we dont find that, scan for known error messages and report
    # if we don't see any errors, fail with general error
    errors = []
    errmsg = None

    # regexps expected in curtin output
    install_pass = INSTALL_PASS_MSG
    install_fail = "({})".format("|".join([
                   'Installation\ failed',
                   'ImportError: No module named.*',
                   'Unexpected error while running command',
                   'E: Unable to locate package.*',
                   'Traceback.*most recent call last.*:']))

    install_is_ok = re.findall(install_pass, install_log)
    # always scan for errors
    found_errors = re.finditer(install_fail, install_log)
    if len(install_is_ok) == 0:
        errmsg = ('Failed to verify Installation is OK')

    for e in found_errors:
        errors.append(find_error_context(e, install_log))
        errmsg = ('Errors during curtin installer')

    return errmsg, errors


def get_apt_proxy():
    # get setting for proxy. should have same result as in tools/launch
    apt_proxy = os.environ.get('apt_proxy')
    if apt_proxy:
        return apt_proxy

    get_apt_config = textwrap.dedent("""
        command -v apt-config >/dev/null 2>&1
        out=$(apt-config shell x Acquire::HTTP::Proxy)
        out=$(sh -c 'eval $1 && echo $x' -- "$out")
        [ -n "$out" ]
        echo "$out"
    """)

    try:
        out = subprocess.check_output(['sh', '-c', get_apt_config])
        if isinstance(out, bytes):
            out = out.decode()
        out = out.rstrip()
        return out
    except subprocess.CalledProcessError:
        pass

    return None


def generate_user_data(collect_scripts=None, apt_proxy=None,
                       boot_cloudconf=None):
    # this returns the user data for the *booted* system
    # its a cloud-config-archive type, which is
    # just a list of parts.  the 'x-shellscript' parts
    # will be executed in the order they're put in
    if collect_scripts is None:
        collect_scripts = []
    parts = []
    base_cloudconfig = {
        'password': 'passw0rd',
        'chpasswd': {'expire': False},
        'power_state': {'mode': 'poweroff'},
        'network': {'config': 'disabled'},
    }

    ssh_keys, _err = util.subp(['tools/ssh-keys-list', 'cloud-config'],
                               capture=True)
    # precises' cloud-init version has limited support for cloud-config-archive
    # and expects cloud-config pieces to be appendable to a single file and
    # yaml.load()'able.  Resolve this by using yaml.dump() when generating
    # a list of parts
    parts = [{'type': 'text/cloud-config',
              'content': yaml.dump(base_cloudconfig, indent=1)},
             {'type': 'text/cloud-config', 'content': ssh_keys}]

    if boot_cloudconf is not None:
        parts.append({'type': 'text/cloud-config', 'content':
                      yaml.dump(boot_cloudconf, indent=1)})

    output_dir = '/mnt/output'
    output_dir_macro = 'OUTPUT_COLLECT_D'
    output_device = '/dev/disk/by-id/virtio-%s' % OUTPUT_DISK_NAME

    collect_prep = textwrap.dedent("mkdir -p " + output_dir)
    collect_post = textwrap.dedent("""\
        cd {output_dir}\n
        # remove any symlinks, but archive information about them.
        # %Y target's file type, %P = path, %l = target of symlink
        find -type l -printf "%Y\t%P\t%l\n" -delete > symlinks.txt
        tar -cf "{output_device}" .
        """).format(output_dir=output_dir, output_device=output_device)

    # copy /root for curtin config and install.log
    copy_rootdir = textwrap.dedent("cp -a /root " + output_dir)

    # failsafe poweroff runs on precise and centos only, where power_state does
    # not exist.
    failsafe_poweroff = textwrap.dedent("""#!/bin/sh -x
        [ -e /etc/centos-release -o -e /etc/redhat-release ] &&
            { shutdown -P now "Shutting down on centos"; }
        if grep -i -q precise /etc/os-release; then
            shutdown -P now "Shutting down on precise";
        fi
        exit 0;
        """)

    scripts = ([collect_prep] + [copy_rootdir] + collect_scripts +
               [collect_post] + [failsafe_poweroff])

    for part in scripts:
        if not part.startswith("#!"):
            part = "#!/bin/sh -x\n" + part
        part = part.replace(output_dir_macro, output_dir)
        logger.debug('Cloud config archive content (pre-json):' + part)
        parts.append({'content': part, 'type': 'text/x-shellscript'})
    return '#cloud-config-archive\n' + json.dumps(parts, indent=1)


def clean_working_dir(tdir, result, keep_pass, keep_fail):
    if result:
        keep = keep_pass
    else:
        keep = keep_fail

    # result, keep-mode
    rkm = 'result=%s keep=%s' % ('pass' if result else 'fail', keep)

    if len(keep) == 1 and keep[0] == "all":
        logger.debug('Keeping tmpdir %s [%s]', tdir, rkm)
    elif len(keep) == 1 and keep[0] == "none":
        logger.debug('Removing tmpdir %s [%s]', tdir, rkm)
        shutil.rmtree(tdir)
    else:
        to_clean = [d for d in os.listdir(tdir) if d not in keep]
        logger.debug('Pruning dirs in %s [%s]: %s',
                     tdir, rkm, ','.join(to_clean))
        for d in to_clean:
            cpath = os.path.join(tdir, d)
            if os.path.isdir(cpath):
                shutil.rmtree(os.path.join(tdir, d))
            else:
                os.unlink(cpath)

    return


def apply_keep_settings(success=None, fail=None):
    data = {}
    flist = (
        (success, "CURTIN_VMTEST_KEEP_DATA_PASS", "pass", "none"),
        (fail, "CURTIN_VMTEST_KEEP_DATA_FAIL", "fail", "all"),
    )

    allowed = ("boot", "collect", "disks", "install", "logs", "none", "all")
    for val, ename, dname, default in flist:
        if val is None:
            val = os.environ.get(ename, default)
        toks = val.split(",")
        for name in toks:
            if name not in allowed:
                raise ValueError("'%s' had invalid token '%s'" % (ename, name))
        data[dname] = toks

    global KEEP_DATA
    KEEP_DATA.update(data)


def tar_disks(tmpdir, outfile="disks.tar", diskmatch=".img"):
    """ Tar up files in ``tmpdir``/disks that ends with the pattern supplied"""

    disks_dir = os.path.join(tmpdir, "disks")
    if os.path.exists(disks_dir):
        outfile = os.path.join(disks_dir, outfile)
        disks = [os.path.join(disks_dir, disk) for disk in
                 os.listdir(disks_dir) if disk.endswith(diskmatch)]
        cmd = ["tar", "--create", "--file=%s" % outfile,
               "--verbose", "--remove-files", "--sparse"]
        cmd.extend(disks)
        logger.info('Taring %s disks sparsely to %s', len(disks), outfile)
        util.subp(cmd, capture=True)
    else:
        logger.debug('No "disks" dir found in tmpdir: %s', tmpdir)


def boot_log_wrap(name, func, cmd, console_log, timeout, purpose):
    logger.debug("%s[%s]: booting with timeout=%s log=%s cmd: %s",
                 name, purpose, timeout, console_log, ' '.join(cmd))
    ret = None
    start = time.time()
    try:
        ret = func()
    finally:
        end = time.time()
        logger.info("%s[%s]: boot took %.02f seconds. returned %s",
                    name, purpose, end - start, ret)
    return ret


def get_lan_ip():
    (out, _) = util.subp(['ip', 'a'], capture=True)
    info = ip_a_to_dict(out)
    (routes, _) = util.subp(['route', '-n'], capture=True)
    gwdevs = [route.split()[-1] for route in routes.splitlines()
              if route.startswith('0.0.0.0') and 'UG' in route]
    if len(gwdevs) > 0:
        dev = gwdevs.pop()
        addr = info[dev].get('inet4')[0].get('address')
    else:
        raise OSError('could not get local ip address')
    return addr


apply_keep_settings()
logger = _initialize_logging()
