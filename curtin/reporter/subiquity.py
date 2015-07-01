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
import json


class SubiquityReporter(BaseReporter):

    def __init__(self, config):
        """Load config dictionary and initialize object."""
        self.path = config['path']
        self.progress = config['progress']

    def report_progress(self, progress):
        """Report installation progress."""
        status = "WORKING"
        self.report(status, progress)

    def report_success(self):
        """Report installation success."""
        status = "OK"
        progress = "Installation succeeded."
        self.report(status, progress)

    def report_failure(self, progress):
        """Report installation failure."""
        status = "FAILED"
        self.report(status, progress)

    def report(self, status, progress):
        """Write the report."""
        report = {"STATUS": status,
                  "PROGRESS": progress}
        with open(self.path, "a") as fp:
            fp.write("%s\n" % json.dumps(report))


def load_factory(options):
    try:
        return SubiquityReporter(options)
    except Exception:
        raise LoadReporterException
