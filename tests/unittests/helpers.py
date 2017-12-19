#   Copyright (C) 2016 Canonical Ltd.
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
import mock


class mocked_open(object):
    # older versions of mock can't really mock the builtin 'open' easily.
    def __init__(self):
        self.mocked = None

    def __enter__(self):
        if self.mocked:
            return self.mocked.start()

        py2_p = '__builtin__.open'
        py3_p = 'builtins.open'
        try:
            self.mocked = mock.patch(py2_p, new_callable=mock.mock_open())
            return self.mocked.start()
        except ImportError:
            self.mocked = mock.patch(py3_p, new_callable=mock.mock_open())
            return self.mocked.start()

    def __exit__(self, etype, value, trace):
        if self.mocked:
            self.mocked.stop()
        self.mocked = None
