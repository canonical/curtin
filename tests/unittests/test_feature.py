# This file is part of curtin. See LICENSE file for copyright and license info.

from .helpers import CiTestCase

import curtin


class TestExportsFeatures(CiTestCase):
    def test_has_storage_v1(self):
        self.assertIn('STORAGE_CONFIG_V1', curtin.FEATURES)

    def test_has_storage_v1_dd(self):
        self.assertIn('STORAGE_CONFIG_V1_DD', curtin.FEATURES)

    def test_has_network_v1(self):
        self.assertIn('NETWORK_CONFIG_V1', curtin.FEATURES)

    def test_has_reporting_events_webhook(self):
        self.assertIn('REPORTING_EVENTS_WEBHOOK', curtin.FEATURES)

    def test_has_centos_apply_network_config(self):
        self.assertIn('CENTOS_APPLY_NETWORK_CONFIG', curtin.FEATURES)

    def test_has_centos_curthook_support(self):
        self.assertIn('CENTOS_CURTHOOK_SUPPORT', curtin.FEATURES)

    def test_has_btrfs_swapfile_support(self):
        self.assertIn('BTRFS_SWAPFILE', curtin.FEATURES)

# vi: ts=4 expandtab syntax=python
