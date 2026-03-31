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

        self.add_patch(
            "curtin.kernel_crash_dumps.Path.exists",
            return_value=preinstalled,
        )
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
        self.add_patch(
            "curtin.distro.get_installed_packages",
            return_value=["kdump-tools" if preinstalled else ""],
        )
        self.add_patch("curtin.distro.install_packages", "m_install")
        ensure_kdump_installed(target)

        if preinstalled:
            self.m_install.assert_not_called()
        else:
            self.m_install.assert_called_with(
                ["kdump-tools"], target=str(target)
            )

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_manual_enable(self, detection_script_available):
        """Test manual enablement logic."""
        target = Path("/target")
        self.add_patch(
            "curtin.kernel_crash_dumps.ensure_kdump_installed",
            "m_ensure",
        )
        self.add_patch(
            "curtin.kernel_crash_dumps.ChrootableTarget",
            "m_chroot",
            new=MagicMock(),
        )
        self.add_patch(
            "curtin.kernel_crash_dumps.detection_script_available",
            return_value=detection_script_available,
        )

        manual_enable(target)

        self.m_ensure.assert_called_once()
        m_subp = self.m_chroot.return_value.__enter__.return_value.subp

        if detection_script_available:
            m_subp.assert_called_with([ENABLEMENT_SCRIPT, "true"])
        else:
            m_subp.assert_not_called()

    def test_manual_enable__exceptions_not_masked(self):
        """Test ProcessExecutionErrors during manual enablement bubble up."""
        target = Path("/target")
        self.add_patch("curtin.kernel_crash_dumps.ensure_kdump_installed")
        self.add_patch(
            "curtin.kernel_crash_dumps.ChrootableTarget",
            "m_chroot",
            new=MagicMock(),
        )
        self.add_patch(
            "curtin.kernel_crash_dumps.detection_script_available",
            return_value=True,
        )
        self.m_chroot.return_value.__enter__.return_value.subp.side_effect = (
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
        self.add_patch(
            "curtin.distro.get_installed_packages",
            return_value=["kdump-tools" if preinstalled else ""],
        )
        self.add_patch(
            "curtin.kernel_crash_dumps.ChrootableTarget",
            "m_chroot",
            new=MagicMock(),
        )

        manual_disable(target)

        m_subp = self.m_chroot.return_value.__enter__.return_value.subp
        if preinstalled:
            m_subp.assert_called_with([ENABLEMENT_SCRIPT, "false"])
        else:
            m_subp.assert_not_called()

    @parameterized.expand(
        (
            (True,),
            (False,),
        )
    )
    def test_automatic_detect(self, wants_enablement):
        """Test automatic enablement logic."""
        target = Path("/target")
        self.add_patch(
            "curtin.kernel_crash_dumps.detection_script_available",
            return_value=wants_enablement,
        )
        self.add_patch(
            "curtin.kernel_crash_dumps.ChrootableTarget",
            "m_chroot",
            new=MagicMock(),
        )

        automatic_detect(target)

        m_subp = self.m_chroot.return_value.__enter__.return_value.subp
        if wants_enablement:
            m_subp.assert_called_with([ENABLEMENT_SCRIPT])
        else:
            m_subp.assert_not_called()
