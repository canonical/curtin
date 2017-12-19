import ast
import datetime
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import curtin.net as curtin_net

from .helpers import check_call

IMAGE_DIR = os.environ.get("IMAGE_DIR", "/srv/images")

DEVNULL = open(os.devnull, 'w')


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Configure logging module to save output to disk and present it on
# sys.stderr
now = datetime.datetime.now().isoformat()
fh = logging.FileHandler(
    '/tmp/{}-vmtest.log'.format(now), mode='w', encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)


class ImageStore:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        if not os.path.isdir(self.base_dir):
            os.makedirs(self.base_dir)

    def get_image(self, repo, release, arch):
        # query sstream for root image
        logger.debug(
            'Query simplestreams for root image: '
            'release={release} arch={arch}'.format(release=release, arch=arch))
        cmd = ["tools/usquery", "--max=1", repo, "release=%s" % release,
               "krel=%s" % release, "arch=%s" % arch,
               "item_name=root-image.gz"]
        logger.debug(" ".join(cmd))
        out = subprocess.check_output(cmd)
        logger.debug(out)
        sstream_data = ast.literal_eval(bytes.decode(out))

        # Check if we already have the image
        logger.debug('Checking cache for image')
        checksum = ""
        release_dir = os.path.join(self.base_dir, repo, release, arch,
                                   sstream_data['version_name'])

        def p(x):
            return os.path.join(release_dir, x)

        if os.path.isdir(release_dir) and os.path.exists(p("root-image.gz")):
            # get checksum of cached image
            with open(p("root-image.gz"), "rb") as fp:
                checksum = hashlib.sha256(fp.read()).hexdigest()
        if not os.path.exists(p("root-image.gz")) or \
                checksum != sstream_data['sha256'] or \
                not os.path.exists(p("root-image")) or \
                not os.path.exists(p("root-image-kernel")) or \
                not os.path.exists(p("root-image-initrd")):
            # clear dir, download, and extract image
            logger.debug('Image not found, downloading...')
            shutil.rmtree(release_dir, ignore_errors=True)
            os.makedirs(release_dir)
            subprocess.check_call(
                ["wget", "-c", sstream_data['item_url'], "-O",
                 p("root-image.gz")])
            logger.debug('Converting image format')
            subprocess.check_call(["tools/maas2roottar", p("root-image.gz")])
        return (p("root-image"), p("root-image-kernel"),
                p("root-image-initrd"))


