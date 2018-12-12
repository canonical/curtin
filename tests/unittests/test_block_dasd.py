# This file is part of curtin. See LICENSE file for copyright and license info.

import mock
import random
import textwrap

from curtin.block import dasd
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


def random_device_id():
    return "%x.%x.%04x" % (random.randint(0, 16),
                           random.randint(0, 16),
                           random.randint(1024, 4096))


def render_lsdasd(template, device_id_line=None):
    if not device_id_line:
        device_id_line = random_device_id()
    return template % device_id_line


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

    def test_with_device_id(self):
        """lsdasd appends device_id param when passed."""

        device_id = random_device_id()
        dasd.lsdasd(device_id=device_id)
        self.assertEqual([
            mock.call(['lsdasd', '--long', '--offline', device_id],
                      capture=True)],
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

    def _random_lsdasd_output(self, device_id=None, entries=16, status=None):
        if not device_id:
            device_id = random_device_id()
        if not status:
            entry = ["%s: %s" % (self.random_string(), self.random_string())]
            status = "\n".join(entry * entries)
        return (device_id, device_id + "\n" + status + "\n")

    def test_parse_lsdasd_no_input(self):
        """_parse_lsdasd raises ValueError on invalid status input."""
        for status_value in [None, 123, {}, (), []]:
            with self.assertRaises(ValueError):
                dasd._parse_lsdasd(status_value)

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
                               "%s/dasda/94:0" % random_device_id())
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))

    def test_parse_lsdasd_returns_device_id_as_key(self):
        """_parse_lsdasd returns dict with device_id as key."""
        (device_id, status) = self._random_lsdasd_output()
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        self.assertEqual(device_id, list(result.keys()).pop())

    def test_parse_lsdasd_defaults_kname_devid_to_none(self):
        """_parse_lsdasd returns dict with kname, devid none if not present."""
        lsdasd = render_lsdasd(LSDASD_OFFLINE_TPL)
        self.assertNotIn('/', lsdasd)
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for device_id, status in result.items():
            self.assertIsNone(status['devid'])
            self.assertIsNone(status['kname'])

    def test_parse_lsdasd_extracts_kname_devid_when_present(self):
        """_parse_lsdasd returns dict with kname, devid when present."""
        lsdasd = render_lsdasd(LSDASD_ACTIVE_TPL,
                               "%s/dasda/94:0" % random_device_id())
        self.assertIn('/', lsdasd)
        result = dasd._parse_lsdasd(lsdasd)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for device_id, status in result.items():
            self.assertIsNotNone(status['devid'])
            self.assertIsNotNone(status['kname'])

    def test_parse_lsdasd_creates_lists_for_splitable_values(self):
        """_parse_lsdasd dict splits values with spaces."""
        mykey = self.random_string()
        myval = " ".join([self.random_string()] * 4)
        mystatus = ("  %s: %s  " % (mykey, myval) +
                    "\n" + "\n".join(['foo: bar'] * 20))
        (device_id, status) = self._random_lsdasd_output(status=mystatus)
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for device_id, status in result.items():
            self.assertEqual(list, type(status[mykey]))

    def test_parse_lsdasd_sets_value_to_none_for_empty_values(self):
        """_parse_lsdasd dict sets None for value of empty values."""
        mykey = self.random_string()
        mystatus = "  %s:  " % mykey + "\n" + "\n".join(['foo: bar'] * 20)
        (device_id, status) = self._random_lsdasd_output(status=mystatus)
        result = dasd._parse_lsdasd(status)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result.keys()))
        for device_id, status in result.items():
            self.assertEqual(None, status[mykey])


class TestDasdGetStatus(CiTestCase):

    lsdasd_status_sep = '\n\n'

    def _compose_lsdasd(self, dasdinput=None, nr_dasd=3):
        if not dasdinput:
            dasdinput = []
            for _ in range(0, nr_dasd):
                tpl = random.choice([LSDASD_OFFLINE_TPL, LSDASD_ACTIVE_TPL,
                                     LSDASD_NOT_FORMATTED_TPL])
                status = render_lsdasd(tpl)
                dasdinput.append(status)

        return "\n".join(dasdinput)

    def _assert_dicts_equal(self, expected, result):
        self.assertEqual(
            {k: expected[k] for k in sorted(expected)},
            {k: result[k] for k in sorted(result)})

    @mock.patch('curtin.block.dasd.lsdasd')
    def test_get_status_noargs(self, m_lsdasd):
        """get_status returns status dict with no arguments passed."""
        generated_output = self._compose_lsdasd()
        m_lsdasd.return_value = generated_output
        expected = {}
        for status in generated_output.split(self.lsdasd_status_sep):
            expected.update(dasd._parse_lsdasd(status))

        result = dasd.get_status()
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self._assert_dicts_equal(expected, result)

    @mock.patch('curtin.block.dasd.lsdasd')
    def test_get_status_single_device_id(self, m_lsdasd):
        """get_status returns status dict for one device_id."""
        device_id = random_device_id()
        generated_output = render_lsdasd(LSDASD_ACTIVE_TPL,
                                         "%s/dasda/94:0" % device_id)
        m_lsdasd.return_value = generated_output
        expected = {}
        for status in generated_output.split(self.lsdasd_status_sep):
            expected.update(dasd._parse_lsdasd(status))

        result = dasd.get_status(device_id=device_id)
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self.assertEqual(1, len(result))
        self._assert_dicts_equal(expected, result)


class TestDasdFormat(CiTestCase):

    def test_bad_devname(self):
        pass

    def test_devname_doesnt_exist_with_strict(self):
        """format raises RuntimeError if devname doesn't exist w/strict=True"""
        pass

    def test_devname_doesnt_exist_no_strict_runs_command(self):
        """format issues cmd w/strict=False and devname doesn't exist."""
        pass

    def test_default_params_match_docstrings(self):
        """format w/defs match docstring."""
        pass

    def test_invalid_blocksize_raise_valueerror(self):
        """format raises ValueError on invalid blocksize value."""
        pass

    def test_invalid_disk_layout_raises_valueerror(self):
        """format raises ValueError on invalid disk_layout value."""
        pass

    def test_invalid_mode_raises_valueerror(self):
        """format raises ValueError on invalid mode value."""
        pass

    def test_force_parameter_added_to_cmd(self):
        """format adds --force to command if param is true."""
        pass

    def test_label_param_passed_to_dasdfmt(self):
        """format adds --label=value to command if set."""
        pass

# vi: ts=4 expandtab syntax=python
