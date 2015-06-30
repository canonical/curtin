#   Copyright (C) 2015 Canonical Ltd.
#
#   Author: Wesley Wiedenmeier
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

"""Subiquity Reporter."""

from curtin.reporter import (
    BaseReporter,
    INSTALL_LOG,
    LoadReporterException,
    )
import os

class SubiquityReporter(BaseReporter):

    def __init__(self, config):
        """Load config dictionary and initialize object."""
        self.path = config['path']

    def report_progress(self, progress):
        """Report installation progress."""
        status = "WORKING"
        message = "%s" % progress
        self.report(status, message)

    def report_success(self):
        """Report installation success."""
        status = "OK"
        message = "Installation succeeded."
        self.report(status, message)

    def report_failure(self, message):
        """Report installation failure."""
        status = "FAILED"
        self.report(status, message)

    def report(self, files, status, message=None):
        """Write the report."""
        with open(self.path, "a") as fp:
            fp.write("%s : %s" % (status, message))


def load_factory(options):
    try:
        return SubiquityReporter(options)
    except Exception:
        raise LoadReporterException
