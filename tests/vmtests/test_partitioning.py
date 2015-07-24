from . import VMBaseClass
from unittest import TestCase

import os
import textwrap


class TestPartitioning(VMBaseClass, TestCase):
    boot_img = "./wily.img"
    conf_file = "examples/tests/basic.yaml"
    interactive = False
    timeout = 300  # If we aren't done in this amount of time give up
    user_data = textwrap.dedent("""\
        #cloud-config
        password: passw0rd
        chpasswd: { expire: False }
        bootcmd:
          - mkdir /media/output
          - mount /dev/vdb /media/output
        runcmd:
          - blkid -o export /dev/vda > /media/output/blkid_output_vda
          - blkid -o export /dev/vda1 > /media/output/blkid_output_vda1
          - blkid -o export /dev/vda2 > /media/output/blkid_output_vda2
        power_state:
          mode: poweroff
        """)

    def test_ptable(self):
        with open(os.path.join(self.mnt, "blkid_output_vda")) as fp:
            blkid_info = self.source(fp.read())
        self.assertEquals(blkid_info["PTTYPE"], "dos")
