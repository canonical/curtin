#   Copyright (C) 2014 Canonical Ltd.
#
#   Author: Newell Jensen <newell.jensen@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

from unittest import TestCase
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


class TestReporter(TestCase):

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


class TestMAASReporter(TestCase):
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
