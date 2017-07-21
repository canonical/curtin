from unittest import TestCase
from mock import patch
import copy

from curtin.commands import install


class TestMigrateProxy(TestCase):
    def test_legacy_moved_over(self):
        """Legacy setting should get moved over."""
        proxy = "http://my.proxy:3128"
        cfg = {'http_proxy': proxy}
        install.migrate_proxy_settings(cfg)
        self.assertEqual(cfg, {'proxy': {'http_proxy': proxy}})

    def test_no_legacy_new_only(self):
        """Legacy setting should get moved over."""
        proxy = "http://my.proxy:3128"
        cfg = {'proxy': {'http_proxy': proxy, 'https_proxy': proxy,
                         'no_proxy': "10.2.2.2"}}
        expected = copy.deepcopy(cfg)
        install.migrate_proxy_settings(cfg)
        self.assertEqual(expected, cfg)
