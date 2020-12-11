# This file is part of curtin. See LICENSE file for copyright and license info.

import random
import string
import textwrap

from curtin.block import dasd
from curtin import util
from .helpers import CiTestCase


def random_device_id():
    return "%x.%x.%04x" % (random.randint(0, 255),
                           random.randint(0, 255),
                           random.randint(1, 0x10000 - 1))


FDASD_OUTPUT = '''
reading volume label ..: VOL1
reading vtoc ..........: ok


Disk /dev/dasda:
  cylinders ............: 10016
  tracks per cylinder ..: 15
  blocks per track .....: 12
  bytes per block ......: 4096
  volume label .........: VOL1
  volume serial ........: 0X0200
  max partitions .......: 3

 ------------------------------- tracks -------------------------------
               Device      start      end   length   Id  System
          /dev/dasda1          2    21847    21846    1  Linux native
                           21848   150239   128392       unused
exiting...
 '''


class TestDasdPartitionTable(CiTestCase):

    def test_from_dasd_output(self):
        devname = self.random_string()
        dasd_pt = dasd.DasdPartitionTable.from_fdasd_output(
            devname, FDASD_OUTPUT)
        self.assertEqual(dasd_pt.devname, devname)
        self.assertEqual(dasd_pt.blocks_per_track, 12)
        self.assertEqual(dasd_pt.bytes_per_block, 4096)
        self.assertEqual(len(dasd_pt.partitions), 1)
        part = dasd_pt.partitions[0]
        self.assertEqual(part.device, '/dev/dasda1')
        self.assertEqual(part.start, 2)
        self.assertEqual(part.end, 21847)
        self.assertEqual(part.length, 21846)
        self.assertEqual(part.id, '1')
        self.assertEqual(part.system, 'Linux native')


class TestDasdValidDeviceId(CiTestCase):

    nonhex = [letter for letter in string.ascii_lowercase
              if letter not in ['a', 'b', 'c', 'd', 'e', 'f']]

    invalids = [None, '', {}, ('', ), 12, '..', CiTestCase.random_string(),
                'qz.zq.ffff', '.ff.1420', 'ff..1518', '0.0.xyyz',
                'ff.ff.10001', '0.0.15ac.f']

    def random_nonhex(self, length=4):
        return ''.join([random.choice(self.nonhex) for x in range(0, length)])

    def test_valid_none_raises(self):
        """raises ValueError on none-ish values for device_id."""
        for invalid in self.invalids:
            with self.assertRaises(ValueError):
                dasd.DasdDevice(invalid)

    def test_valid_checks_for_two_periods(self):
        """device_id must have exactly two '.' chars"""

        nodots = self.random_string()
        onedot = "%s.%s" % (nodots, self.random_string())
        threedots = "%s.%s." % (onedot, self.random_string())

        for invalid in [nodots, onedot, threedots]:
            self.assertNotEqual(2, invalid.count('.'))
            with self.assertRaises(ValueError):
                dasd.DasdDevice(invalid)

        valid = random_device_id()
        self.assertEqual(2, valid.count('.'))
        dasd.DasdDevice(valid)

    def test_valid_checks_for_three_values_after_split(self):
        """device_id must have exactly three non-empty strings after split."""
        missing_css = ".dsn.dev"
        missing_dsn = "css..dev"
        missing_dev = "css.dsn."
        for invalid in [missing_css, missing_dsn, missing_dev]:
            self.assertEqual(2, invalid.count('.'))
            with self.assertRaises(ValueError):
                dasd.DasdDevice(invalid)

    def test_valid_checks_css_value(self):
        """device_id css component must be in integer range of 0, 256"""
        invalid_css = "ffff.0.abcd"
        with self.assertRaises(ValueError):
            dasd.DasdDevice(invalid_css)

    def test_valid_checks_dsn_value(self):
        """device_id dsn component must be in integer range of 0, 256"""
        invalid_dsn = "f.ffff.abcd"
        with self.assertRaises(ValueError):
            dasd.DasdDevice(invalid_dsn)

    def test_valid_checks_dev_value(self):
        """device_id dev component must be in integer range of 0, 0xFFFF"""
        invalid_dev = "0.0.10001"
        with self.assertRaises(ValueError):
            dasd.DasdDevice(invalid_dev)

    def test_valid_handles_non_hex_values(self):
        """device_id raises ValueError with non hex values in fields"""
        # build a device_id with 3 nonhex random values
        invalid_dev = ".".join([self.random_nonhex() for x in range(0, 3)])
        with self.assertRaises(ValueError):
            dasd.DasdDevice(invalid_dev)


