import ast
import hashlib
import os
import tempfile
import shutil
import subprocess

IMAGE_DIR = "/home/magicanus/code/curtin-vm-test"


class ImageStore:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        if not os.path.isdir(self.base_dir):
            os.makedirs(self.base_dir)

    def get_image(self, repo, release, arch):
        # query sstream for root image
        out = subprocess.check_output(
            ["tools/usquery", "--max=1", repo, "release=%s" % release,
             "arch=%s" % arch, "item_name=root-image.gz"])
        sstream_data = ast.literal_eval(bytes.decode(out))

        # Check if we already have the image
        checksum = ""
        release_dir = os.path.join(self.base_dir, repo, release, arch,
                                   sstream_data['version_name'])
        p = lambda x: os.path.join(release_dir, x)
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
            shutil.rmtree(release_dir, ignore_errors=True)
            os.makedirs(release_dir)
            subprocess.check_call(
                ["wget", "-c", sstream_data['item_url'], "-O",
                 p("root-image.gz")])
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
        self.target_disk = os.path.join(self.tmpdir, "install_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "qcow2",
                               self.target_disk, "10G"])

        # create seed.img for installed system's cloud init
        self.seed_disk = os.path.join(self.tmpdir, "seed.img")
        subprocess.check_call(["cloud-localds", self.seed_disk,
                               user_data_file, meta_data_file])

        # create output disk, mount ro
        self.output_disk = os.path.join(self.tmpdir, "output_disk.img")
        subprocess.check_call(["qemu-img", "create", "-f", "raw",
                               self.output_disk, "10M"])
        subprocess.check_call(["mkfs.ext2", self.output_disk])

    def mount_output_disk(self):
        subprocess.check_call(["fuseext2", "-o", "rw+", self.output_disk,
                               self.mnt])

    def __del__(self):
        # remove tempdir
        shutil.rmtree(self.tmpdir)


class VMBaseClass:
    @classmethod
    def setUpClass(self):
        # get boot img
        image_store = ImageStore(IMAGE_DIR)
        (boot_img, boot_kernel, boot_initrd) = image_store.get_image(
            self.repo, self.release, self.arch)

        # set up tempdir
        self.td = TempDir(self.user_data)

        # create launch cmd
        cmd = ["tools/launch"]
        if not self.interactive:
            cmd.extend(["--silent", "--power=off"])
        cmd.extend(["--netdev=user", "-d", self.td.target_disk,
                   boot_img, "--kernel=%s" % boot_kernel, "--initrd=%s" %
                   boot_initrd, "--", "curtin", "install", "--config=%s" %
                   self.conf_file, "cp:///"])

        # run vm with installer
        subprocess.check_call(cmd, timeout=self.install_timeout)

        # create xkvm cmd
        cmd = ["tools/xkvm", "--netdev=user", "-d", self.td.target_disk, "-d",
               self.td.output_disk, "--",
               "-drive", "file=%s,if=virtio,media=cdrom" % self.td.seed_disk,
               "-m", "1024"]
        if not self.interactive:
            cmd.extend(["-nographic", "-serial", "file:%s" %
                       os.path.join(self.td.tmpdir, "serial.log")])

        # run vm with installed system, fail if timeout expires
        subprocess.check_call(cmd, timeout=self.boot_timeout)

        # mount output disk
        self.td.mount_output_disk()

    @classmethod
    def tearDownClass(self):
        subprocess.call(["fusermount", "-u", self.td.mnt])
        # remove launch logfile
        if os.path.exists("./serial.log"):
            os.remove("./serial.log")

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
