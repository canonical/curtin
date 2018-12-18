# This file is part of curtin. See LICENSE file for copyright and license info.

import mock
import random
import string
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
    return "%x.%x.%04x" % (random.randint(0, 256),
                           random.randint(0, 256),
                           random.randint(1, 65535))


def render_lsdasd(template, device_id_line=None):
    if not device_id_line:
        device_id_line = random_device_id()
    return template % device_id_line


class TestDasdIsValidDeviceId(CiTestCase):

    nonhex = [l for l in string.ascii_lowercase if l not in
              ['a', 'b', 'c', 'd', 'e', 'f']]

    def random_nonhex(self, length=4):
        return ''.join([random.choice(self.nonhex) for x in range(0, length)])

    def test_is_valid_none_raises(self):
        """raises ValueError on none-ish values for device_id."""
        for invalid in [None, '', {}, ('', ), 12]:
            with self.assertRaises(ValueError):
                dasd.is_valid_device_id(invalid)

    def test_is_valid_checks_for_two_periods(self):
        """device_id must have exactly two '.' chars"""

        nodots = self.random_string()
        onedot = "%s.%s" % (nodots, self.random_string())
        threedots = "%s.%s." % (onedot, self.random_string())

        for invalid in [nodots, onedot, threedots]:
            print(invalid)
            self.assertNotEqual(2, invalid.count('.'))
            with self.assertRaises(ValueError):
                dasd.is_valid_device_id(invalid)

        valid = random_device_id()
        self.assertEqual(2, valid.count('.'))
        dasd.is_valid_device_id(valid)

    def test_is_valid_checks_for_three_values_after_split(self):
        """device_id must have exactly three non-empty strings after split."""
        missing_css = ".dsn.dev"
        missing_dsn = "css..dev"
        missing_dev = "css.dsn."
        for invalid in [missing_css, missing_dsn, missing_dev]:
            self.assertEqual(2, invalid.count('.'))
            with self.assertRaises(ValueError):
                dasd.is_valid_device_id(invalid)

    def test_is_valid_checks_css_value(self):
        """device_id css component must be in integer range of 0, 256"""
        invalid_css = "ffff.0.abcd"
        with self.assertRaises(ValueError):
            dasd.is_valid_device_id(invalid_css)

    def test_is_valid_checks_dsn_value(self):
        """device_id dsn component must be in integer range of 0, 256"""
        invalid_dsn = "f.ffff.abcd"
        with self.assertRaises(ValueError):
            dasd.is_valid_device_id(invalid_dsn)

    def test_is_valid_checks_dev_value(self):
        """device_id dev component must be in integer range of 0, 0xFFFF"""
        invalid_dev = "0.0.10001"
        with self.assertRaises(ValueError):
            dasd.is_valid_device_id(invalid_dev)

    def test_is_valid_handles_non_hex_values(self):
        """device_id raises ValueError with non hex values in fields"""
        # build a device_id with 3 nonhex random values
        invalid_dev = ".".join([self.random_nonhex() for x in range(0, 3)])
        with self.assertRaises(ValueError):
            dasd.is_valid_device_id(invalid_dev)


class TestDasdValidDeviceId(CiTestCase):

    invalids = [None, '', {}, ('', ), 12, '..', CiTestCase.random_string(),
                'qz.zq.ffff', '.ff.1420', 'ff..1518', '0.0.xyyz',
                'ff.ff.10001', '0.0.15ac.f']

    def test_valid_device_id_returns_true(self):
        """returns True when given valid device_id."""
        self.assertTrue(dasd.valid_device_id(random_device_id()))

    def test_valid_device_id_returns_false_if_not_valid(self):
        """returns False when given a value that does not meet requirements"""
        for invalid in self.invalids:
            self.assertFalse(dasd.valid_device_id(invalid))


