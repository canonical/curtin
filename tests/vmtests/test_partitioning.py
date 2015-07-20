from . import VMBaseClass
from curtin import util
from unittest import TestCase

import parted


class TestPartitioning(VMBaseClass, TestCase):
    boot_img = "./wily.img"
    conf_file = "examples/custom-partitioning-test.yaml"
    number_of_disks = 1
    disks = []

    def test_part_table(self):
        (out, _err) = util.subp(["blkid", "-o", "export", self.disks[0]],
                                capture=True)
        current_ptable = list(filter(lambda x: "PTTYPE" in x,
                                     out.splitlines()))[0].split("=")[-1]
        self.assertEqual(current_ptable, "dos")
