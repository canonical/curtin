# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path
from unittest.mock import MagicMock, patch

from curtin.commands.curthooks import configure_kernel_crash_dumps
from curtin.kernel_crash_dumps import (ENABLEMENT_SCRIPT, automatic_detect,
                                       detection_script_available,
                                       ensure_kdump_installed, manual_disable,
                                       manual_enable)
from tests.unittests.helpers import CiTestCase


@patch("curtin.kernel_crash_dumps.manual_disable")
@patch("curtin.kernel_crash_dumps.manual_enable")
@patch("curtin.kernel_crash_dumps.automatic_detect")
class TestKernelCrashDumpsCurthook(CiTestCase):

    def test_config__automatic(
        self,
        auto_mock,
        enable_mock,
        disable_mock,
    ):
        """Test expected automatic configs."""
        configs = [
            {"kernel-crash-dumps": {}},
            {"kernel-crash-dumps": {"enabled": None}},
        ]
        for config in configs:
            configure_kernel_crash_dumps(config, "/target")
            auto_mock.assert_called_once_with("/target")
            enable_mock.assert_not_called()
            disable_mock.assert_not_called()

            auto_mock.reset_mock()

    def test_config__manual_enable(
        self,
        auto_mock,
        enable_mock,
        disable_mock,
    ):
        """Test expected automatic configs."""
        config = {"kernel-crash-dumps": {"enabled": True}}
        configure_kernel_crash_dumps(config, "/target")
        auto_mock.assert_not_called()
        enable_mock.assert_called_once_with("/target")
        disable_mock.assert_not_called()

    def test_config__manual_disable(
        self,
        auto_mock,
        enable_mock,
        disable_mock,
    ):
        """Test expected automatic configs."""
        config = {"kernel-crash-dumps": {"enabled": False}}
        configure_kernel_crash_dumps(config, "/target")
        auto_mock.assert_not_called()
        enable_mock.assert_not_called()
        disable_mock.assert_called_once_with("/target")


class TestKernelCrashDumpsUtilities(CiTestCase):

    def test_detection_script_available(self):
        """Test detection_script_available checks for script path."""

        cases = [
            (True, True),
            (False, False),
        ]

        for preinstalled, expected in cases:
            with patch(
                "curtin.kernel_crash_dumps.Path.exists",
                return_value=preinstalled,
            ):
                self.assertEqual(
                    detection_script_available(Path("")),
                    expected,
                )

    def test_ensure_kdump_installed(self):
        """Test detection of preinstall and install of kdump-tools."""

        cases = [True, False]

        target = Path("/target")
        for preinstalled in cases:
            with (
                patch(
                    "curtin.distro.get_installed_packages",
                    return_value=["kdump-tools" if preinstalled else ""],
                )
            ):
                with patch("curtin.distro.install_packages") as do_install:
                    ensure_kdump_installed(target)

            if preinstalled:
                do_install.assert_not_called()
            else:
                do_install.assert_called_with(
                    ["kdump-tools"], target=str(target),
                )

    def test_manual_enable(self):
        """Test manual enablement logic."""
        target = Path("/target")
        with patch(
            "curtin.kernel_crash_dumps.ensure_kdump_installed",
        ) as ensure_mock:
            with patch(
                "curtin.kernel_crash_dumps.ChrootableTarget",
                new=MagicMock(),
            ) as chroot_mock:
                manual_enable(target)
        ensure_mock.assert_called_once_with(Path("/target"))
        subp_mock = chroot_mock.return_value.__enter__.return_value.subp
        subp_mock.assert_called_with(
            [ENABLEMENT_SCRIPT, "true"],
        )

    def test_manual_disable(self):
        """Test manual disable logic."""
        cases = [True, False]
        target = Path("/target")

        for preinstalled in cases:
            with patch(
                "curtin.distro.get_installed_packages",
                return_value=["kdump-tools" if preinstalled else ""],
            ):
                with patch(
                    "curtin.kernel_crash_dumps.ChrootableTarget",
                    new=MagicMock(),
                ) as chroot_mock:
                    manual_disable(target)

            subp_mock = chroot_mock.return_value.__enter__.return_value.subp
            if preinstalled:
                subp_mock.assert_called_with([ENABLEMENT_SCRIPT, "false"])
            else:
                subp_mock.assert_not_called()

    def test_automatic_detect(self):
        """Test automatic enablement logic."""
        cases = [True, False]
        target = Path("/target")

        for wants_enablement in cases:
            with patch(
                "curtin.kernel_crash_dumps.detection_script_available",
                return_value=wants_enablement,
            ):
                with patch(
                    "curtin.kernel_crash_dumps.ChrootableTarget",
                    new=MagicMock(),
                ) as chroot_mock:
                    automatic_detect(target)

            subp_mock = chroot_mock.return_value.__enter__.return_value.subp
            if wants_enablement:
                subp_mock.assert_called_with([ENABLEMENT_SCRIPT])
            else:
                subp_mock.assert_not_called()
