import ast
import datetime
import hashlib
import logging
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib
import curtin.net as curtin_net

from .helpers import check_call

IMAGE_SRC_URL = os.environ.get(
    'IMAGE_SRC_URL',
    "http://maas.ubuntu.com/images/ephemeral-v2/daily/streams/v1/index.sjson")

IMAGE_DIR = os.environ.get("IMAGE_DIR", "/srv/images")
DEFAULT_SSTREAM_OPTS = [
    '--max=1', '--keyring=/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg']
DEFAULT_FILTERS = ['arch=amd64', 'item_name=root-image.gz']


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
    """Local mirror of MAAS images simplestreams data."""

    # By default sync on demand.
    sync = True

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

    def convert_image(self, root_image_path):
        """Use maas2roottar to unpack root-image, kernel and initrd."""
        logger.debug('Converting image format')
        subprocess.check_call(["tools/maas2roottar", root_image_path])

    def sync_images(self, filters=DEFAULT_FILTERS):
        """Sync MAAS images from source_url simplestreams."""
        try:
            out = subprocess.check_output(
                ['sstream-mirror', '--help'], stderr=subprocess.STDOUT)
            if isinstance(out, bytes):
                out = out.decode()
            if '--progress' in out:
                progress = ['--progress']
        except subprocess.CalledProcessError:
            progress = []

        cmd = ['sstream-mirror'] + DEFAULT_SSTREAM_OPTS + progress + [
            self.source_url, self.base_dir] + filters
        logger.debug('Syncing images {}'.format(cmd))
        out = subprocess.check_output(cmd)
        logger.debug(out)

    def get_image(self, release, arch, filters=None):
        """Return local path for root image, kernel and initrd."""
        if filters is None:
            filters = [
                'release=%s' % release, 'krel=%s' % release, 'arch=%s' % arch]
        # Query local sstream for compressed root image.
        logger.debug(
            'Query simplestreams for root image: %s', filters)
        cmd = ['sstream-query'] + DEFAULT_SSTREAM_OPTS + [
            self.url, 'item_name=root-image.gz'] + filters
        logger.debug(" ".join(cmd))
        out = subprocess.check_output(cmd)
        logger.debug(out)
        # No output means we have no images locally, so try to sync.
        # If there's output, ImageStore.sync decides if images should be
        # synced or not.
        if not out or self.sync:
            self.sync_images(filters=filters)
            out = subprocess.check_output(cmd)
        sstream_data = ast.literal_eval(bytes.decode(out))
        root_image_gz = urllib.parse.urlsplit(sstream_data['item_url']).path
        # Make sure the image checksums correctly. Ideally
        # sstream-[query,mirror] would make the verification for us.
        # See https://bugs.launchpad.net/simplestreams/+bug/1513625
        with open(root_image_gz, "rb") as fp:
            checksum = hashlib.sha256(fp.read()).hexdigest()
        if checksum != sstream_data['sha256']:
            self.sync_images(filters=filters)
            out = subprocess.check_output(cmd)
            sstream_data = ast.literal_eval(bytes.decode(out))
            root_image_gz = urllib.parse.urlsplit(
                sstream_data['item_url']).path

        image_dir = os.path.dirname(root_image_gz)
        root_image_path = os.path.join(image_dir, 'root-image')
        kernel_path = os.path.join(image_dir, 'root-image-kernel')
        initrd_path = os.path.join(image_dir, 'root-image-initrd')
        # Check if we need to unpack things from the compressed image.
        if (not os.path.exists(root_image_path) or
                not os.path.exists(kernel_path) or
                not os.path.exists(initrd_path)):
            self.convert_image(root_image_gz)
        return (root_image_path, kernel_path, initrd_path)


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
        if get_env_var_bool('CURTIN_VMTEST_KEEP_DATA', False):
            # remove tempdir
            shutil.rmtree(self.tmpdir)


class VMBaseClass:
    disk_to_check = {}
    fstab_expected = {}
    extra_kern_args = None

    @classmethod
    def setUpClass(self):
        logger.debug('Acquiring boot image')
        # get boot img
        image_store = ImageStore(IMAGE_SRC_URL, IMAGE_DIR)
        # Disable sync if env var is set.
        if get_env_var_bool('CURTIN_VMTEST_IMAGE_SYNC', False):
            logger.debug("Images not synced.")
            image_store.sync = False
        (boot_img, boot_kernel, boot_initrd) = image_store.get_image(
            self.release, self.arch)

        # set up tempdir
        logger.debug('Setting up tempdir')
        self.td = TempDir(
            generate_user_data(collect_scripts=self.collect_scripts))
        self.install_log = os.path.join(self.td.tmpdir, 'install-serial.log')
        self.boot_log = os.path.join(self.td.tmpdir, 'boot-serial.log')

        # create launch cmd
        cmd = ["tools/launch", "-v"]
        if not self.interactive:
            cmd.extend(["--silent", "--power=off"])

        cmd.extend(["--serial-log=" + self.install_log])

        if self.extra_kern_args:
            cmd.extend(["--append=" + self.extra_kern_args])

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

        # proxy config
        configs = [self.conf_file]
        proxy = get_apt_proxy()
        if get_apt_proxy is not None:
            proxy_config = os.path.join(self.td.tmpdir, 'proxy.cfg')
            with open(proxy_config, "w") as fp:
                fp.write(json.dumps({'apt_proxy': proxy}) + "\n")
            configs.append(proxy_config)

        cmd.extend(netdevs + ["--disk", self.td.target_disk] + extra_disks +
                   [boot_img, "--kernel=%s" % boot_kernel, "--initrd=%s" %
                    boot_initrd, "--", "curtin", "-vv", "install"] +
                   ["--config=%s" % f for f in configs] +
                   ["cp:///"])

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

    def check_file_strippedline(self, filename, search):
        with open(os.path.join(self.td.mnt, filename), "r") as fp:
            data = list(i.strip() for i in fp.readlines())
        self.assertIn(search, data)

    def check_file_regex(self, filename, regex):
        with open(os.path.join(self.td.mnt, filename), "r") as fp:
            data = fp.read()
        self.assertRegex(data, regex)

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

    def test_fstab(self):
        if (os.path.exists(self.td.mnt + "fstab") and
                self.fstab_expected is not None):
            with open(os.path.join(self.td.mnt, "fstab")) as fp:
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
        if (os.path.exists(self.td.mnt + "ls_dname") and
                self.disk_to_check is not None):
            with open(os.path.join(self.td.mnt, "ls_dname"), "r") as fp:
                contents = fp.read().splitlines()
            for diskname, part in self.disk_to_check.items():
                if part is not 0:
                    link = diskname + "-part" + str(part)
                    self.assertIn(link, contents)
                self.assertIn(diskname, contents)


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

    parts = [{'type': 'text/cloud-config',
              'content': json.dumps(base_cloudconfig, indent=1)}]

    output_dir_macro = 'OUTPUT_COLLECT_D'
    output_dir = '/mnt/output'
    output_device = '/dev/vdb'

    collect_prep = textwrap.dedent("mkdir -p " + output_dir)
    collect_post = textwrap.dedent(
        'tar -C "%s" -cf "%s" .' % (output_dir, output_device))

    scripts = [collect_prep] + collect_scripts + [collect_post]

    for part in scripts:
        if not part.startswith("#!"):
            part = "#!/bin/sh\n" + part
        part = part.replace(output_dir_macro, output_dir)
        logger.debug('Cloud config archive content (pre-json):' + part)
        parts.append({'content': part, 'type': 'text/x-shellscript'})
    return '#cloud-config-archive\n' + json.dumps(parts, indent=1)


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