class TestDasdCcwDeviceAttr(CiTestCase):

    def setUp(self):
        super(TestDasdCcwDeviceAttr, self).setUp()
        self.add_patch('curtin.block.dasd.os.path.isfile', 'm_isfile')
        self.add_patch('curtin.block.dasd.util.load_file', 'm_loadfile')
        self.add_patch('curtin.block.dasd.glob.glob', 'm_glob')

        # defaults
        self.m_isfile.return_value = True
        self.m_loadfile.return_value = self.random_string()
        self.dasd = dasd.DasdDevice(random_device_id())

    def _test_ccw_attr(self, my_attr=None, attr_val_in=None, attr_val=None):
        if not my_attr:
            my_attr = self.random_string()
        self.m_loadfile.return_value = attr_val_in
        attr_path = '/sys/bus/ccw/devices/%s/%s' % (self.dasd.device_id,
                                                    my_attr)
        result = self.dasd.ccw_device_attr(my_attr)
        self.assertEqual(attr_val, result)
        self.m_isfile.assert_called_with(attr_path)
        if result:
            self.m_loadfile.assert_called_with(attr_path)
        return result

    def test_ccw_device_attr_reads_attr(self):
        """ccw_device_attr reads specified attr and provides value."""
        attr_val = self.random_string()
        self._test_ccw_attr(attr_val_in=attr_val, attr_val=attr_val)

    def test_ccw_device_attr_strips_attr_value(self):
        """ccw_device_attr returns stripped attr value."""
        attr_val = '%s' % self.random_string()
        attr_val_in = attr_val + '\n'
        self._test_ccw_attr(attr_val_in=attr_val_in, attr_val=attr_val)

    def test_ccw_device_attr_returns_none_if_invalid_path(self):
        """ccw_device_attr returns None for missing attributes"""
        self.m_isfile.return_value = False
        attr_path = self.random_string()
        attr_val_in = self.random_string()
        self._test_ccw_attr(my_attr=attr_path, attr_val_in=attr_val_in,
                            attr_val=None)

    def test_is_not_formatted_returns_true_when_unformatted(self):
        self.m_loadfile.return_value = 'unformatted'
        self.assertTrue(self.dasd.is_not_formatted())

    def test_is_not_formatted_returns_false_if_formatted(self):
        self.m_loadfile.return_value = self.random_string()
        self.assertFalse(self.dasd.is_not_formatted())

    def test_blocksize(self):
        blocksize_val = '%d' % random.choice([512, 1024, 2048, 4096])
        path = self.random_string()
        self.m_glob.return_value = [path]
        self.m_loadfile.return_value = blocksize_val
        self.assertEqual(blocksize_val, self.dasd.blocksize())
        self.m_loadfile.assert_called_once_with(path)


class TestDiskLayout(CiTestCase):

    def setUp(self):
        super(TestDiskLayout, self).setUp()
        self.add_patch('curtin.block.dasd.dasd_format', 'm_dasd_format')
        dpath = 'curtin.block.dasd.DasdDevice'
        self.add_patch(dpath + '.devname', 'm_devname')

        self.dasd = dasd.DasdDevice(random_device_id())
        self.devname = self.random_string()
        self.m_devname.return_value = self.devname

    def test_disk_layout_returns_dasd_format_result(self):
        """disk_layout returns dasd disk_layout format as string"""
        expected = self.m_dasd_format.return_value = self.random_string()
        self.assertEqual(expected, self.dasd.disk_layout())

    def test_disk_layout_raises_valueerror_on_missing_format(self):
        """disk_layout raises ValueError if view missing 'format' section."""
        self.m_dasd_format.return_value = None
        with self.assertRaises(ValueError):
            self.dasd.disk_layout()


