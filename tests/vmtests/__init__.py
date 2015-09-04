import ast
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import curtin.net as curtin_net

IMAGE_DIR = "/srv/images"

DEVNULL = open(os.devnull, 'w')


class ImageStore:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        if not os.path.isdir(self.base_dir):
            os.makedirs(self.base_dir)

    def get_image(self, repo, release, arch):
        # query sstream for root image
        print('Query simplestreams for root image: '
              'release={release} arch={arch}'.format(release=release,
                                                     arch=arch))
        cmd = ["tools/usquery", "--max=1", repo, "release=%s" % release,
               "krel=%s" % release, "arch=%s" % arch,
               "item_name=root-image.gz"]
        print(" ".join(cmd))
        out = subprocess.check_output(cmd)
        print(out)
        sstream_data = ast.literal_eval(bytes.decode(out))

        # Check if we already have the image
        print('Checking cache for image')
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
            print('Image not found, downloading...')
            shutil.rmtree(release_dir, ignore_errors=True)
            os.makedirs(release_dir)
            subprocess.check_call(
                ["wget", "-c", sstream_data['item_url'], "-O",
                 p("root-image.gz")])
            print('Converting image format')
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
        print('Creating target disk')
        self.target_disk = os.path.join(self.tmpdir, "install_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "qcow2",
                              self.target_disk, "10G"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create seed.img for installed system's cloud init
        print('Creating seed disk')
        self.seed_disk = os.path.join(self.tmpdir, "seed.img")
        subprocess.check_call(["cloud-localds", self.seed_disk,
                              user_data_file, meta_data_file],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

        # create output disk, mount ro
        print('Creating output disk')
        self.output_disk = os.path.join(self.tmpdir, "output_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "raw",
                              self.output_disk, "10M"],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.check_call(["/sbin/mkfs.ext2", "-F", self.output_disk],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def mount_output_disk(self):
        print('Mounting output disk')
        subprocess.check_call(["fuseext2", "-o", "rw+", self.output_disk,
                              self.mnt],
                              stdout=DEVNULL, stderr=subprocess.STDOUT)

    def __del__(self):
        # remove tempdir
        shutil.rmtree(self.tmpdir)


class VMBaseClass:
    @classmethod
    def setUpClass(self):
        print('Acquiring boot image')
        # get boot img
        image_store = ImageStore(IMAGE_DIR)
        (boot_img, boot_kernel, boot_initrd) = image_store.get_image(
            self.repo, self.release, self.arch)

        # set up tempdir
        print('Setting up tempdir')
        self.td = TempDir(self.user_data)

        # create launch cmd
        cmd = ["tools/launch"]
        if not self.interactive:
            cmd.extend(["--silent", "--power=off"])

        # check for network configuration
        self.network_state = curtin_net.parse_net_config(self.conf_file)
        print(self.network_state)

        # build -n arg list with macaddrs from net_config physical config
        macs = []
        interfaces = {}
        if self.network_state:
            interfaces = self.network_state.get('interfaces')
        for ifname in interfaces:
            print(ifname)
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
                    boot_initrd, "--", "curtin", "install", "--config=%s" %
                    self.conf_file, "cp:///"])

        # run vm with installer
        try:
            print('Running curtin installer')
            print('{}'.format(" ".join(cmd)))
            subprocess.check_call(cmd, timeout=self.install_timeout,
                                  stdout=DEVNULL, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            print('Curting installer failed')
            raise
        finally:
            if os.path.exists('serial.log'):
                with open('serial.log', 'r') as l:
                    print('Serial console output:\n{}'.format(l.read()))

        print('')
        print('Checking curtin install output for errors')
        with open('serial.log') as l:
            install_log = l.read()
            errors = re.findall('\[.*\]\ cloud-init.*:.*Installation\ failed',
                                install_log)
            if len(errors) > 0:
                for e in errors:
                    print(e)
                print('Errors during curtin installer')
                raise Exception('Errors during curtin installer')
            else:
                print('Install OK')

        # drop the size parameter if present in extra_disks
        extra_disks = [x if ":" not in x else x.split(':')[0]
                       for x in extra_disks]
        # create xkvm cmd
        cmd = (["tools/xkvm"] + netdevs + ["--disk", self.td.target_disk,
               "--disk", self.td.output_disk] + extra_disks +
               ["--", "-drive",
                "file=%s,if=virtio,media=cdrom" % self.td.seed_disk,
                "-m", "1024"])
        if not self.interactive:
            cmd.extend(["-nographic", "-serial", "file:%s" %
                       os.path.join(self.td.tmpdir, "serial.log")])

        # run vm with installed system, fail if timeout expires
        try:
            print('Booting target image')
            print('{}'.format(" ".join(cmd)))
            subprocess.check_call(cmd, timeout=self.boot_timeout,
                                  stdout=DEVNULL, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            print('Booting after install failed')
            raise
        finally:
            serial_log = os.path.join(self.td.tmpdir, 'serial.log')
            if os.path.exists(serial_log):
                with open(serial_log, 'r') as l:
                    # Encode the content in utf-8 so it can be printed.
                    log_content = l.read().encode('utf8')
                    print('Serial console output:\n{}'.format(log_content))

        # mount output disk
        self.td.mount_output_disk()
        print('Ready for testcases')

    @classmethod
    def tearDownClass(self):
        print('Removing launch logfile')
        subprocess.call(["fusermount", "-u", self.td.mnt])
        # remove launch logfile
        if os.path.exists("./serial.log"):
            os.remove("./serial.log")

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
