# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin import block
from curtin import config
from curtin import futil
from curtin import util

from curtin.commands import curthooks
from .helpers import CiTestCase


class TestPublicAPI(CiTestCase):
    """Test entry points known to be used externally.

    Curtin's only known external library user is the curthooks
    that are present in the MAAS images.  This will test for presense
    of the modules and entry points that are used there.

    This unit test is present to just test entry points.  Function
    behavior should be present elsewhere."""

    def assert_has_callables(self, module, expected):
        self.assertEqual(expected, _module_has(module, expected, callable))

    def test_block(self):
        """Verify expected attributes in curtin.block."""
        self.assert_has_callables(
            block,
            ['get_devices_for_mp', 'get_blockdev_for_partition', '_lsblock'])

    def test_config(self):
        """Verify exported attributes in curtin.config."""
        self.assert_has_callables(config, ['load_config'])

    def test_util(self):
        """Verify exported attributes in curtin.util."""
        self.assert_has_callables(
            util, ['RunInChroot', 'load_command_environment'])

    def test_centos_apply_network_config(self):
        """MAAS images use centos_apply_network_config from cmd.curthooks."""
        self.assert_has_callables(curthooks, ['centos_apply_network_config'])

    def test_futil(self):
        """Verify exported attributes in curtin.futil."""
        self.assert_has_callables(futil, ['write_files'])


def _module_has(module, names, nfilter=None):
    found = [(name, getattr(module, name))
             for name in names if hasattr(module, name)]
    if nfilter is not None:
        found = [(name, attr) for name, attr in found if nfilter(attr)]

    return [name for name, _ in found]

# vi: ts=4 expandtab syntax=python
