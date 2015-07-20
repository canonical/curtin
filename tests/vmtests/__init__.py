from curtin import util

import os
import tempfile


class VMBaseClass():
    @classmethod
    def setUpClass(self):
        # make sure boot img is present
        if not os.path.exists(self.boot_img):
            raise ValueError("boot image '%s' does not exist" % self.boot_img)

        # create tmpdir
        self.tmpdir = tempfile.mkdtemp()

        # create disks
        for diskno in range(self.number_of_disks):
            disk_file_name = os.path.join(self.tmpdir, "disk%s.img" % diskno)
            util.subp(["qemu-img", "create", "-f", "raw", disk_file_name,
                      "4G"])
            self.disks.append(disk_file_name)

        # create launch cmd
        cmd = ["tools/launch", "--netdev=user", "--power=off"]
        for disk in self.disks:
            cmd.extend(["-d", disk])
        cmd.extend([self.boot_img, "--", "curtin", "install"])
        if self.conf_file:
            if not os.path.exists(self.conf_file):
                raise ValueError("specified conf file '%s' does not exist" %
                                 self.conffile)
            cmd.extend(["--config=%s" % self.conf_file])
        cmd.append("cp:///")

        # run vm
        util.subp(cmd)

    @classmethod
    def tearDownClass(self):
        # remove disks
        for disk in self.disks:
            os.remove(disk)

        # remove tempdir
        os.rmdir(self.tmpdir)

        # remove logfile
        os.remove("./serial.log")

# vi: ts=4 expandtab syntax=python
