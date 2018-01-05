# This file is part of curtin. See LICENSE file for copyright and license info.

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

from mock import patch

from curtin.reporter.legacy import (
    EmptyReporter,
    load_reporter,
    LoadReporterException,
    )
# #XXX: see `XXX` below for details
from curtin.reporter.legacy.maas import (
    load_factory,
    MAASReporter
    )

from curtin import reporter
from curtin.reporter import handlers
from curtin import url_helper
from curtin.reporter import events
from .helpers import CiTestCase

import base64
import os


class TestLegacyReporter(CiTestCase):

    @patch('curtin.reporter.legacy.LOG')
    def test_load_reporter_logs_empty_cfg(self, mock_LOG):
        cfg = {}
        reporter = load_reporter(cfg)
        self.assertIsInstance(reporter, EmptyReporter)
        self.assertTrue(mock_LOG.info.called)

    @patch('curtin.reporter.legacy.LOG')
    def test_load_reporter_logs_cfg_with_no_module(
            self, mock_LOG):
        cfg = {'reporter': {'empty': {}}}
        reporter = load_reporter(cfg)
        self.assertIsInstance(reporter, EmptyReporter)
        self.assertTrue(mock_LOG.error.called)

    @patch('curtin.reporter.legacy.LOG')
    def test_load_reporter_logs_cfg_wrong_options(self, mock_LOG):
        # we are passing wrong config options for maas reporter
        # to test load_reporter in event reporter options are wrong
        cfg = {'reporter': {'maas': {'wrong': 'wrong'}}}
        reporter = load_reporter(cfg)
        self.assertIsInstance(reporter, EmptyReporter)
        self.assertTrue(mock_LOG.error.called)


class TestMAASReporter(CiTestCase):
    def test_load_factory_raises_exception_wrong_options(self):
        options = {'wrong': 'wrong'}
        self.assertRaises(
            LoadReporterException, load_factory, options)

    def test_load_factory_returns_maas_reporter_good_options(self):
        options = {
            'url': 'url', 'consumer_key': 'consumer_key',
            'token_key': 'token_key', 'token_secret': 'token_secret'}
        reporter = load_factory(options)
        self.assertIsInstance(reporter, MAASReporter)


