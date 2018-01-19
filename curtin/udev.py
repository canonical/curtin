# This file is part of curtin. See LICENSE file for copyright and license info.

import os
from curtin import util


def compose_udev_equality(key, value):
    """Return a udev comparison clause, like `ACTION=="add"`."""
    assert key == key.upper()
    return '%s=="%s"' % (key, value)


def compose_udev_attr_equality(attribute, value):
    """Return a udev attribute comparison clause, like `ATTR{type}=="1"`."""
    assert attribute == attribute.lower()
    return 'ATTR{%s}=="%s"' % (attribute, value)


def compose_udev_setting(key, value):
    """Return a udev assignment clause, like `NAME="eth0"`."""
    assert key == key.upper()
    return '%s="%s"' % (key, value)


def generate_udev_rule(interface, mac):
    """Return a udev rule to set the name of network interface with `mac`.

    The rule ends up as a single line looking something like:

    SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*",
    ATTR{address}="ff:ee:dd:cc:bb:aa", NAME="eth0"
    """
    rule = ', '.join([
        compose_udev_equality('SUBSYSTEM', 'net'),
        compose_udev_equality('ACTION', 'add'),
        compose_udev_equality('DRIVERS', '?*'),
        compose_udev_attr_equality('address', mac),
        compose_udev_setting('NAME', interface),
        ])
    return '%s\n' % rule


def udevadm_settle(exists=None, timeout=None):
    settle_cmd = ["udevadm", "settle"]
    if exists:
        # skip the settle if the requested path already exists
        if os.path.exists(exists):
            return
        settle_cmd.extend(['--exit-if-exists=%s' % exists])
    if timeout:
        settle_cmd.extend(['--timeout=%s' % timeout])

    util.subp(settle_cmd)


def udevadm_trigger(devices):
    if devices is None:
        devices = []
    util.subp(['udevadm', 'trigger'] + list(devices))
    udevadm_settle()

# vi: ts=4 expandtab syntax=python
