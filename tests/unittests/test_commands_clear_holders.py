# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.commands import clear_holders
from .helpers import CiTestCase

import argparse


class TestClearHolders(CiTestCase):

    def setUp(self):
        super(TestClearHolders, self).setUp()
        self.add_patch('curtin.block.clear_holders', 'm_clear_holders')
        self.add_patch('curtin.block', 'm_block')

    def test_argument_parsing_devices_is_dict(self):
        argv = ['/dev/disk/vda1']
        parser = argparse.ArgumentParser()
        clear_holders.POPULATE_SUBCMD(parser)
        args = parser.parse_args(argv)
        self.assertEqual(list, type(args.devices))


# vi: ts=4 expandtab syntax=python
