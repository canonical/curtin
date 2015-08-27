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

from .registry import DictRegistry
from .handlers import available_handlers

DEFAULT_CONFIG = {
    'logging': {'type': 'log'},
}


def update_configuration(config):
    """Update the instanciated_handler_registry.

    :param config:
        The dictionary containing changes to apply.  If a key is given
        with a False-ish value, the registered handler matching that name
        will be unregistered.
    """
    for handler_name, handler_config in config.items():
        if not handler_config:
            instantiated_handler_registry.unregister_item(
                handler_name, force=True)
            continue
        handler_config = handler_config.copy()
        cls = available_handlers.registered_items[handler_config.pop('type')]
        instantiated_handler_registry.unregister_item(handler_name)
        instance = cls(**handler_config)
        instantiated_handler_registry.register_item(handler_name, instance)


instantiated_handler_registry = DictRegistry()
update_configuration(DEFAULT_CONFIG)