class TestLabel(CiTestCase):

    info = {'ID_BUS': 'ccw', 'ID_TYPE': 'disk',
            'ID_UID': 'IBM.750000000DXP71.1500.18',
            'ID_XUID': 'IBM.750000000DXP71.1500.18',
            'ID_SERIAL': '0X1518'}

    info_nolabel = {'ID_BUS': 'ccw', 'ID_TYPE': 'disk',
                    'ID_UID': 'IBM.750000000DXP71.1500.18',
                    'ID_XUID': 'IBM.750000000DXP71.1500.18'}

    def setUp(self):
        super(TestLabel, self).setUp()
        self.add_patch('curtin.block.dasd.dasdinfo', 'm_dasdinfo')

        # defaults
        self.m_dasdinfo.return_value = self.info
        self.dasd = dasd.DasdDevice(random_device_id())

    def test_label_returns_disk_serial(self):
        self.assertIsNotNone(self.dasd.label())
        self.m_dasdinfo.assert_called_with(self.dasd.device_id)

    def test_label_raises_valueerror_if_no_label(self):
        self.m_dasdinfo.return_value = self.info_nolabel
        with self.assertRaises(ValueError):
            self.dasd.label()


class TestNeedsFormatting(CiTestCase):

    def setUp(self):
        super(TestNeedsFormatting, self).setUp()
        dpath = 'curtin.block.dasd.DasdDevice'
        self.add_patch(dpath + '.is_not_formatted', 'm_not_fmt')
        self.add_patch(dpath + '.blocksize', 'm_blocksize')
        self.add_patch(dpath + '.disk_layout', 'm_disk_layout')
        self.add_patch(dpath + '.label', 'm_label')

        self.m_not_fmt.return_value = False
        self.blocksize = 4096
        self.m_blocksize.return_value = self.blocksize
        self.disk_layout = self.random_string()
        self.m_disk_layout.return_value = self.disk_layout
        self.label = self.random_string()
        self.m_label.return_value = self.label

        self.dasd = dasd.DasdDevice(random_device_id())

    def test_needs_formatting_label_mismatch(self):
        my_label = self.random_string()
        self.assertNotEqual(self.label, my_label)
        self.assertTrue(
            self.dasd.needs_formatting(
                self.blocksize, self.disk_layout, my_label))

    def test_needs_formatting_layout_mismatch(self):
        my_layout = self.random_string()
        self.assertNotEqual(self.disk_layout, my_layout)
        self.assertTrue(
            self.dasd.needs_formatting(
                self.blocksize, my_layout, self.label))

    def test_needs_formatting_blocksize_mismatch(self):
        my_blocksize = random.randrange(self.blocksize)
        self.assertNotEqual(self.blocksize, my_blocksize)
        self.assertTrue(
            self.dasd.needs_formatting(
                my_blocksize, self.disk_layout, self.label))

    def test_needs_formatting_unformatted_disk(self):
        self.m_not_fmt.return_value = True
        self.assertTrue(
            self.dasd.needs_formatting(
                self.blocksize, self.disk_layout, self.label))

    def test_needs_formatting_ignores_label_mismatch(self):
        self.assertFalse(
            self.dasd.needs_formatting(
                self.blocksize, self.disk_layout, None))