class TestDasdDeviceIdToKname(CiTestCase):

    def setUp(self):
        super(TestDasdDeviceIdToKname, self).setUp()
        self.add_patch('curtin.block.dasd.valid_device_id', 'm_valid')
        self.add_patch('curtin.block.dasd.is_online', 'm_online')
        self.add_patch('curtin.block.dasd.os.path.isdir', 'm_isdir')
        self.add_patch('curtin.block.dasd.os.listdir', 'm_listdir')

        # defaults
        self.m_valid.return_value = True
        self.m_online.return_value = True
        self.m_isdir.return_value = True
        self.m_listdir.return_value = [self.random_string()]

    def test_device_id_to_kname_returns_kname(self):
        """returns a dasd kname if device_id is valid and online """
        result = dasd.device_id_to_kname(random_device_id())
        self.assertIsNotNone(result)
        self.assertGreater(len(result), len("dasda"))

    def test_devid_to_kname_raises_valueerror_invalid_device_id(self):
        """device_id_to_kname raises ValueError on invalid device_id."""
        self.m_valid.return_value = False
        device_id = self.random_string()
        with self.assertRaises(ValueError):
            dasd.device_id_to_kname(device_id)
        self.m_valid.assert_called_with(device_id)
        self.assertEqual(1, self.m_valid.call_count)
        self.assertEqual(0, self.m_online.call_count)
        self.assertEqual(0, self.m_isdir.call_count)
        self.assertEqual(0, self.m_listdir.call_count)

    def test_devid_to_kname_raises_runtimeerror_no_online(self):
        """device_id_to_kname raises RuntimeError on offline devices."""
        self.m_online.return_value = False
        device_id = self.random_string()
        with self.assertRaises(RuntimeError):
            dasd.device_id_to_kname(device_id)
        self.m_valid.assert_called_with(device_id)
        self.assertEqual(1, self.m_valid.call_count)
        self.m_online.assert_called_with(device_id)
        self.assertEqual(1, self.m_online.call_count)
        self.assertEqual(0, self.m_isdir.call_count)
        self.assertEqual(0, self.m_listdir.call_count)

    def test_devid_to_kname_raises_runtimeerror_no_blockpath(self):
        """device_id_to_kname raises RuntimeError on invalid sysfs path."""
        self.m_isdir.return_value = False
        device_id = self.random_string()
        with self.assertRaises(RuntimeError):
            dasd.device_id_to_kname(device_id)
        self.m_valid.assert_called_with(device_id)
        self.assertEqual(1, self.m_valid.call_count)
        self.m_online.assert_called_with(device_id)
        self.assertEqual(1, self.m_online.call_count)
        self.assertEqual(1, self.m_isdir.call_count)
        self.m_isdir.assert_called_with(
            '/sys/bus/ccw/devices/%s/block' % device_id)
        self.assertEqual(0, self.m_listdir.call_count)

    def test_devid_to_kname_raises_runtimeerror_empty_blockdir(self):
        """device_id_to_kname raises RuntimeError on empty blockdir."""
        device_id = self.random_string()
        self.m_listdir.return_value = []
        with self.assertRaises(RuntimeError):
            dasd.device_id_to_kname(device_id)
        self.m_valid.assert_called_with(device_id)
        self.assertEqual(1, self.m_valid.call_count)
        self.m_online.assert_called_with(device_id)
        self.assertEqual(1, self.m_online.call_count)
        self.assertEqual(1, self.m_isdir.call_count)
        self.m_isdir.assert_called_with(
            '/sys/bus/ccw/devices/%s/block' % device_id)
        self.m_listdir.assert_called_with(
            '/sys/bus/ccw/devices/%s/block' % device_id)
        self.assertEqual(1, self.m_listdir.call_count)


class TestDasdKnameToDeviceId(CiTestCase):

    def setUp(self):
        super(TestDasdKnameToDeviceId, self).setUp()
        self.add_patch('curtin.block.dasd.os.path.exists', 'm_exists')
        self.add_patch('curtin.block.dasd.os.path.realpath', 'm_realpath')

        # defaults
        self.m_exists.return_value = True
        self.m_realpath.return_value = self._mk_device_path()

    def _mk_device_path(self, css_id=None, device_id=None):
        if not css_id:
            css_id = random_device_id()
        if not device_id:
            device_id = random_device_id()
        return '/sys/devices/css0/%s/%s' % (css_id, device_id)

    def test_kname_raises_value_error_on_invalid_kname(self):
        """kname_to_device_id raises ValueError on invalid kname."""
        for invalid in [None, '']:
            with self.assertRaises(ValueError):
                dasd.kname_to_device_id(invalid)

    def test_kname_strips_leading_dev(self):
        """kname_to_device_id strips leading /dev/ from kname if found."""
        kname = self.random_string()
        devname = '/dev/' + kname
        dasd.kname_to_device_id(devname)
        self.m_exists.assert_called_with(
            '/sys/class/block/%s/device' % kname)

    def test_kname_raises_runtimeerror_on_missing_sysfs_path(self):
        """kname_to_device_id raises RuntimeError if sysfs path missing."""
        kname = self.random_string()
        self.m_exists.return_value = False
        with self.assertRaises(RuntimeError):
            dasd.kname_to_device_id(kname)
        self.m_exists.assert_called_with(
            '/sys/class/block/%s/device' % kname)

    def test_kname_returns_device_id(self):
        """kname_to_device returns device_id rom sysfs kname path."""
        device_id = random_device_id()
        self.m_realpath.return_value = (
            self._mk_device_path(device_id=device_id))
        result = dasd.kname_to_device_id(self.random_string())
        self.assertEqual(device_id, result)


