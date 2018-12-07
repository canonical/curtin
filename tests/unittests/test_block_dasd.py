# This file is part of curtin. See LICENSE file for copyright and license info.

import mock
import random
import textwrap

from curtin.config import merge_config
from curtin.block import dasd
from curtin.util import ProcessExecutionError
from .helpers import CiTestCase


LSDASD_OFFLINE_TPL = textwrap.dedent("""\
%s
  status:                offline
  use_diag:                0
  readonly:                0
  eer_enabled:                0
  erplog:                0
  hpf:
  uid:
  paths_installed:             10 11 12 13
  paths_in_use:
  paths_non_preferred:
  paths_invalid_cabling:
  paths_cuir_quiesced:
  paths_invalid_hpf_characteristics:
  paths_error_threshold_exceeded:

""")

LSDASD_NOT_FORMATTED_TPL = textwrap.dedent("""\
%s
  status:                n/f
  type:                 ECKD
  blksz:                512
  size:
  blocks:
  use_diag:                0
  readonly:                0
  eer_enabled:                0
  erplog:                0
  hpf:                    1
  uid:                  IBM.750000000DXP71.XXXX.YY
  paths_installed:             10 11 12 13
  paths_in_use:             10 11 12
  paths_non_preferred:
  paths_invalid_cabling:
  paths_cuir_quiesced:
  paths_invalid_hpf_characteristics:
  paths_error_threshold_exceeded:

""")

LSDASD_ACTIVE_TPL = textwrap.dedent("""\
%s
  status:                active
  type:                 ECKD
  blksz:                4096
  size:                 21129MB
  blocks:                5409180
  use_diag:                0
  readonly:                0
  eer_enabled:                0
  erplog:                0
  hpf:                    1
  uid:                  IBM.750000000DXP71.XXXX.YY
  paths_installed:             10 11 12 13
  paths_in_use:             10 11 12
  paths_non_preferred:
  paths_invalid_cabling:
  paths_cuir_quiesced:
  paths_invalid_hpf_characteristics:
  paths_error_threshold_exceeded:

""")


def random_bus_id():
    return "%x.%x.%04x" % (random.randint(0, 16),
                           random.randint(0, 16),
                           random.randint(1024, 4096))


def render_lsdasd(template, bus_id_line=None):
    if not bus_id_line:
        bus_id_line = random_bus_id()
    return template % bus_id_line


class TestLsdasd(CiTestCase):

    def setUp(self):
        super(TestLsdasd, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')

        # defaults
        self.m_subp.return_value = (None, None)

    def test_noargs(self):
        """lsdasd invoked with --long --offline with no params."""

        dasd.lsdasd()
        self.assertEqual(
                [mock.call(['lsdasd', '--long', '--offline'], capture=True)],
                self.m_subp.call_args_list)

    def test_with_bus_id(self):
        """lsdasd appends bus_id param when passed."""

        bus_id = random_bus_id()
        dasd.lsdasd(bus_id=bus_id)
        self.assertEqual(
                [mock.call(
                    ['lsdasd', '--long', '--offline', bus_id], capture=True)],
                self.m_subp.call_args_list)

    def test_with_offline_false(self):
        """lsdasd does not have --offline if param is false."""

        dasd.lsdasd(offline=False)
        self.assertEqual([mock.call(['lsdasd', '--long'], capture=True)],
                         self.m_subp.call_args_list)

    def test_returns_stdout(self):
        """lsdasd returns stdout from command output."""

        stdout = self.random_string()
        self.m_subp.return_value = (stdout, None)
        output = dasd.lsdasd()
        self.assertEqual(stdout, output)
        self.assertEqual(self.m_subp.call_count, 1)

    def test_ignores_stderr(self):
        """lsdasd does not include stderr in return value."""

        stderr = self.random_string()
        self.m_subp.return_value = (None, stderr)
        output = dasd.lsdasd()
        self.assertNotEqual(stderr, output)
        self.assertEqual(self.m_subp.call_count, 1)


class TestParseLsdasd(CiTestCase):

    def _random_lsdasd_output(self, busid=None, entries=16, status=None):
        if not busid:
            busid = random_bus_id()
        if not status:
           entry = ["%s: %s" % (self.random_string(), self.random_string())]
           status = "\n".join(entry * entries)
        return (busid, busid + "\n" + status + "\n")

    def test_parse_lsdasd_no_input(self):
        """_parse_lsdasd raises ValueError on invalid status input."""
        for status_value in [None, 123, {}, (), []]:
            with self.assertRaises(ValueError):
                result = dasd._parse_lsdasd(status_value)

    def test_parse_lsdasd_invalid_strings_short(self):
        """_parse_lsdasd raises ValueError on short input"""
        with self.assertRaises(ValueError):
            dasd._parse_lsdasd(self.random_string())

    def test_parse_lsdasd_invalid_strings_long(self):
        """_parse_lsdasd raises ValueError on invalid long input."""
        with self.assertRaises(ValueError):
            dasd._parse_lsdasd("\n".join([self.random_string()] * 20))

    def test_parse_lsdasd_returns_dict(self):
        """_parse_lsdasd returns a non-empty dictionary with valid input."""
        lsdasd = render_lsdasd(LSDASD_ACTIVE_TPL,
                               "%s/dasda/94:0" % random_bus_id())
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))

    def test_parse_lsdasd_returns_busid_as_key(self):
        """_parse_lsdasd returns dict with bus_id as key."""
        (busid, status) = self._random_lsdasd_output()
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        self.assertEqual(busid, list(result.keys()).pop())

    def test_parse_lsdasd_returns_busid_as_key(self):
        """_parse_lsdasd returns dict with bus_id as key."""
        (busid, status) = self._random_lsdasd_output()
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        self.assertEqual(busid, list(result.keys()).pop())

    def test_parse_lsdasd_defaults_kname_devid_to_none(self):
        """_parse_lsdasd returns dict with kname, devid none if not present."""
        lsdasd = render_lsdasd(LSDASD_OFFLINE_TPL)
        self.assertNotIn('/', lsdasd)
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for bus_id, status in result.items():
            self.assertIsNone(status['devid'])
            self.assertIsNone(status['kname'])

    def test_parse_lsdasd_extracts_kname_devid_when_present(self):
        """_parse_lsdasd returns dict with kname, devid when present."""
        lsdasd = render_lsdasd(LSDASD_ACTIVE_TPL,
                               "%s/dasda/94:0" % random_bus_id())
        self.assertIn('/', lsdasd)
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for bus_id, status in result.items():
            self.assertIsNotNone(status['devid'])
            self.assertIsNotNone(status['kname'])

    def test_parse_lsdasd_creates_lists_for_splitable_values(self):
        """_parse_lsdasd dict splits values with spaces."""
        mykey = self.random_string()
        myval = " ".join([self.random_string()] * 4)
        mystatus = ("  %s: %s  " % (mykey, myval) +
                    "\n" + "\n".join(['foo: bar'] * 20))
        (busid, status) = self._random_lsdasd_output(status=mystatus)
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for bus_id, status in result.items():
            self.assertEqual(list, type(status[mykey]))

    def test_parse_lsdasd_sets_value_to_none_for_empty_values(self):
        """_parse_lsdasd dict sets None for value of empty values."""
        mykey = self.random_string()
        mystatus = "  %s:  " % mykey + "\n" + "\n".join(['foo: bar'] * 20)
        (busid, status) = self._random_lsdasd_output(status=mystatus)
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for bus_id, status in result.items():
            self.assertEqual(None, status[mykey])


class TestDasdGetStatus(CiTestCase):
    pass

# vi: ts=4 expandtab syntax=python