class TestFormat(CiTestCase):

    def setUp(self):
        super(TestFormat, self).setUp()
        self.add_patch('curtin.block.dasd.os.path.exists', 'm_exists')
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')
        dpath = 'curtin.block.dasd.DasdDevice'
        self.add_patch(dpath + '.devname', 'm_devname')

        # defaults
        self.m_exists.return_value = True
        self.m_subp.return_value = (None, None)
        self.dasd = dasd.DasdDevice(random_device_id())
        self.devname = self.random_string()
        self.m_devname.return_value = self.devname

    def test_format_defaults_match_docstring(self):
        self.dasd.format()
        self.m_subp.assert_called_with(
            ['dasdfmt', '-y', '--blocksize=4096', '--disk_layout=cdl',
             '--mode=quick', self.dasd.devname], capture=True)

    def test_format_uses_supplied_params(self):
        blksize = 512
        layout = 'ldl'
        set_label = self.random_string()
        mode = 'quick'
        self.dasd.format(blksize=blksize, layout=layout,
                         set_label=set_label, mode=mode)
        self.m_subp.assert_called_with(
            ['dasdfmt', '-y', '--blocksize=%s' % blksize,
             '--disk_layout=%s' % layout, '--mode=%s' % mode,
             '--label=%s' % set_label, self.dasd.devname], capture=True)

    def test_format_no_label_ignores_set_label_keep_label(self):
        blksize = 512
        layout = 'ldl'
        set_label = self.random_string()
        mode = 'quick'
        self.dasd.format(blksize=blksize, layout=layout,
                         set_label=set_label, no_label=True, mode=mode)
        self.m_subp.assert_called_with(
            ['dasdfmt', '-y', '--blocksize=%s' % blksize,
             '--disk_layout=%s' % layout, '--mode=%s' % mode,
             '--no_label', self.dasd.devname], capture=True)

    def test_format_keep_label_ignores_set_label(self):
        blksize = 512
        layout = 'ldl'
        set_label = self.random_string()
        mode = 'quick'
        self.dasd.format(blksize=blksize, layout=layout,
                         set_label=set_label, keep_label=True, mode=mode)
        self.m_subp.assert_called_with(
            ['dasdfmt', '-y', '--blocksize=%s' % blksize,
             '--disk_layout=%s' % layout, '--mode=%s' % mode,
             '--keep_label', self.dasd.devname], capture=True)

    def test_format_raise_valueerror_on_bad_blksize(self):
        rval = random.randint(1, 5000)
        blksize = (rval + 1) if rval in [512, 1024, 2048, 4096] else rval
        self.assertNotIn(blksize, [512, 1024, 2048, 4096])
        with self.assertRaises(ValueError):
            self.dasd.format(blksize=blksize)

    def test_format_raise_valueerror_on_bad_layout(self):
        layout = self.random_string()
        with self.assertRaises(ValueError):
            self.dasd.format(layout=layout)

    def test_format_raise_valueerror_on_mode(self):
        mode = self.random_string()
        with self.assertRaises(ValueError):
            self.dasd.format(mode=mode)

    def test_format_add_force_if_set(self):
        self.dasd.format(force=True)
        self.m_subp.assert_called_with(
            ['dasdfmt', '-y', '--blocksize=4096', '--disk_layout=cdl',
             '--mode=quick', '--force', self.dasd.devname], capture=True)