class TestDasdCcwDeviceAttr(CiTestCase):

    def setUp(self):
        super(TestDasdCcwDeviceAttr, self).setUp()
        self.add_patch('curtin.block.dasd.valid_device_id', 'm_valid')
        self.add_patch('curtin.block.dasd.os.path.isfile', 'm_isfile')
        self.add_patch('curtin.block.dasd.util.load_file', 'm_loadfile')

        # defaults
        self.m_valid.return_value = True
        self.m_isfile.return_value = True
        self.m_loadfile.return_value = self.random_string()

    def test_ccw_device_attr_invalid_device_id(self):
        """ccw_device_attr raises ValueError on invalid device_id values."""
        invalid = random.choice(TestDasdValidDeviceId.invalids)
        self.m_valid.return_value = False
        with self.assertRaises(ValueError):
            dasd.ccw_device_attr(invalid, self.random_string())

    def test_ccw_device_attr_reads_attr(self):
        """ccw_device_attr reads specified attr and provides value."""
        my_device = random_device_id
        my_attr = self.random_string()
        attr_val = self.random_string()
        self.m_loadfile.return_value = attr_val
        attr_path = '/sys/bus/ccw/devices/%s/%s' % (my_device, my_attr)

        result = dasd.ccw_device_attr(my_device, my_attr)
        self.assertEqual(attr_val, result)
        self.m_isfile.assert_called_with(attr_path)
        self.m_loadfile.assert_called_with(attr_path)

    def test_ccw_device_attr_strips_attr_value(self):
        """ccw_device_attr returns stripped attr value."""
        my_device = random_device_id
        my_attr = self.random_string()
        attr_val = '%s\n' % self.random_string()
        self.m_loadfile.return_value = attr_val
        attr_path = '/sys/bus/ccw/devices/%s/%s' % (my_device, my_attr)

        result = dasd.ccw_device_attr(my_device, my_attr)
        self.assertEqual(attr_val.strip(), result)
        self.m_isfile.assert_called_with(attr_path)
        self.m_loadfile.assert_called_with(attr_path)

    def test_ccw_device_attr_returns_empty_string_if_invalid_path(self):
        """ccw_device_attr returns empty string for missing attributes"""
        my_device = random_device_id
        my_attr = self.random_string()
        self.m_isfile.return_value = False
        attr_path = '/sys/bus/ccw/devices/%s/%s' % (my_device, my_attr)
        result = dasd.ccw_device_attr(my_device, my_attr)
        self.assertEqual('', result)
        self.m_isfile.assert_called_with(attr_path)

    def test_is_active_returns_true_if_status_is_online(self):
        self.m_loadfile.return_value = 'online'
        result = dasd.is_active(random_device_id())
        self.assertTrue(result)

    def test_is_active_returns_false_if_status_is_not_online(self):
        self.m_loadfile.return_value = self.random_string()
        result = dasd.is_active(random_device_id())
        self.assertFalse(result)

    def test_is_alias_returns_true_if_alias(self):
        self.m_loadfile.return_value = '1'
        result = dasd.is_alias(random_device_id())
        self.assertTrue(result)

    def test_is_alias_returns_false_if_not_alias(self):
        self.m_loadfile.return_value = self.random_string()
        result = dasd.is_alias(random_device_id())
        self.assertFalse(result)

    def test_is_not_formatted_returns_true_when_unformatted(self):
        self.m_loadfile.return_value = 'unformatted'
        result = dasd.is_not_formatted(random_device_id())
        self.assertTrue(result)

    def test_is_not_formatted_returns_false_if_formatted(self):
        self.m_loadfile.return_value = self.random_string()
        result = dasd.is_not_formatted(random_device_id())
        self.assertFalse(result)

    def test_is_online_returns_true_if_alias(self):
        self.m_loadfile.return_value = '1'
        result = dasd.is_online(random_device_id())
        self.assertTrue(result)

    def test_is_online_returns_false_if_not_online(self):
        self.m_loadfile.return_value = self.random_string()
        result = dasd.is_online(random_device_id())
        self.assertFalse(result)

    def test_status_returns_device_status_attr(self):
        status_val = self.random_string()
        self.m_loadfile.return_value = status_val
        self.assertEqual(status_val, dasd.status(random_device_id()))

    @mock.patch('curtin.block.dasd.device_id_to_kname')
    def test_blocksize(self, m_kname):
        m_kname.return_value = self.random_string()
        blocksize_val = '%d' % random.choice([512, 1024, 2048, 4096])
        self.m_loadfile.return_value = blocksize_val
        self.assertEqual(blocksize_val, dasd.blocksize(random_device_id()))


