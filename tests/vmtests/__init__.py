import atexit
import datetime
import errno
import logging
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import textwrap
import time
import curtin.net as curtin_net
import curtin.util as util

from .image_sync import query as imagesync_query
from .image_sync import mirror as imagesync_mirror
from .helpers import check_call, TimeoutExpired
from unittest import TestCase

IMAGE_SRC_URL = os.environ.get(
    'IMAGE_SRC_URL',
    "http://maas.ubuntu.com/images/ephemeral-v2/daily/streams/v1/index.sjson")

IMAGE_DIR = os.environ.get("IMAGE_DIR", "/srv/images")
try:
    IMAGES_TO_KEEP = int(os.environ.get("IMAGES_TO_KEEP", 1))
except ValueError:
    raise ValueError("IMAGES_TO_KEEP in environment was not an integer")

DEFAULT_SSTREAM_OPTS = [
    '--keyring=/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg']

DEVNULL = open(os.devnull, 'w')
KEEP_DATA = {"pass": "none", "fail": "all"}
INSTALL_PASS_MSG = "Installation finished. No error reported."
IMAGE_SYNCS = []

DEFAULT_BRIDGE = os.environ.get("CURTIN_VMTEST_BRIDGE", "user")

_TOPDIR = None


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


def _initialize_logging():
    # Configure logging module to save output to disk and present it on
    # sys.stderr

    logger = logging.getLogger(__name__)
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


def get_images(src_url, local_d, release, arch, sync=True):
    # ensure that the image items (roottar, kernel, initrd)
    # we need for release and arch are available in base_dir.
    # returns updated ftypes dictionary {ftype: item_url}
    # TODO: move krel up as an parameter
    krel = release
    ftypes = {
        'vmtest.root-image': '',
        'vmtest.root-tgz': '',
        'boot-kernel': '',
        'boot-initrd': ''
    }
    common_filters = ['release=%s' % release, 'krel=%s' % krel,
                      'arch=%s' % arch]
    filters = ['ftype~(%s)' % ("|".join(ftypes.keys()))] + common_filters

    if sync:
        imagesync_mirror(output_d=local_d, source=src_url,
                         mirror_filters=common_filters,
                         max_items=IMAGES_TO_KEEP)

    query_str = 'query = %s' % (' '.join(filters))
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

    if not results and not sync:
        # try to fix this with a sync
        logger.info(fail_msg + "  Attempting to fix with an image sync. (%s)",
                    query_str)
        return get_images(src_url, local_d, release, arch, sync=True)
    elif not results:
        raise ValueError("Nothing found in query: %s" % query_str)

    missing = []
    expected = sorted(ftypes.keys())
    found = sorted(f.get('ftype') for f in results)
    if expected != found:
        raise ValueError("Query returned unexpected ftypes=%s. "
                         "Expected=%s" % (found, expected))
    for item in results:
        ftypes[item['ftype']] = item['item_url']

    missing = [(ftype, path) for ftype, path in ftypes.items()
               if not os.path.exists(path)]

    if len(missing):
        raise FileNotFoundError("missing files for ftypes: %s" % missing)

    return ftypes


class ImageStore:
    """Local mirror of MAAS images simplestreams data."""

    # By default sync on demand.
    sync = True

    # images are expected in dirs named <release>/<arch>/YYYYMMDD[.X]
    image_dir_re = re.compile(r"^[0-9]{4}[01][0-9][0123][0-9]([.][0-9])*$")

    def __init__(self, source_url, base_dir):
        """Initialize the ImageStore.

        source_url is the simplestreams source from where the images will be
        downloaded.
        base_dir is the target dir in the filesystem to keep the mirror.
        """
        self.source_url = source_url
        self.base_dir = base_dir
        if not os.path.isdir(self.base_dir):
            os.makedirs(self.base_dir)
        self.url = pathlib.Path(self.base_dir).as_uri()

    def get_image(self, release, arch):
        """Return local path for root image, kernel and initrd, tarball."""
        ftypes = get_images(
            self.source_url, self.base_dir, release, arch, self.sync)
        root_image_path = ftypes['vmtest.root-image']
        kernel_path = ftypes['boot-kernel']
        initrd_path = ftypes['boot-initrd']
        tarball = ftypes['vmtest.root-tgz']
        return (root_image_path, kernel_path, initrd_path, tarball)


