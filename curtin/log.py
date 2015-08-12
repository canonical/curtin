#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
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

import logging

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

LOG = _getLogger()

# vi: ts=4 expandtab syntax=python