class TestDasdInfo(CiTestCase):

    info = textwrap.dedent("""\
        ID_BUS=ccw
        ID_TYPE=disk
        ID_UID=IBM.750000000DXP71.1500.20
        ID_XUID=IBM.750000000DXP71.1500.20
        ID_SERIAL=0x1520
        """)

    def setUp(self):
        super(TestDasdInfo, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')

        # defaults
        self.m_subp.return_value = ('', '')

    def test_info_returns_dictionary(self):
        """dasdinfo returns dictionary of device info."""
        device_id = random_device_id()
        self.m_subp.return_value = (self.info, '')
        expected = util.load_shell_content(self.info)
        self.assertDictEqual(expected, dasd.dasdinfo(device_id))

    def test_info_raises_on_failure(self):
        """dasdinfo raises if the process invocation fails."""
        device_id = random_device_id()
        expected_stdout = self.random_string()
        expected_stderr = self.random_string()
        self.m_subp.side_effect = (
            util.ProcessExecutionError(stdout=expected_stdout,
                                       stderr=expected_stderr,
                                       exit_code=random.randint(1, 255),
                                       cmd=self.random_string()))
        with self.assertRaises(util.ProcessExecutionError):
            dasd.dasdinfo(device_id)


class TestDasdFormat(CiTestCase):

    def setUp(self):
        super(TestDasdFormat, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')
        self.add_patch('curtin.block.dasd.os.path.exists', 'm_exists')
        self.add_patch('curtin.block.dasd._dasd_format', 'm_dasd_format')

        # defaults
        self.m_exists.return_value = True
        self.m_subp.return_value = ('', '')

    def test_dasd_format_raise_error_on_invalid_device(self):
        """dasdview raises error on invalid device path."""
        devname = self.random_string()
        self.m_exists.return_value = False
        with self.assertRaises(ValueError):
            dasd.dasd_format(devname)

    def test_dasd_foramt_calls__dasd_format(self):
        """dasdview calls parser on output from dasdview command."""
        devname = self.random_string()
        view = self.random_string()
        self.m_subp.return_value = (view, self.random_string())
        dasd.dasd_format(devname)
        self.m_subp.assert_called_with(
            ['dasdview', '--extended', devname], capture=True)
        self.m_dasd_format.assert_called_with(view)


class Test_DasdFormat(CiTestCase):

    view_output_template = textwrap.dedent("""\

    --- general DASD information ----------------------------------------------
    device node            : /dev/dasdd
    busid                  : 0.0.1518
    type                   : ECKD
    device type            : hex 3390  	dec 13200

    --- DASD geometry ---------------------------------------------------------
    number of cylinders    : hex 2721  	dec 10017
    tracks per cylinder    : hex f  	dec 15
    blocks per track       : hex c  	dec 12
    blocksize              : hex 1000  	dec 4096

    --- extended DASD information ---------------------------------------------
    real device number     : hex 0  	dec 0
    subchannel identifier  : hex 178  	dec 376
    CU type  (SenseID)     : hex 3990  	dec 14736
    CU model (SenseID)     : hex e9  	dec 233
    device type  (SenseID) : hex 3390  	dec 13200
    device model (SenseID) : hex c  	dec 12
    open count             : hex 1  	dec 1
    req_queue_len          : hex 0  	dec 0
    chanq_len              : hex 0  	dec 0
    status                 : hex 5  	dec 5
    label_block            : hex 2  	dec 2
    FBA_layout             : hex 0  	dec 0
    characteristics_size   : hex 40  	dec 64
    confdata_size          : hex 100  	dec 256
    format                 : hex 2  	dec 2      	{format}
    features               : hex 0  	dec 0      	default

    characteristics        : 3990e933 900c5e0c  39f72032 2721000f
                             e000e5a2 05940222  13090674 00000000
                             00000000 00000000  32321502 dfee0001
                             0677080f 007f4800  1f3c0000 00002721

    configuration_data     : dc010100 f0f0f2f1  f0f7f9f0 f0c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10818
                             d4020000 f0f0f2f1  f0f7f9f6 f1c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10800
                             d0000000 f0f0f2f1  f0f7f9f6 f1c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f00800
                             f0000001 f0f0f2f1  f0f7f9f0 f0c9c2d4
                             f7f5f0f0 f0f0f0f0  f0c4e7d7 f7f10800
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             00000000 00000000  00000000 00000000
                             81000003 2d001e00  15000247 000c0016
                             000cc018 935e41ee  00030000 0000a000""")

    def test__dasd_format_returns_format(self):
        """_parse_dasdview returns dict w/ required keys parsing valid view."""
        for (format, expected) in [
                ('CDL formatted', 'cdl'),
                ('LDL formatted', 'ldl'),
                ('not formatted', 'not-formatted'),
                ]:
            result = dasd._dasd_format(
                self.view_output_template.format(format=format))
            self.assertEqual(result, expected)

# vi: ts=4 expandtab syntax=python
