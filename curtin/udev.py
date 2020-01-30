# This file is part of curtin. See LICENSE file for copyright and license info.

import shlex
import os

from curtin import util
from curtin.log import logged_call


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


@logged_call()
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


def udevadm_info(path=None):
    """ Return a dictionary populated by properties of the device specified
        in the `path` variable via querying udev 'property' database.

    :params: path: path to device, either /dev or /sys
    :returns: dictionary of key=value pairs as exported from the udev database
    :raises: ValueError path is None, ProcessExecutionError on exec error.
    """
    if not path:
        raise ValueError('Invalid path: "%s"' % path)

    info_cmd = ['udevadm', 'info', '--query=property', '--export', path]
    output, _ = util.subp(info_cmd, capture=True)

    # strip for trailing empty line
    info = {}
    for line in output.splitlines():
        if not line:
            continue
        # maxsplit=2 gives us key and remaininng part of line is value
        # py2.7 on Trusty doesn't have keyword, pass as argument
        key, value = line.split('=', 2)
        if not value:
            value = None
        if value:
            # preserve spaces in values to match udev database
            parsed = shlex.split(value)
            if ' ' not in value:
                info[key] = parsed[0]
            else:
                # special case some known entries with spaces, e.g. ID_SERIAL
                # and DEVLINKS, see tests/unittests/test_udev.py
                if key == "DEVLINKS":
                    info[key] = shlex.split(parsed[0])
                elif key == 'ID_SERIAL':
                    info[key] = parsed[0]
                else:
                    info[key] = parsed

    return info


# vi: ts=4 expandtab syntax=python
