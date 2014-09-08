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

## TODO - make python3 compliant
# str = None 

from abc import (
    ABCMeta,
    abstractmethod,
    abstractproperty,
    )
from curtin.util import (
    import_module,
    try_import_module,
    )

INSTALL_LOG = "/var/log/curtin_install.log"

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

    def report_success(self, progress):
        """Empty."""

    def report_failure(self, progress):
        """Empty."""


def load_reporter(config):
    """Loads and returns reporter intance stored in config file."""
    
    reporter = config.get('reporter')
    if reporter is None:
        return EmptyReporter()
    name, options = reporter.popitem()
    module = try_import_module('curtin.reporter.%s' % name)
    if module is None:
        return EmptyReporter()
    try:
        return module.load_factory(options)
    except Exception as e:
        return EmptyReporter()
