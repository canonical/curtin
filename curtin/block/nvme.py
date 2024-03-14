# This file is part of curtin. See LICENSE file for copyright and license info.

from typing import Any, Dict, Iterator, List

from curtin.log import LOG


def _iter_nvme_controllers(cfg) -> Iterator[Dict[str, Any]]:
    if not cfg:
        cfg = {}

    if 'storage' in cfg:
        if not isinstance(cfg['storage'], dict):
            sconfig = {}
        else:
            sconfig = cfg['storage'].get('config', [])
    else:
        sconfig = cfg.get('config', [])

    if not sconfig or not isinstance(sconfig, list):
        LOG.warning('Configuration dictionary did not contain'
                    ' a storage configuration.')
        return

    for item in sconfig:
        if item['type'] == 'nvme_controller':
            yield item


def get_nvme_controllers_from_config(
        cfg, *, exclude_pcie=False) -> List[Dict[str, Any]]:
    '''Parse a curtin storage config and return a list of
    NVMe controllers. If exclude_pcie is True, only return controllers that do
    not use PCIe transport.'''
    controllers = _iter_nvme_controllers(cfg)

    if not exclude_pcie:
        return list(controllers)

    return [ctrler for ctrler in controllers if ctrler['transport'] != 'pcie']
