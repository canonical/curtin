# vi: ts=4 expandtab

import abc

from .registry import DictRegistry
from .. import url_helper
from .. import log as logging


LOG = logging.getLogger(__name__)


class ReportingHandler(object):
    """Base class for report handlers.

    Implement :meth:`~publish_event` for controlling what
    the handler does with an event.
    """

    @abc.abstractmethod
    def publish_event(self, event):
        """Publish an event to the ``INFO`` log level."""


class LogHandler(ReportingHandler):
    """Publishes events to the curtin log at the ``DEBUG`` log level."""

    def __init__(self, level="DEBUG"):
        super(LogHandler, self).__init__()
        if isinstance(level, int):
            pass
        else:
            input_level = level
            try:
                level = getattr(logging, level.upper())
            except Exception:
                LOG.warn("invalid level '%s', using WARN", input_level)
                level = logging.WARN
        self.level = level

    def publish_event(self, event):
        """Publish an event to the ``DEBUG`` log level."""
        logger = logging.getLogger(
            '.'.join(['curtin', 'reporting', event.event_type, event.name]))
        logger.log(self.level, event.as_string())


class PrintHandler(ReportingHandler):
    """Print the event as a string."""

    def publish_event(self, event):
        print(event.as_string())


class WebHookHandler(ReportingHandler):
    def __init__(self, endpoint, consumer_key=None, token_key=None,
                 token_secret=None, consumer_secret=None, timeout=None,
                 retries=None, level="DEBUG"):
        super(WebHookHandler, self).__init__()

        self.oauth_helper = url_helper.OauthUrlHelper(
            consumer_key=consumer_key, token_key=token_key,
            token_secret=token_secret, consumer_secret=consumer_secret)
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries
        try:
            self.level = getattr(logging, level.upper())
        except Exception:
            LOG.warn("invalid level '%s', using WARN", level)
            self.level = logging.WARN
        self.headers = {'Content-Type': 'application/json'}

    def publish_event(self, event):
        try:
            return self.oauth_helper.geturl(
                url=self.endpoint, data=event.as_dict(),
                headers=self.headers, retries=self.retries)
        except Exception as e:
            LOG.warn("failed posting event: %s [%s]" % (event.as_string(), e))


class JournaldHandler(ReportingHandler):

    def __init__(self, level="DEBUG", identifier="curtin_event"):
        super(JournaldHandler, self).__init__()
        if isinstance(level, int):
            pass
        else:
            input_level = level
            try:
                level = getattr(logging, level.upper())
            except Exception:
                LOG.warn("invalid level '%s', using WARN", input_level)
                level = logging.WARN
        self.level = level
        self.identifier = identifier

    def publish_event(self, event):
        # Ubuntu older than precise will not have python-systemd installed.
        try:
            from systemd import journal
        except ImportError:
            raise
        level = str(getattr(journal, "LOG_" + event.level, journal.LOG_DEBUG))
        extra = {}
        if hasattr(event, 'result'):
            extra['CURTIN_RESULT'] = event.result
        journal.send(
            event.as_string(),
            PRIORITY=level,
            SYSLOG_IDENTIFIER=self.identifier,
            CURTIN_EVENT_TYPE=event.event_type,
            CURTIN_MESSAGE=event.description,
            CURTIN_NAME=event.name,
            **extra
            )


available_handlers = DictRegistry()
available_handlers.register_item('log', LogHandler)
available_handlers.register_item('print', PrintHandler)
available_handlers.register_item('webhook', WebHookHandler)
# only add journald handler on systemd systems
try:
    available_handlers.register_item('journald', JournaldHandler)
except ImportError:
    print('journald report handler not supported; no systemd module')
