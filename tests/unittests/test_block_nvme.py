# This file is part of curtin. See LICENSE file for copyright and license info.

from typing import List

import curtin.block.nvme as nvme
from .helpers import CiTestCase


class TestGetNvmeControllersFromConfig(CiTestCase):
    def test_no_controller(self):
        self.assertFalse(nvme.get_nvme_controllers_from_config({}))
        self.assertFalse(nvme.get_nvme_controllers_from_config(
            {"storage": False}))
        self.assertFalse(nvme.get_nvme_controllers_from_config(
            {"storage": {}}))
        self.assertFalse(nvme.get_nvme_controllers_from_config({
            "storage": {
                "config": "disabled",
            },
        }))
        self.assertFalse(nvme.get_nvme_controllers_from_config({
            "storage": {
                "config": [
                    {"type": "partition"},
                    {"type": "mount"},
                    {"type": "disk"},
                ],
            },
        }))

    def test_one_controller(self):
        expected = [{"type": "nvme_controller", "transport": "pcie"}]

        self.assertEqual(expected, nvme.get_nvme_controllers_from_config({
            "storage": {
                "config": [
                    {"type": "partition"},
                    {"type": "mount"},
                    {"type": "disk"},
                    {"type": "nvme_controller", "transport": "pcie"},
                ],
            },
        }))

    def test_multiple_controllers(self):
        cfg = {
            "storage": {
                "config": [
                    {"type": "partition"},
                    {
                        "type": "nvme_controller",
                        "id": "nvme-controller-nvme0",
                        "transport": "tcp",
                        "tcp_addr": "1.2.3.4",
                        "tcp_port": "1111",
                    }, {
                        "type": "nvme_controller",
                        "id": "nvme-controller-nvme1",
                        "transport": "tcp",
                        "tcp_addr": "4.5.6.7",
                        "tcp_port": "1212",
                    }, {
                        "type": "nvme_controller",
                        "id": "nvme-controller-nvme2",
                        "transport": "pcie",
                    },
                ],
            },
        }
        ctrlers_id: List[str] = []
        for ctrler in nvme.get_nvme_controllers_from_config(cfg):
            ctrlers_id.append(ctrler["id"])

        self.assertEqual([
            "nvme-controller-nvme0",
            "nvme-controller-nvme1",
            "nvme-controller-nvme2",
            ], ctrlers_id)

        ctrlers_id: List[str] = []
        for ctrler in nvme.get_nvme_controllers_from_config(cfg,
                                                            exclude_pcie=True):
            ctrlers_id.append(ctrler["id"])

        self.assertEqual([
            "nvme-controller-nvme0",
            "nvme-controller-nvme1",
            ], ctrlers_id)
