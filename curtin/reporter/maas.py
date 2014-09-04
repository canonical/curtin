# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from curtin import util
from curtin.log import LOG
from curtin.reporter import BaseReporter, report

MAAS_INSTALL_LOG = '/var/log/curtin_install.log'


class MAASReporter(BaseReporter):

    def __init__(self, maas_reporter):
        """Load config dictionary and initialize object."""
        self.url = maas_reporter.get('url')
        self.consumer_key = maas_reporter.get('consumer_key')
        self.consumer_secret = ''
        self.token_key = maas_reporter.get('token_key')
        self.token_secret = maas_reporter.get('token_secret')

    def report_progress(self, progress):
        """Report installation progress."""
        status = "WORKING"
        message = "Installation in progress %s" % progress
        report(
            self.url, self.consumer_key, self.consumer_secret,
            self.token_key, self.token_secret,
            status, message)

    def report_success(self):
        """Report installation success."""
        status = "OK"
        message = "Installation succeeded."
        report(
            self.url, self.consumer_key, self.consumer_secret,
            self.token_key, self.token_secret,
            [MAAS_INSTALL_LOG], status, message)

    def report_failure(self, message):
        """Report installation failure."""
        status = "FAILED"
        report(
            self.url, self.consumer_key, self.consumer_secret,
            self.token_key, self.token_secret,
            [MAAS_INSTALL_LOG], status, message)


def load_factory(options):
    return MAASReporter(options)