class TestReporter(CiTestCase):
    config = {'element1': {'type': 'webhook', 'level': 'INFO',
                           'consumer_key': "ck_foo",
                           'consumer_secret': 'cs_foo',
                           'token_key': 'tk_foo',
                           'token_secret': 'ts_foo',
                           'endpoint': '127.0.0.1:8000'}}
    ev_name = 'event_name_1'
    ev_desc = 'test event description'

    def _get_reported_event(self, mock_report_event):
        self.assertTrue(mock_report_event.called)
        calls = mock_report_event.call_args_list
        self.assertTrue(len(calls) > 0)
        call = calls[-1][0]
        self.assertIsInstance(call[0], events.ReportingEvent)
        return call[0]

    def test_default_configuration(self):
        handler_registry = \
            reporter.instantiated_handler_registry.registered_items
        self.assertTrue('logging' in handler_registry)
        self.assertIsInstance(handler_registry['logging'],
                              handlers.LogHandler)

    @patch('curtin.reporter.instantiated_handler_registry')
    @patch('curtin.reporter.DictRegistry')
    def test_update_config(self, mock_registry, mock_handler_registry):
        reporter.update_configuration(self.config)
        mock_handler_registry.unregister_item.assert_called_with('element1')
        calls = mock_handler_registry.register_item.call_args_list
        self.assertEqual(len(calls), 1)
        webhook = calls[0][0][1]
        self.assertEqual(webhook.endpoint, self.config['element1']['endpoint'])
        self.assertEqual(webhook.level, 20)
        self.assertIsInstance(webhook.oauth_helper,
                              url_helper.OauthUrlHelper)

    @patch('curtin.url_helper.OauthUrlHelper')
    def test_webhook_handler(self, mock_url_helper):
        event = events.ReportingEvent(events.START_EVENT_TYPE, 'test_event',
                                      'test event', level='INFO')
        webhook_handler = handlers.WebHookHandler('127.0.0.1:8000',
                                                  level='INFO')
        webhook_handler.publish_event(event)
        webhook_handler.oauth_helper.geturl.assert_called_with(
            url='127.0.0.1:8000', data=event.as_dict(),
            headers=webhook_handler.headers, retries=None)
        event.level = 'DEBUG'
        webhook_handler.oauth_helper.geturl.called = False
        webhook_handler.publish_event(event)
        webhook_handler = handlers.WebHookHandler('127.0.0.1:8000',
                                                  level="INVALID")
        self.assertEquals(webhook_handler.level, 30)

    @patch('curtin.reporter.events.report_event')
    def test_report_start_event(self, mock_report_event):
        events.report_start_event(self.ev_name, self.ev_desc)
        event_dict = self._get_reported_event(mock_report_event).as_dict()
        self.assertEqual(event_dict.get('name'), self.ev_name)
        self.assertEqual(event_dict.get('level'), 'INFO')
        self.assertEqual(event_dict.get('description'), self.ev_desc)
        self.assertEqual(event_dict.get('event_type'), events.START_EVENT_TYPE)

    @patch('curtin.reporter.events.report_event')
    def test_report_finish_event(self, mock_report_event):
        events.report_finish_event(self.ev_name, self.ev_desc)
        event = self._get_reported_event(mock_report_event)
        self.assertIsInstance(event, events.FinishReportingEvent)
        event_dict = event.as_dict()
        self.assertEqual(event_dict.get('description'), self.ev_desc)

    @patch('curtin.reporter.events.report_event')
    def test_report_finished_event_levelset(self, mock_report_event):
        events.report_finish_event(self.ev_name, self.ev_desc,
                                   result=events.status.FAIL)
        event_dict = self._get_reported_event(mock_report_event).as_dict()
        self.assertEqual(event_dict.get('level'), 'ERROR')
        self.assertEqual(event_dict.get('description'), self.ev_desc)

        events.report_finish_event(self.ev_name, self.ev_desc,
                                   result=events.status.WARN)
        event_dict = self._get_reported_event(mock_report_event).as_dict()
        self.assertEqual(event_dict.get('level'), 'WARN')
        self.assertEqual(event_dict.get('description'), self.ev_desc)

    @patch('curtin.reporter.events.report_event')
    def test_report_finished_post_files(self, mock_report_event):
        test_data = b'abcdefg'
        tmpfname = self.tmp_path('testfile')
        with open(tmpfname, 'wb') as fp:
            fp.write(test_data)
        events.report_finish_event(self.ev_name, self.ev_desc,
                                   post_files=[tmpfname])
        event = self._get_reported_event(mock_report_event)
        files = event.as_dict().get('files')
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0].get('path'), tmpfname)
        self.assertEqual(files[0].get('encoding'), 'base64')
        self.assertEqual(files[0].get('content'),
                         base64.b64encode(test_data).decode())

    @patch('curtin.reporter.events.report_event')
    def test_report_finished_post_files_absent_file(self, mock_report_event):
        """Absent files provided with post_files result in empty content."""
        tmpfname = self.tmp_path('testfile')
        self.assertFalse(os.path.exists(tmpfname))
        events.report_finish_event(self.ev_name, self.ev_desc,
                                   post_files=[tmpfname])
        event = self._get_reported_event(mock_report_event)
        files = event.as_dict().get('files')
        self.assertTrue(len(files) == 1)
        self.assertEqual(files[0].get('path'), tmpfname)
        self.assertEqual(files[0].get('encoding'), 'base64')
        self.assertIsNone(files[0]['content'],
                          'Unexpected content found for absent post_file.')

    @patch('curtin.url_helper.OauthUrlHelper')
    def test_webhook_handler_post_files(self, mock_url_helper):
        test_data = b'abcdefg'
        tmpfname = self.tmp_path('testfile')
        with open(tmpfname, 'wb') as fp:
            fp.write(test_data)
        event = events.FinishReportingEvent('test_event_name',
                                            'test event description',
                                            post_files=[tmpfname],
                                            level='INFO')
        webhook_handler = handlers.WebHookHandler('127.0.0.1:8000',
                                                  level='INFO')
        webhook_handler.publish_event(event)
        webhook_handler.oauth_helper.geturl.assert_called_with(
            url='127.0.0.1:8000', data=event.as_dict(),
            headers=webhook_handler.headers, retries=None)

# vi: ts=4 expandtab syntax=python
