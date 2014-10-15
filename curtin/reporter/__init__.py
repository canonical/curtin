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

"""Reporter Abstract Base Class."""

# TODO - make python3 compliant
# str = None

import os

from abc import (
    ABCMeta,
    abstractmethod,
    )
from curtin.log import LOG
from curtin.util import (
    try_import_module,
    ensure_dir,
    )

INSTALL_LOG = "/var/log/curtin/install.log"


class BaseReporter:
    """Skeleton for a report."""

    __metaclass__ = ABCMeta

    @abstractmethod
    def report_progress(self, progress):
        """Report installation progress."""

    @abstractmethod
    def report_success(self):
        """Report installation success."""

    @abstractmethod
    def report_failure(self, failure):
        """Report installation failure."""


class EmptyReporter(BaseReporter):

    def report_progress(self, progress):
        """Empty."""

    def report_success(self):
        """Empty."""

    def report_failure(self, failure):
        """Empty."""


class LoadReporterException(Exception):
    """Raise exception if desired reporter not loaded."""
    pass


def load_reporter(config):
    """Loads and returns reporter instance stored in config file."""

    reporter = config.get('reporter')
    if reporter is None:
        LOG.info("'reporter' not found in config file.")
        return EmptyReporter()
    name, options = reporter.popitem()
    module = try_import_module('curtin.reporter.%s' % name)
    if module is None:
        LOG.error(
            "Module for %s reporter could not load." % name)
        return EmptyReporter()
    try:
        return module.load_factory(options)
    except LoadReporterException:
        LOG.error(
            "Failed loading %s reporter with %s" % (name, options))
        return EmptyReporter()


def clear_install_log():
    """Clear the installation log, so no previous installation is present."""
    # Create MAAS install log directory
    ensure_dir(os.path.dirname(INSTALL_LOG))
    try:
        open(INSTALL_LOG, 'w').close()
    except:
        pass


def writeline_install_log(output):
    """Write output into the install log."""
    if not output.endswith('\n'):
        output += '\n'
    try:
        with open(INSTALL_LOG, 'a') as fp:
            fp.write(output)
    except IOError:
        pass
