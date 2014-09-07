# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

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
