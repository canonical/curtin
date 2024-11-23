# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path
from unittest.mock import MagicMock, patch

from parameterized import parameterized

from curtin.commands.curthooks import configure_kernel_crash_dumps
from curtin.kernel_crash_dumps import (ENABLEMENT_SCRIPT, automatic_detect,
                                       detection_script_available,
                                       ensure_kdump_installed, manual_disable,
                                       manual_enable)
from curtin.util import ProcessExecutionError
from tests.unittests.helpers import CiTestCase


@patch("curtin.kernel_crash_dumps.manual_disable")
@patch("curtin.kernel_crash_dumps.manual_enable")
@patch("curtin.kernel_crash_dumps.automatic_detect")
class TestKernelCrashDumpsCurthook(CiTestCase):

    @parameterized.expand(
        (
            ({"kernel-crash-dumps": {}},),
            ({"kernel-crash-dumps": {"enabled": None}},),
        )
    )
    def test_config__automatic(
        self,
        auto_mock,
        enable_mock,
        disable_mock,
        config,
    ):
        """Test expected automatic configs."""

        configure_kernel_crash_dumps(config, "/target")
        auto_mock.assert_called_once()
        enable_mock.assert_not_called()
        disable_mock.assert_not_called()

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
        enable_mock.assert_called_once()
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
        disable_mock.assert_called_once()


class TestKernelCrashDumpsUtilities(CiTestCase):

    @parameterized.expand(
        (
            (True, True),
            (False, False),
        )
    )
    def test_detection_script_available(self, preinstalled, expected):
        """Test detection_script_available checks for script path."""

        with patch(
            "curtin.kernel_crash_dumps.Path.exists",
            return_value=preinstalled,
        ):
            self.assertEqual(detection_script_available(Path("")), expected)

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_ensure_kdump_installed(self, preinstalled):
        """Test detection of preinstall and install of kdump-tools."""

        target = Path("/target")
        with (
            patch(
                "curtin.distro.get_installed_packages",
                return_value=["kdump-tools" if preinstalled else ""],
            ),
            patch("curtin.distro.install_packages") as do_install,
        ):
            ensure_kdump_installed(target)

        if preinstalled:
            do_install.assert_not_called()
        else:
            do_install.assert_called_with(["kdump-tools"], target=str(target))

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_manual_enable(self, detection_script_available):
        """Test manual enablement logic."""
        target = Path("/target")
        with (
            patch(
                "curtin.kernel_crash_dumps.ensure_kdump_installed",
            ) as ensure_mock,
            patch(
                "curtin.kernel_crash_dumps.ChrootableTarget",
                new=MagicMock(),
            ) as chroot_mock,
            patch(
                "curtin.kernel_crash_dumps.detection_script_available",
                return_value=detection_script_available,
            ),
        ):
            manual_enable(target)

        ensure_mock.assert_called_once()
        subp_mock = chroot_mock.return_value.__enter__.return_value.subp

        if detection_script_available:
            subp_mock.assert_called_with(
                [ENABLEMENT_SCRIPT, "true"],
            )

        else:
            subp_mock.assert_not_called()

    def test_manual_enable__exceptions_not_masked(self):
        """Test ProcessExecutionErrors during manual enablement bubble up."""
        target = Path("/target")
        with (
            patch(
                "curtin.kernel_crash_dumps.ensure_kdump_installed",
            ),
            patch(
                "curtin.kernel_crash_dumps.ChrootableTarget",
                new=MagicMock(),
            ) as ch_mock,
            patch(
                "curtin.kernel_crash_dumps.detection_script_available",
                return_value=True,
            ),
        ):

            ch_mock.return_value.__enter__.return_value.subp.side_effect = (
                ProcessExecutionError()
            )
            with self.assertRaises(ProcessExecutionError):
                manual_enable(target)

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_manual_disable(self, preinstalled):
        """Test manual disable logic."""
        target = Path("/target")
        with (
            patch(
                "curtin.distro.get_installed_packages",
                return_value=["kdump-tools" if preinstalled else ""],
            ),
            patch(
                "curtin.kernel_crash_dumps.ChrootableTarget",
                new=MagicMock(),
            ) as chroot_mock,
        ):
            manual_disable(target)

        subp_mock = chroot_mock.return_value.__enter__.return_value.subp
        if preinstalled:
            subp_mock.assert_called_with([ENABLEMENT_SCRIPT, "false"])
        else:
            subp_mock.assert_not_called()

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_automatic_detect(self, wants_enablement):
        """Test automatic enablement logic."""
        target = Path("/target")
        with (
            patch(
                "curtin.kernel_crash_dumps.detection_script_available",
                return_value=wants_enablement,
            ),
            patch(
                "curtin.kernel_crash_dumps.ChrootableTarget",
                new=MagicMock(),
            ) as chroot_mock,
        ):
            automatic_detect(target)

        subp_mock = chroot_mock.return_value.__enter__.return_value.subp
        if wants_enablement:
            subp_mock.assert_called_with([ENABLEMENT_SCRIPT])
        else:
            subp_mock.assert_not_called()
