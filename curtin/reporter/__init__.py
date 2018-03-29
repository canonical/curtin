# This file is part of curtin. See LICENSE file for copyright and license info.

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
# vi: ts=4 expandtab syntax=python
