# This file is part of curtin. See LICENSE file for copyright and license info.

import filecmp
import json
import mock

from curtin import url_helper

from .helpers import CiTestCase


class TestDownload(CiTestCase):
    def setUp(self):
        super(TestDownload, self).setUp()
        self.tmpd = self.tmp_dir()
        self.src_file = self.tmp_path("my-source", self.tmpd)
        with open(self.src_file, "wb") as fp:
            # Write the min amount of bytes
            fp.write(b':-)\n' * int(8200/4))
        self.target_file = self.tmp_path("my-target", self.tmpd)

    def test_download_file_url(self):
        """Download a file to another file."""
        url_helper.download("file://" + self.src_file, self.target_file)
        self.assertTrue(filecmp.cmp(self.src_file, self.target_file),
                        "Downloaded file differed from source file.")

    @mock.patch('curtin.url_helper.UrlReader')
    def test_download_file_url_retry(self, urlreader_mock):
        """Retry downloading a file with server error (http 5xx)."""
        urlreader_mock.side_effect = url_helper.UrlError(None, code=500)

        self.assertRaises(url_helper.UrlError, url_helper.download,
                          "file://" + self.src_file, self.target_file,
                          retries=3, retry_delay=0)
        self.assertEquals(4, urlreader_mock.call_count,
                          "Didn't call UrlReader 4 times (retries=3)")

    @mock.patch('curtin.url_helper.UrlReader')
    def test_download_file_url_no_retry(self, urlreader_mock):
        """No retry by default on downloading a file with server error
           (http 5xx)."""
        urlreader_mock.side_effect = url_helper.UrlError(None, code=500)

        self.assertRaises(url_helper.UrlError, url_helper.download,
                          "file://" + self.src_file, self.target_file,
                          retry_delay=0)
        self.assertEquals(1, urlreader_mock.call_count,
                          "Didn't call UrlReader once (retries=0)")

    @mock.patch('curtin.url_helper.UrlReader')
    def test_download_file_url_no_retry_on_client_error(self, urlreader_mock):
        """No retry by default on downloading a file with 4xx http error."""
        urlreader_mock.side_effect = url_helper.UrlError(None, code=404)

        self.assertRaises(url_helper.UrlError, url_helper.download,
                          "file://" + self.src_file, self.target_file,
                          retries=3, retry_delay=0)
        self.assertEquals(1, urlreader_mock.call_count,
                          "Didn't call UrlReader once (400 class error)")

    def test_download_file_url_retry_then_success(self):
        """Retry downloading a file with server error and then succeed."""
        url_reader = url_helper.UrlReader

        with mock.patch('curtin.url_helper.UrlReader') as urlreader_mock:
            # return first an error, then, real object
            def urlreader_download(url):
                urlreader_mock.side_effect = url_reader
                raise url_helper.UrlError(None, code=500)
            urlreader_mock.side_effect = urlreader_download
            url_helper.download("file://" + self.src_file, self.target_file,
                                retries=3, retry_delay=0)
        self.assertEquals(2, urlreader_mock.call_count,
                          "Didn't call UrlReader twice (first failing,"
                          "then success)")
        self.assertTrue(filecmp.cmp(self.src_file, self.target_file),
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