class TempDir:
    def __init__(self, user_data):
        # Create tmpdir
        self.tmpdir = tempfile.mkdtemp()

        # write cloud-init for installed system
        meta_data_file = os.path.join(self.tmpdir, "meta-data")
        with open(meta_data_file, "w") as fp:
            fp.write("instance-id: inst-123\n")
        user_data_file = os.path.join(self.tmpdir, "user-data")
        with open(user_data_file, "w") as fp:
            fp.write(user_data)

        # make mnt dir
        self.mnt = os.path.join(self.tmpdir, "mnt")
        os.mkdir(self.mnt)

        # create target disk
        logger.debug('Creating target disk')
        self.target_disk = os.path.join(self.tmpdir, "install_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "qcow2",
                              self.target_disk, "10G"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create seed.img for installed system's cloud init
        logger.debug('Creating seed disk')
        self.seed_disk = os.path.join(self.tmpdir, "seed.img")
        subprocess.check_call(["cloud-localds", self.seed_disk,
                              user_data_file, meta_data_file],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create output disk, mount ro
        logger.debug('Creating output disk')
        self.output_disk = os.path.join(self.tmpdir, "output_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "raw",
                              self.output_disk, "10M"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.check_call(["/sbin/mkfs.ext2", "-F", self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def mount_output_disk(self):
        logger.debug('extracting output disk')
        subprocess.check_call(['tar', '-C', self.mnt, '-xf', self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def __del__(self):
        # remove tempdir
        shutil.rmtree(self.tmpdir)


class VMBaseClass:
    @classmethod
    def setUpClass(self):
        logger.debug('Acquiring boot image')
        # get boot img
        image_store = ImageStore(IMAGE_DIR)
        (boot_img, boot_kernel, boot_initrd) = image_store.get_image(
            self.repo, self.release, self.arch)

        # set up tempdir
        logger.debug('Setting up tempdir')
        self.td = TempDir(self.user_data)
        self.install_log = os.path.join(self.td.tmpdir, 'install-serial.log')
        self.boot_log = os.path.join(self.td.tmpdir, 'boot-serial.log')

        # create launch cmd
        cmd = ["tools/launch", "-v"]
        if not self.interactive:
            cmd.extend(["--silent", "--power=off"])

        cmd.extend(["--serial-log=" + self.install_log])

        # check for network configuration
        self.network_state = curtin_net.parse_net_config(self.conf_file)
        logger.debug("Network state: {}".format(self.network_state))

        # build -n arg list with macaddrs from net_config physical config
        macs = []
        interfaces = {}
        if self.network_state:
            interfaces = self.network_state.get('interfaces')
        for ifname in interfaces:
            logger.debug("Interface name: {}".format(ifname))
            iface = interfaces.get(ifname)
            hwaddr = iface.get('mac_address')
            if hwaddr:
                macs.append(hwaddr)
        netdevs = []
        if len(macs) > 0:
            for mac in macs:
                netdevs.extend(["--netdev=user,mac={}".format(mac)])
        else:
            netdevs.extend(["--netdev=user"])

        # build disk arguments
        extra_disks = []
        for (disk_no, disk_sz) in enumerate(self.extra_disks):
            dpath = os.path.join(self.td.tmpdir, 'extra_disk_%d.img' % disk_no)
            extra_disks.extend(['--disk', '{}:{}'.format(dpath, disk_sz)])

        cmd.extend(netdevs + ["--disk", self.td.target_disk] + extra_disks +
                   [boot_img, "--kernel=%s" % boot_kernel, "--initrd=%s" %
                    boot_initrd, "--", "curtin", "-vv",
                    "install", "--config=%s" % self.conf_file, "cp:///"])

        # run vm with installer
        lout_path = os.path.join(self.td.tmpdir, "launch-install.out")
        try:
            logger.debug('Running curtin installer')
            logger.debug('{}'.format(" ".join(cmd)))
            with open(lout_path, "wb") as fpout:
                check_call(cmd, timeout=self.install_timeout,
                           stdout=fpout, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            logger.debug('Curtin installer failed')
            raise
        finally:
            if os.path.exists(self.install_log):
                with open(self.install_log, 'r', encoding='utf-8') as l:
                    logger.debug(
                        u'Serial console output:\n{}'.format(l.read()))
            else:
                logger.warn("Did not have a serial log file from launch.")

        logger.debug('')
        if os.path.exists(self.install_log):
            logger.debug('Checking curtin install output for errors')
            with open(self.install_log) as l:
                install_log = l.read()
            errors = re.findall(
                '\[.*\]\ cloud-init.*:.*Installation\ failed', install_log)
            if len(errors) > 0:
                for e in errors:
                    logger.debug(e)
                logger.debug('Errors during curtin installer')
                raise Exception('Errors during curtin installer')
            else:
                logger.debug('Install OK')
        else:
            raise Exception("No install log was produced")

        # drop the size parameter if present in extra_disks
        extra_disks = [x if ":" not in x else x.split(':')[0]
                       for x in extra_disks]
        # create xkvm cmd
        cmd = (["tools/xkvm", "-v"] + netdevs + ["--disk", self.td.target_disk,
               "--disk", self.td.output_disk] + extra_disks +
               ["--", "-drive",
                "file=%s,if=virtio,media=cdrom" % self.td.seed_disk,
                "-m", "1024"])
        if not self.interactive:
            cmd.extend(["-nographic", "-serial", "file:" + self.boot_log])

        # run vm with installed system, fail if timeout expires
        try:
            logger.debug('Booting target image')
            logger.debug('{}'.format(" ".join(cmd)))
            xout_path = os.path.join(self.td.tmpdir, "xkvm-boot.out")
            with open(xout_path, "wb") as fpout:
                check_call(cmd, timeout=self.boot_timeout,
                           stdout=fpout, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            logger.debug('Booting after install failed')
            raise
        finally:
            if os.path.exists(self.boot_log):
                with open(self.boot_log, 'r', encoding='utf-8') as l:
                    logger.debug(
                        u'Serial console output:\n{}'.format(l.read()))

        # mount output disk
        self.td.mount_output_disk()
        logger.debug('Ready for testcases')

    @classmethod
    def tearDownClass(self):
        logger.debug('Removing launch logfile')

    @classmethod
    def expected_interfaces(self):
        expected = []
        interfaces = {}
        if self.network_state:
            interfaces = self.network_state.get('interfaces')
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
    def get_network_state(self):
        return self.network_state

    @classmethod
    def get_expected_etc_network_interfaces(self):
        return curtin_net.render_interfaces(self.network_state)

    @classmethod
    def get_expected_etc_resolvconf(self):
        ifaces = {}
        eni = curtin_net.render_interfaces(self.network_state)
        curtin_net.parse_deb_config_data(ifaces, eni, None)
        return ifaces

    # Misc functions that are useful for many tests
    def output_files_exist(self, files):
        for f in files:
            self.assertTrue(os.path.exists(os.path.join(self.td.mnt, f)))

    def get_blkid_data(self, blkid_file):
        with open(os.path.join(self.td.mnt, blkid_file)) as fp:
            data = fp.read()
        ret = {}
        for line in data.splitlines():
            if line == "":
                continue
            val = line.split('=')
            ret[val[0]] = val[1]
        return ret
