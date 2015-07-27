from . import VMBaseClass, source_data
from unittest import TestCase

import os
import textwrap


class TestPartitioning(VMBaseClass, TestCase):
    repo = "maas-daily"
    release = "wily"
    arch = "amd64"
    conf_file = "examples/tests/basic.yaml"
    install_timeout = 600
    boot_timeout = 120
    interactive = False
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
        with open(os.path.join(self.td.mnt, "blkid_output_vda")) as fp:
            blkid_info = source_data(fp.read())
        self.assertEquals(blkid_info["PTTYPE"], "dos")
