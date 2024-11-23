# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path

from curtin import distro
from curtin.log import LOG
from curtin.util import ChrootableTarget

ENABLEMENT_SCRIPT = "/usr/share/kdump-tools/kdump_set_default"


def ensure_kdump_installed(target: Path) -> None:
    """Ensure kdump-tools installed on target system and install it if not.

    kdump-tools is theoretically part of the base-install in >=24.10
    but we may need to dynamically install it if manual enablement is
    requested.
    """
    if "kdump-tools" not in distro.get_installed_packages(str(target)):
        distro.install_packages(["kdump-tools"], target=str(target))


def detection_script_available(target: Path) -> bool:
    """Detect existence of the enablement script.

    Enablement script will only be found on targets where kdump-tools is
    pre-installed and it's a version which contains the script.
    """
    path = target / ENABLEMENT_SCRIPT[1:]
    if path.exists():
        LOG.debug("kernel-crash-dumps enablement script found.")
        return True
    else:
        LOG.debug("kernel-crash-dumps enablement script missing.")
        return False


def manual_enable(target: Path) -> None:
    """Manually enable kernel crash dumps with kdump-tools on target."""
    ensure_kdump_installed(target)
    if detection_script_available(target):
        with ChrootableTarget(str(target)) as in_target:
            in_target.subp([ENABLEMENT_SCRIPT, "true"])
    else:
        # Enablement script not found. Likely scenario is that enablement was
        # requested on a pre-24.10 series but the script hasn't been SRU'd yet.
        # This is OK since installing on these series will mean kdump-tools
        # is enabled by default.
        # Let's not block the install on this but at least warn the user.
        LOG.warning(
            (
                "kernel-crash-dumps enablement requested but enablement "
                "script not found. Not running."
            ),
        )


def manual_disable(target: Path) -> None:
    """Manually disable kernel crash dumps with kdump-tools on target."""
    if "kdump-tools" in distro.get_installed_packages(str(target)):
        with ChrootableTarget(str(target)) as in_target:
            in_target.subp([ENABLEMENT_SCRIPT, "false"])


def automatic_detect(target: Path) -> None:
    """Perform conditional enablement with kdump-tools on target.

    Uses the enablement script provided by kdump-tools to detect
    system criteria and either enable or disable kernel crash dumps
    on the target system. The script is not run if it's not found.
    """
    if detection_script_available(target):
        LOG.debug("Running conditional enablement script...")
        with ChrootableTarget(str(target)) as in_target:
            in_target.subp([ENABLEMENT_SCRIPT])
