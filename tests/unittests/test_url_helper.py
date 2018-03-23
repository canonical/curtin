# This file is part of curtin. See LICENSE file for copyright and license info.

import filecmp
import json
import mock

from curtin import url_helper

from .helpers import CiTestCase


class TestDownload(CiTestCase):
    def test_download_file_url(self):
        """Download a file to another file."""
        tmpd = self.tmp_dir()
        src_file = self.tmp_path("my-source", tmpd)
        target_file = self.tmp_path("my-target", tmpd)

        # Make sure we have > 8192 bytes in the file (buflen of UrlReader)
        with open(src_file, "wb") as fp:
            for line in range(0, 1024):
                fp.write(b'Who are the people in your neighborhood.\n')

        url_helper.download("file://" + src_file, target_file)
        self.assertTrue(filecmp.cmp(src_file, target_file),
                        "Downloaded file differed from source file.")


class TestGetMaasVersion(CiTestCase):
    @mock.patch('curtin.url_helper.geturl')
    def test_get_maas_version(self, mock_get_url):
        """verify we fetch maas version from api """
        host = '127.0.0.1'
        endpoint = 'http://%s/MAAS/metadata/node-1230348484' % host
        maas_version = {'version': '2.1.5+bzr5596-0ubuntu1'}
        maas_api_version = '2.0'
        mock_get_url.side_effect = iter([
            maas_api_version.encode('utf-8'),
            ("%s" % json.dumps(maas_version)).encode('utf-8'),
        ])
        result = url_helper.get_maas_version(endpoint)
        self.assertEqual(maas_version, result)
        mock_get_url.assert_has_calls([
            mock.call('http://%s/MAAS/api/version/' % host),
            mock.call('http://%s/MAAS/api/%s/version/' % (host,
                                                          maas_api_version))
        ])

    @mock.patch('curtin.url_helper.LOG')
    @mock.patch('curtin.url_helper.geturl')
    def test_get_maas_version_unsupported(self, mock_get_url, mock_log):
        """return value is None if endpoint returns unsupported MAAS version
        """
        host = '127.0.0.1'
        endpoint = 'http://%s/MAAS/metadata/node-1230348484' % host
        supported = ['1.0', '2.0']
        maas_api_version = 'garbage'
        mock_get_url.side_effect = iter([
            maas_api_version.encode('utf-8'),
        ])
        result = url_helper.get_maas_version(endpoint)
        self.assertIsNone(result)
        self.assertTrue(mock_log.warn.called)
        mock_log.warn.assert_called_with(
            'Endpoint "%s" API version "%s" not in MAAS supported'
            'versions: "%s"', endpoint, maas_api_version, supported)
        mock_get_url.assert_has_calls([
            mock.call('http://%s/MAAS/api/version/' % host),
        ])

    def test_get_maas_version_no_endpoint(self):
        """verify we return None with invalid endpoint """
        host = None
        result = url_helper.get_maas_version(host)
        self.assertEqual(None, result)

    @mock.patch('curtin.url_helper.LOG')
    @mock.patch('curtin.url_helper.geturl')
    def test_get_maas_version_bad_json(self, mock_get_url, mock_log):
        """return value is None if endpoint returns invalid json """
        host = '127.0.0.1'
        endpoint = 'http://%s/MAAS/metadata/node-1230348484' % host
        maas_api_version = '2.0'
        bad_json = '{1237'.encode('utf-8')
        mock_get_url.side_effect = iter([
            maas_api_version.encode('utf-8'),
            bad_json,
        ])
        result = url_helper.get_maas_version(endpoint)
        self.assertIsNone(result)
        self.assertTrue(mock_log.warn.called)
        mock_log.warn.assert_called_with(
            'Failed to load MAAS version result: %s', bad_json)
        mock_get_url.assert_has_calls([
            mock.call('http://%s/MAAS/api/version/' % host),
            mock.call('http://%s/MAAS/api/%s/version/' % (host,
                                                          maas_api_version))
        ])

    @mock.patch('curtin.url_helper.LOG')
    @mock.patch('curtin.url_helper.geturl')
    def test_get_maas_version_network_error_returns_none(self, mock_get_url,
                                                         mock_log):
        """return value is None if endpoint fails to respond"""
        host = '127.0.0.1'
        endpoint = 'http://%s/MAAS/metadata/node-1230348484' % host
        maas_api_version = '2.0'
        exception = url_helper.UrlError('404')
        mock_get_url.side_effect = iter([
            maas_api_version.encode('utf-8'),
            exception,
        ])
        result = url_helper.get_maas_version(endpoint)
        self.assertIsNone(result)
        self.assertTrue(mock_log.warn.called)
        mock_log.warn.assert_called_with(
            'Failed to query MAAS version via URL: %s', exception)
        mock_get_url.assert_has_calls([
            mock.call('http://%s/MAAS/api/version/' % host),
            mock.call('http://%s/MAAS/api/%s/version/' % (host,
                                                          maas_api_version))
        ])