class TestDiskLayout(CiTestCase):

    dasdvalue_not = dasd.Dasdvalue(0x0, 0, 'not-formatted')
    dasdvalue_ldl = dasd.Dasdvalue(0x1, 1, 'ldl')
    dasdvalue_cdl = dasd.Dasdvalue(0x2, 2, 'cdl')

    def setUp(self):
        super(TestDiskLayout, self).setUp()
        self.add_patch('curtin.block.dasd.device_id_to_kname', 'm_devid')
        self.add_patch('curtin.block.dasd.os.path.exists', 'm_exists')
        self.add_patch('curtin.block.dasd.dasdview', 'm_dasdview')

        # defaults
        self.m_devid.return_value = random_device_id()
        self.m_exists.return_value = True
        self.m_dasdview.return_value = {
            'extended': {'format': self.dasdvalue_not}}

    def test_disk_layout_returns_dasd_extended_format_value(self):
        """disk_layout returns dasd disk_layout format as string"""
        self.assertEqual(self.dasdvalue_not.txt,
                         dasd.disk_layout(devname=self.random_string()))

    def test_disk_layout_converts_device_id_to_devname(self):
        """disk_layout uses device_id to construct a devname."""
        my_device_id = random_device_id()
        my_kname = self.random_string()
        my_devname = '/dev/' + my_kname
        self.m_devid.return_value = my_kname
        self.assertEqual(self.dasdvalue_not.txt,
                         dasd.disk_layout(device_id=my_device_id))
        self.m_devid.assert_called_with(my_device_id)
        self.m_exists.assert_called_with(my_devname)
        self.m_dasdview.assert_called_with(my_devname)

    def test_disk_layout_raises_valuerror_without_devid_or_devname(self):
        """disk_layout raises ValueError if not provided devid or devname."""
        with self.assertRaises(ValueError):
            dasd.disk_layout()

    def test_disk_layout_raises_valuerror_if_devname_is_not_found(self):
        """disk_layout raises ValueError if devpath does not exist."""
        self.m_exists.return_value = False
        with self.assertRaises(ValueError):
            dasd.disk_layout(devname=self.random_string())


class TestLsdasd(CiTestCase):

    def setUp(self):
        super(TestLsdasd, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')

        # defaults
        self.m_subp.return_value = (None, None)

    def test_noargs(self):
        """lsdasd invoked with --long --offline with no params."""

        dasd.lsdasd(rawoutput=True)
        self.assertEqual(
                [mock.call(['lsdasd', '--long', '--offline'], capture=True)],
                self.m_subp.call_args_list)

    def test_with_device_id(self):
        """lsdasd appends device_id param when passed."""

        device_id = random_device_id()
        dasd.lsdasd(device_id=device_id, rawoutput=True)
        self.assertEqual([
            mock.call(['lsdasd', '--long', '--offline', device_id],
                      capture=True)],
            self.m_subp.call_args_list)

    def test_with_offline_false(self):
        """lsdasd does not have --offline if param is false."""

        dasd.lsdasd(offline=False, rawoutput=True)
        self.assertEqual([mock.call(['lsdasd', '--long'], capture=True)],
                         self.m_subp.call_args_list)

    def test_returns_stdout(self):
        """lsdasd returns stdout from command output."""

        stdout = self.random_string()
        self.m_subp.return_value = (stdout, None)
        output = dasd.lsdasd(rawoutput=True)
        self.assertEqual(stdout, output[0])
        self.assertEqual(self.m_subp.call_count, 1)

    def test_ignores_stderr(self):
        """lsdasd does not include stderr in return value."""

        stderr = self.random_string()
        self.m_subp.return_value = (None, stderr)
        output = dasd.lsdasd(rawoutput=True)
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


class TestLsdasdDict(CiTestCase):

    lsdasd_status_sep = '\n\n'

    def setUp(self):
        super(TestLsdasdDict, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')

        # defaults
        self.m_subp.return_value = (None, None)

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

    def test_lsdasd_noargs(self):
        """lsdasd returns status dict with no arguments passed."""
        generated_output = self._compose_lsdasd()
        self.m_subp.return_value = (generated_output, '')
        expected = {}
        for status in generated_output.split(self.lsdasd_status_sep):
            expected.update(dasd._parse_lsdasd(status))

        result = dasd.lsdasd()
        self.assertEqual(dict, type(result))
        self.assertNotEqual({}, result)
        self._assert_dicts_equal(expected, result)

    def test_lsdasd_single_device_id(self):
        """lsdasd returns status dict for one device_id."""
        device_id = random_device_id()
        generated_output = render_lsdasd(LSDASD_ACTIVE_TPL,
                                         "%s/dasda/94:0" % device_id)
        self.m_subp.return_value = (generated_output, '')
        expected = {}
        for status in generated_output.split(self.lsdasd_status_sep):
            expected.update(dasd._parse_lsdasd(status))

        result = dasd.lsdasd(device_id=device_id)
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
