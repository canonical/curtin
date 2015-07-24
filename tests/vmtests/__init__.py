import os
import tempfile
import shutil
import subprocess


class VMBaseClass():
    @classmethod
    def setUpClass(self):
        # make sure boot img is present
        if not os.path.exists(self.boot_img):
            raise ValueError("boot image '%s' does not exist" % self.boot_img)

        # create tmpdir
        self.tmpdir = tempfile.mkdtemp()

        # create target disk
        target_disk = os.path.join(self.tmpdir, "install_disk.img")
        subprocess.call(["qemu-img", "create", "-f", "qcow2", target_disk,
                        "4G"])

        # create launch cmd
        cmd = ["tools/launch"]
        if not self.interactive:
            cmd.append("--silent")
        cmd.extend(["--power=off", "--netdev=user", "-d", target_disk,
                   self.boot_img, "--", "curtin", "install", "--config=%s" %
                   self.conf_file, "cp:///"])

        # run vm with installer
        subprocess.call(cmd)

        # write cloud-init for installed system
        meta_data_file = os.path.join(self.tmpdir, "meta-data")
        with open(meta_data_file, "w") as fp:
            fp.write("instance-id: inst-123\n")
        user_data_file = os.path.join(self.tmpdir, "user-data")
        with open(user_data_file, "w") as fp:
            fp.write(self.user_data)

        # create seed.img for installed system's cloud init
        seed_path = os.path.join(self.tmpdir, "seed.img")
        subprocess.call(["cloud-localds", seed_path, user_data_file,
                        meta_data_file])

        # create output disk
        output_disk = os.path.join(self.tmpdir, "output_disk.img")
        subprocess.call(["qemu-img", "create", "-f", "raw", output_disk,
                        "10M"])
        subprocess.call(["mkfs.ext2", output_disk])

        # create xkvm cmd
        cmd = ["tools/xkvm", "--netdev=user", "-d", target_disk, "-d",
               output_disk, "--",
               "-drive", "file=%s,if=virtio,media=cdrom" % seed_path]
        if not self.interactive:
            cmd.extend(["-nographic", "-serial", "file:%s" %
                       os.path.join(self.tmpdir, "serial.log")])

        # run vm with installed system, fail if timeout expires
        try:
            subprocess.call(cmd, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.timed_out = True
        else:
            self.timed_out = False

        # mount output disk
        self.mnt = os.path.join(self.tmpdir, "mnt")
        os.mkdir(self.mnt)
        subprocess.call(["fuseext2", "-o", "rw+", output_disk, self.mnt])

    @classmethod
    def tearDownClass(self):
        # unmount output disk
        subprocess.call(["fusermount", "-u", self.mnt])

        # remove tempdir
        shutil.rmtree(self.tmpdir)

        # remove logfile
        if os.path.exists("./serial.log"):
            os.remove("./serial.log")

    def source(self, data):
        ret = {}
        for line in data.splitlines():
            if line == "":
                continue
            val = line.split('=')
            ret[val[0]] = val[1]
        return ret

    def test_did_not_time_out(self):
        self.assertFalse(self.timed_out)
