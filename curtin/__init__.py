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

# This constant is made available so a caller can read it
# it must be kept the same as that used in helpers/common:get_carryover_params
KERNEL_CMDLINE_COPY_TO_INSTALL_SEP = "---"

# The 'FEATURES' variable is provided so that users of curtin
# can determine which features are supported.  Each entry should have
# a consistent meaning.
FEATURES = [
    # install supports the 'network' config version 1
    'NETWORK_CONFIG_V1',
    # reporter supports 'webhook' type
    'REPORTING_EVENTS_WEBHOOK',
    # install supports the 'storage' config version 1
    'STORAGE_CONFIG_V1',
    # subcommand 'system-install' is present
    'SUBCOMMAND_SYSTEM_INSTALL',
    # subcommand 'system-upgrade' is present
    'SUBCOMMAND_SYSTEM_UPGRADE',
    # supports new format of apt configuration
    'APT_CONFIG_V1',
]

# vi: ts=4 expandtab syntax=python