class TempDir(object):
    boot = None
    collect = None
    disks = None
    install = None
    logs = None
    output_disk = None

    def __init__(self, name, user_data):
        # Create tmpdir
        self.tmpdir = os.path.join(_topdir(), name)
        try:
            os.mkdir(self.tmpdir)
        except OSError as e:
            if e.errno == errno.EEXIST:
                raise ValueError("name '%s' already exists in %s" %
                                 (name, _topdir))
            else:
                raise e

        # make subdirs
        self.collect = os.path.join(self.tmpdir, "collect")
        self.install = os.path.join(self.tmpdir, "install")
        self.boot = os.path.join(self.tmpdir, "boot")
        self.logs = os.path.join(self.tmpdir, "logs")
        self.disks = os.path.join(self.tmpdir, "disks")

        self.dirs = (self.collect, self.install, self.boot, self.logs,
                     self.disks)
        for d in self.dirs:
            os.mkdir(d)

        self.success_file = os.path.join(self.logs, "success")
        self.errors_file = os.path.join(self.logs, "errors.json")

        # write cloud-init for installed system
        meta_data_file = os.path.join(self.install, "meta-data")
        with open(meta_data_file, "w") as fp:
            fp.write("instance-id: inst-123\n")
        user_data_file = os.path.join(self.install, "user-data")
        with open(user_data_file, "w") as fp:
            fp.write(user_data)

        # create target disk
        logger.debug('Creating target disk')
        self.target_disk = os.path.join(self.disks, "install_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "qcow2",
                              self.target_disk, "10G"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create seed.img for installed system's cloud init
        logger.debug('Creating seed disk')
        self.seed_disk = os.path.join(self.boot, "seed.img")
        subprocess.check_call(["cloud-localds", self.seed_disk,
                              user_data_file, meta_data_file],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create output disk, mount ro
        logger.debug('Creating output disk')
        self.output_disk = os.path.join(self.boot, "output_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "raw",
                              self.output_disk, "10M"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.check_call(["mkfs.ext2", "-F", self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def collect_output(self):
        logger.debug('extracting output disk')
        subprocess.check_call(['tar', '-C', self.collect, '-xf',
                               self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)


class VMBaseClass(TestCase):
    __test__ = False
    disk_to_check = {}
    fstab_expected = {}
    extra_kern_args = None
    recorded_errors = 0
    recorded_failures = 0
    image_store_class = ImageStore
    collect_scripts = []
    interactive = False
    conf_file = "examples/tests/basic.yaml"
    extra_disks = []
    boot_timeout = 300
    install_timeout = 600

    # these get set from base_vm_classes
    release = None
    arch = None

    @classmethod
    def setUpClass(cls):
        setup_start = time.time()
        logger.info('Starting setup for testclass: {}'.format(cls.__name__))
        # get boot img
        image_store = cls.image_store_class(IMAGE_SRC_URL, IMAGE_DIR)
        # Disable sync if env var is set.
        image_store.sync = get_env_var_bool('CURTIN_VMTEST_IMAGE_SYNC', False)
        logger.debug("Image sync = %s", image_store.sync)
        (boot_img, boot_kernel, boot_initrd, tarball) = image_store.get_image(
            cls.release, cls.arch)

        # set up tempdir
        cls.td = TempDir(
            name=cls.__name__,
            user_data=generate_user_data(collect_scripts=cls.collect_scripts))
        logger.info('Using tempdir: {}'.format(cls.td.tmpdir))

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
        cmd = ["tools/launch", "-v", dowait]
        if not cls.interactive:
            cmd.extend(["--silent", "--power=off"])

        cmd.extend(["--serial-log=" + cls.install_log])

        if cls.extra_kern_args:
            cmd.extend(["--append=" + cls.extra_kern_args])

        # publish the root tarball
        install_src = "PUBURL/" + os.path.basename(tarball)
        cmd.append("--publish=%s" % tarball)

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
            if hwaddr:
                macs.append(hwaddr)
        netdevs = []
        if len(macs) > 0:
            for mac in macs:
                netdevs.extend(["--netdev=" + DEFAULT_BRIDGE +
                                ",mac={}".format(mac)])
        else:
            netdevs.extend(["--netdev=" + DEFAULT_BRIDGE])

        # build disk arguments
        extra_disks = []
        for (disk_no, disk_sz) in enumerate(cls.extra_disks):
            dpath = os.path.join(cls.td.disks, 'extra_disk_%d.img' % disk_no)
            extra_disks.extend(['--disk', '{}:{}'.format(dpath, disk_sz)])

        # proxy config
        configs = [cls.conf_file]
        proxy = get_apt_proxy()
        if get_apt_proxy is not None:
            proxy_config = os.path.join(cls.td.install, 'proxy.cfg')
            with open(proxy_config, "w") as fp:
                fp.write(json.dumps({'apt_proxy': proxy}) + "\n")
            configs.append(proxy_config)

        cmd.extend(netdevs + ["--disk", cls.td.target_disk] + extra_disks +
                   [boot_img, "--kernel=%s" % boot_kernel, "--initrd=%s" %
                    boot_initrd, "--", "curtin", "-vv", "install"] +
                   ["--config=%s" % f for f in configs] +
                   [install_src])

        # run vm with installer
        lout_path = os.path.join(cls.td.logs, "install-launch.out")
        logger.info('Running curtin installer: {}'.format(cls.install_log))
        try:
            with open(lout_path, "wb") as fpout:
                cls.boot_system(cmd, timeout=cls.install_timeout,
                                console_log=cls.install_log, proc_out=fpout,
                                purpose="install")
        except TimeoutExpired:
            logger.error('Curtin installer failed with timeout')
            cls.tearDownClass()
            raise
        finally:
            if os.path.exists(cls.install_log):
                with open(cls.install_log, 'r', encoding='utf-8') as l:
                    logger.debug(
                        u'Serial console output:\n{}'.format(l.read()))
            else:
                logger.warn("Boot for install did not produce a console log.")

        logger.debug('')
        try:
            if os.path.exists(cls.install_log):
                with open(cls.install_log) as l:
                    install_log = l.read()
                errmsg, errors = check_install_log(install_log)
                if errmsg:
                    for e in errors:
                        logger.error(e)
                    logger.error(errmsg)
                    raise Exception(cls.__name__ + ":" + errmsg)
                else:
                    logger.info('Install OK')
            else:
                logger.info('Install Failed')
                raise Exception("No install log was produced")
        except:
            cls.tearDownClass()
            raise

        # drop the size parameter if present in extra_disks
        extra_disks = [x if ":" not in x else x.split(':')[0]
                       for x in extra_disks]
        # create xkvm cmd
        cmd = (["tools/xkvm", "-v", dowait] + netdevs +
               ["--disk", cls.td.target_disk, "--disk", cls.td.output_disk] +
               extra_disks +
               ["--", "-drive",
                "file=%s,if=virtio,media=cdrom" % cls.td.seed_disk,
                "-m", "1024"])
        if not cls.interactive:
            cmd.extend(["-nographic", "-serial", "file:" + cls.boot_log])

        # run vm with installed system, fail if timeout expires
        try:
            logger.info('Booting target image: {}'.format(cls.boot_log))
            logger.debug('{}'.format(" ".join(cmd)))
            xout_path = os.path.join(cls.td.logs, "boot-xkvm.out")
            with open(xout_path, "wb") as fpout:
                cls.boot_system(cmd, console_log=cls.boot_log, proc_out=fpout,
                                timeout=cls.boot_timeout, purpose="first_boot")
        except Exception as e:
            logger.error('Booting after install failed: %s', e)
            cls.tearDownClass()
            raise e
        finally:
            if os.path.exists(cls.boot_log):
                with open(cls.boot_log, 'r', encoding='utf-8') as l:
                    logger.debug(
                        u'Serial console output:\n{}'.format(l.read()))
            else:
                    logger.warn("Booting after install not produce"
                                " a console log.")

        # mount output disk
        try:
            cls.td.collect_output()
        except:
            cls.tearDownClass()
            raise
        logger.info(
            "%s: setUpClass finished. took %.02f seconds. Running testcases.",
            cls.__name__, time.time() - setup_start)

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
    def get_network_state(cls):
        return cls.network_state

    @classmethod
    def get_expected_etc_network_interfaces(cls):
        return curtin_net.render_interfaces(cls.network_state)

    @classmethod
    def get_expected_etc_resolvconf(cls):
        ifaces = {}
        eni = curtin_net.render_interfaces(cls.network_state)
        curtin_net.parse_deb_config_data(ifaces, eni, None)
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

    # Misc functions that are useful for many tests
    def output_files_exist(self, files):
        for f in files:
            self.assertTrue(os.path.exists(os.path.join(self.td.collect, f)))

    def check_file_strippedline(self, filename, search):
        with open(os.path.join(self.td.collect, filename), "r") as fp:
            data = list(i.strip() for i in fp.readlines())
        self.assertIn(search, data)

    def check_file_regex(self, filename, regex):
        with open(os.path.join(self.td.collect, filename), "r") as fp:
            data = fp.read()
        self.assertRegex(data, regex)

    def get_blkid_data(self, blkid_file):
        with open(os.path.join(self.td.collect, blkid_file)) as fp:
            data = fp.read()
        ret = {}
        for line in data.splitlines():
            if line == "":
                continue
            val = line.split('=')
            ret[val[0]] = val[1]
        return ret

    def test_fstab(self):
        if (os.path.exists(self.td.collect + "fstab") and
                self.fstab_expected is not None):
            with open(os.path.join(self.td.collect, "fstab")) as fp:
                fstab_lines = fp.readlines()
            fstab_entry = None
            for line in fstab_lines:
                for device, mntpoint in self.fstab_expected.items():
                        if device in line:
                            fstab_entry = line
                            self.assertIsNotNone(fstab_entry)
                            self.assertEqual(fstab_entry.split(' ')[1],
                                             mntpoint)

    def test_dname(self):
        fpath = os.path.join(self.td.collect, "ls_dname")
        if (os.path.exists(fpath) and self.disk_to_check is not None):
            with open(fpath, "r") as fp:
                contents = fp.read().splitlines()
            for diskname, part in self.disk_to_check.items():
                if part is not 0:
                    link = diskname + "-part" + str(part)
                    self.assertIn(link, contents)
                self.assertIn(diskname, contents)

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


class PsuedoImageStore(object):
    def __init__(self, source_url, base_dir):
        self.source_url = source_url
        self.base_dir = base_dir

    def get_image(self, release, arch):
        """Return local path for root image, kernel and initrd, tarball."""
        names = ['psuedo-root-image', 'psuedo-kernel', 'psuedo-initrd',
                 'psuedo-tarball']
        return [os.path.join(self.base_dir, release, arch, f) for f in names]


class PsuedoVMBaseClass(VMBaseClass):
    # This mimics much of the VMBaseClass just with faster setUpClass
    # The tests here will fail only if CURTIN_VMTEST_DEBUG_ALLOW_FAIL
    # is set to a true value.  This allows the code to mostly run
    # during a 'make vmtest' (keeping it running) but not to break test.
    #
    # boot_timeouts is a dict of {'purpose': 'mesg'}
    image_store_class = PsuedoImageStore
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

    def collect_output(self):
        logger.debug('Psuedo extracting output disk')
        with open(os.path.join(self.td.collect, "fstab")) as fp:
            fp.write('\n'.join(("# psuedo fstab",
                                "LABEL=root / ext4 defaults 0 1")))

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

    def _maybe_raise(self, exc):
        if self.allow_test_fails:
            raise exc


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
                   'E: Unable to locate package.*']))

    install_is_ok = re.findall(install_pass, install_log)
    if len(install_is_ok) == 0:
        errors = re.findall(install_fail, install_log)
        if len(errors) > 0:
            for e in errors:
                logger.error(e)
            errmsg = ('Errors during curtin installer')
        else:
            errmsg = ('Failed to verify Installation is OK')

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


def generate_user_data(collect_scripts=None, apt_proxy=None):
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
    }

    ssh_keys, _err = util.subp(['tools/ssh-keys-list', 'cloud-config'],
                               capture=True)
    parts = [{'type': 'text/cloud-config',
              'content': json.dumps(base_cloudconfig, indent=1)},
             {'type': 'text/cloud-config', 'content': ssh_keys}]

    output_dir_macro = 'OUTPUT_COLLECT_D'
    output_dir = '/mnt/output'
    output_device = '/dev/vdb'

    collect_prep = textwrap.dedent("mkdir -p " + output_dir)
    collect_post = textwrap.dedent(
        'tar -C "%s" -cf "%s" .' % (output_dir, output_device))

    # failsafe poweroff runs on precise only, where power_state does
    # not exist.
    precise_poweroff = textwrap.dedent("""#!/bin/sh
        [ "$(lsb_release -sc)" = "precise" ] || exit 0;
        shutdown -P now "Shutting down on precise"
        """)

    scripts = ([collect_prep] + collect_scripts + [collect_post] +
               [precise_poweroff])

    for part in scripts:
        if not part.startswith("#!"):
            part = "#!/bin/sh\n" + part
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


apply_keep_settings()
logger = _initialize_logging()
