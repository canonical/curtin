# This file is part of curtin. See LICENSE file for copyright and license info.

import logging
import time

from functools import wraps

# Logging items for easy access
getLogger = logging.getLogger

CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


def basicConfig(**kwargs):
    # basically like logging.basicConfig but only output for our logger
    if kwargs.get('filename'):
        handler = logging.FileHandler(filename=kwargs['filename'],
                                      mode=kwargs.get('filemode', 'a'))
    elif kwargs.get('stream'):
        handler = logging.StreamHandler(stream=kwargs['stream'])
    else:
        handler = NullHandler()

    if 'verbosity' in kwargs:
        level = ((logging.ERROR, logging.INFO, logging.DEBUG)
                 [min(kwargs['verbosity'], 2)])
    else:
        level = kwargs.get('level', logging.NOTSET)

    handler.setFormatter(logging.Formatter(fmt=kwargs.get('format'),
                                           datefmt=kwargs.get('datefmt')))
    handler.setLevel(level)

    logging.getLogger().setLevel(level)

    logger = _getLogger()
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(level)
    logger.addHandler(handler)


def _getLogger(name='curtin'):
    return logging.getLogger(name)


if not logging.getLogger().handlers:
    logging.getLogger().addHandler(NullHandler())


def _repr_call(name, *args, **kwargs):
    return "%s(%s)" % (
        name,
        ', '.join([str(repr(a)) for a in args] +
                  ["%s=%s" % (k, repr(v)) for k, v in kwargs.items()]))


def log_call(func, *args, **kwargs):
    return log_time(
        "TIMED %s: " % _repr_call(func.__name__, *args, **kwargs),
        func, *args, **kwargs)


def log_time(msg, func, *args, **kwargs):
    start = time.time()
    try:
        return func(*args, **kwargs)
    finally:
        LOG.debug(msg + "%.3f", (time.time() - start))


def logged_call():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return log_call(func, *args, **kwargs)
        return wrapper
    return decorator


def logged_time(msg):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return log_time("TIMED %s: " % msg, func, *args, **kwargs)
        return wrapper
    return decorator


LOG = _getLogger()

# vi: ts=4 expandtab syntax=python
