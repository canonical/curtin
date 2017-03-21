from unittest import TestCase

import curtin


class TestExportsFeatures(TestCase):
    def test_has_storage_v1(self):
        self.assertIn('STORAGE_CONFIG_V1', curtin.FEATURES)

    def test_has_storage_v1_dd(self):
        self.assertIn('STORAGE_CONFIG_V1_DD', curtin.FEATURES)

    def test_has_network_v1(self):
        self.assertIn('NETWORK_CONFIG_V1', curtin.FEATURES)

    def test_has_reporting_events_webhook(self):
        self.assertIn('REPORTING_EVENTS_WEBHOOK', curtin.FEATURES)
