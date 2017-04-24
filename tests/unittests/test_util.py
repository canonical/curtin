from unittest import TestCase, skipIf
import mock
import os
import stat
import shutil
import tempfile

from curtin import util
from .helpers import simple_mocked_open


class TestLogTimer(TestCase):
    def test_logger_called(self):
        data = {}

        def mylog(msg):
            data['msg'] = msg

        with util.LogTimer(mylog, "mymessage"):
            pass

        self.assertIn("msg", data)
        self.assertIn("mymessage", data['msg'])


class TestDisableDaemons(TestCase):
    prcpath = "usr/sbin/policy-rc.d"

    def setUp(self):
        self.target = tempfile.mkdtemp()
        self.temp_prc = os.path.join(self.target, self.prcpath)

    def tearDown(self):
        shutil.rmtree(self.target)

    def test_disable_daemons_in_root_works(self):
        ret = util.disable_daemons_in_root(self.target)
        self.assertTrue(ret)
        self.assertTrue(os.path.exists(self.temp_prc))

        ret = util.undisable_daemons_in_root(self.target)

        # return should have been true (it removed) and file should be gone
        self.assertTrue(ret)
        self.assertFalse(os.path.exists(self.temp_prc))

    def test_disable_daemons_with_existing_is_false(self):
        util.write_file(os.path.join(self.target, self.prcpath), "foo")
        ret = util.disable_daemons_in_root(self.target)

        # the return should have been false (it did not create)
        # but the file should still exist
        self.assertFalse(ret)
        self.assertTrue(os.path.exists(self.temp_prc))


class TestWhich(TestCase):
    def setUp(self):
        self.orig_is_exe = util.is_exe
        util.is_exe = self.my_is_exe
        self.orig_path = os.environ.get("PATH")
        os.environ["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin"

    def tearDown(self):
        if self.orig_path is None:
            del os.environ["PATH"]
        else:
            os.environ["PATH"] = self.orig_path

        util.is_exe = self.orig_is_exe
        self.exe_list = []

    def my_is_exe(self, fpath):
        return os.path.abspath(fpath) in self.exe_list

    def test_target_none(self):
        self.exe_list = ["/usr/bin/ls"]
        self.assertEqual(util.which("ls"), "/usr/bin/ls")

    def test_no_program_target_none(self):
        self.exe_list = []
        self.assertEqual(util.which("fuzz"), None)

    def test_target_set(self):
        self.exe_list = ["/foo/bin/ls"]
        self.assertEqual(util.which("ls", target="/foo"), "/bin/ls")

    def test_no_program_target_set(self):
        self.exe_list = ["/usr/bin/ls"]
        self.assertEqual(util.which("fuzz"), None)

    def test_custom_path_target_unset(self):
        self.exe_list = ["/usr/bin2/fuzz"]
        self.assertEqual(
            util.which("fuzz", search=["/bin1", "/usr/bin2"]),
            "/usr/bin2/fuzz")

    def test_custom_path_target_set(self):
        self.exe_list = ["/target/usr/bin2/fuzz"]
        found = util.which("fuzz", search=["/bin1", "/usr/bin2"],
                           target="/target")
        self.assertEqual(found, "/usr/bin2/fuzz")


class TestLsbRelease(TestCase):
    def setUp(self):
        self._reset_cache()

    def _reset_cache(self):
        keys = [k for k in util._LSB_RELEASE.keys()]
        for d in keys:
            del util._LSB_RELEASE[d]

    @mock.patch("curtin.util.subp")
    def test_lsb_release_functional(self, mock_subp):
        output = '\n'.join([
            "Distributor ID: Ubuntu",
            "Description:    Ubuntu 14.04.2 LTS",
            "Release:    14.04",
            "Codename:   trusty",
        ])
        rdata = {'id': 'Ubuntu', 'description': 'Ubuntu 14.04.2 LTS',
                 'codename': 'trusty', 'release': '14.04'}

        def fake_subp(cmd, capture=False, target=None):
            return output, 'No LSB modules are available.'

        mock_subp.side_effect = fake_subp
        found = util.lsb_release()
        mock_subp.assert_called_with(
            ['lsb_release', '--all'], capture=True, target=None)
        self.assertEqual(found, rdata)

    @mock.patch("curtin.util.subp")
    def test_lsb_release_unavailable(self, mock_subp):
        def doraise(*args, **kwargs):
            raise util.ProcessExecutionError("foo")
        mock_subp.side_effect = doraise

        expected = {k: "UNAVAILABLE" for k in
                    ('id', 'description', 'codename', 'release')}
        self.assertEqual(util.lsb_release(), expected)


class TestSubp(TestCase):

    stdin2err = ['bash', '-c', 'cat >&2']
    stdin2out = ['cat']
    bin_true = ['bash', '-c', ':']
    exit_with_value = ['bash', '-c', 'exit ${1:-0}', 'test_subp_exit_val']
    utf8_invalid = b'ab\xaadef'
    utf8_valid = b'start \xc3\xa9 end'
    utf8_valid_2 = b'd\xc3\xa9j\xc8\xa7'

    try:
        decode_type = unicode
        nodecode_type = str
    except NameError:
        decode_type = str
        nodecode_type = bytes

    def printf_cmd(self, *args):
        # bash's printf supports \xaa.  So does /usr/bin/printf
        # but by using bash, we remove dependency on another program.
        return(['bash', '-c', 'printf "$@"', 'printf'] + list(args))

    def test_subp_handles_utf8(self):
        # The given bytes contain utf-8 accented characters as seen in e.g.
        # the "deja dup" package in Ubuntu.
        cmd = self.printf_cmd(self.utf8_valid_2)
        (out, _err) = util.subp(cmd, capture=True)
        self.assertEqual(out, self.utf8_valid_2.decode('utf-8'))

    def test_subp_target_as_different_forms_of_slash_works(self):
        # passing target=/ in any form should work.

        # it is assumed that if chroot was used, then test case would
        # fail unless user was root ('chroot /' is still priviledged)
        util.subp(self.bin_true, target="/")
        util.subp(self.bin_true, target="//")
        util.subp(self.bin_true, target="///")
        util.subp(self.bin_true, target="//etc/..//")

    def test_subp_exit_nonzero_raises(self):
        exc = None
        try:
            util.subp(self.exit_with_value + ["9"])
        except util.ProcessExecutionError as e:
            self.assertEqual(9, e.exit_code)
            exc = e

        self.assertNotEqual(exc, None)

    def test_rcs_not_in_list_raise(self):
        exc = None
        try:
            util.subp(self.exit_with_value + ["9"], rcs=["8", "0"])
        except util.ProcessExecutionError as e:
            self.assertEqual(9, e.exit_code)
            exc = e
        self.assertNotEqual(exc, None)

    def test_rcs_other_than_zero_work(self):
        _out, _err = util.subp(self.exit_with_value + ["9"], rcs=[9])

    def test_subp_respects_decode_false(self):
        (out, err) = util.subp(self.stdin2out, capture=True, decode=False,
                               data=self.utf8_valid)
        self.assertTrue(isinstance(out, self.nodecode_type))
        self.assertTrue(isinstance(err, self.nodecode_type))
        self.assertEqual(out, self.utf8_valid)

    def test_subp_decode_ignore(self):
        # this executes a string that writes invalid utf-8 to stdout
        (out, err) = util.subp(self.printf_cmd('abc\\xaadef'),
                               capture=True, decode='ignore')
        self.assertTrue(isinstance(out, self.decode_type))
        self.assertTrue(isinstance(err, self.decode_type))
        self.assertEqual(out, 'abcdef')

    def test_subp_decode_strict_valid_utf8(self):
        (out, err) = util.subp(self.stdin2out, capture=True,
                               decode='strict', data=self.utf8_valid)
        self.assertEqual(out, self.utf8_valid.decode('utf-8'))
        self.assertTrue(isinstance(out, self.decode_type))
        self.assertTrue(isinstance(err, self.decode_type))

    def test_subp_decode_invalid_utf8_replaces(self):
        (out, err) = util.subp(self.stdin2out, capture=True,
                               data=self.utf8_invalid)
        expected = self.utf8_invalid.decode('utf-8', errors='replace')
        self.assertTrue(isinstance(out, self.decode_type))
        self.assertTrue(isinstance(err, self.decode_type))
        self.assertEqual(out, expected)

    def test_subp_decode_strict_raises(self):
        args = []
        kwargs = {'args': self.stdin2out, 'capture': True,
                  'decode': 'strict', 'data': self.utf8_invalid}
        self.assertRaises(UnicodeDecodeError, util.subp, *args, **kwargs)

    def test_subp_capture_stderr(self):
        data = b'hello world'
        (out, err) = util.subp(self.stdin2err, capture=True,
                               decode=False, data=data)
        self.assertEqual(err, data)
        self.assertEqual(out, b'')

    def test_returns_none_if_no_capture(self):
        (out, err) = util.subp(self.stdin2out, data=b'')
        self.assertEqual(err, None)
        self.assertEqual(out, None)

    def _subp_wrap_popen(self, cmd, kwargs,
                         stdout=b'', stderr=b'', returncodes=None):
        # mocks the subprocess.Popen as expected from subp
        # checks that subp returned the output of 'communicate' and
        # returns the (args, kwargs) that Popen() was called with.
        # returncodes is a list to cover, one for each expected call

        if returncodes is None:
            returncodes = [0]

        capture = kwargs.get('capture')

        mreturncodes = mock.PropertyMock(side_effect=iter(returncodes))
        with mock.patch("curtin.util.subprocess.Popen") as m_popen:
            sp = mock.Mock()
            m_popen.return_value = sp
            if capture:
                sp.communicate.return_value = (stdout, stderr)
            else:
                sp.communicate.return_value = (None, None)
            type(sp).returncode = mreturncodes
            ret = util.subp(cmd, **kwargs)

        # popen may be called once or > 1 for retries, but must be called.
        self.assertTrue(m_popen.called)
        # communicate() needs to have been called.
        self.assertTrue(sp.communicate.called)

        if capture:
            # capture response is decoded if decode is not False
            decode = kwargs.get('decode', "replace")
            if decode is False:
                self.assertEqual(stdout.decode(stdout, stderr), ret)
            else:
                self.assertEqual((stdout.decode(errors=decode),
                                  stderr.decode(errors=decode)), ret)
        else:
            # if capture is false, then return is None, None
            self.assertEqual((None, None), ret)

        # if target is not provided or is /, chroot should not be used
        calls = m_popen.call_args_list
        popen_args, popen_kwargs = calls[-1]
        target = util.target_path(kwargs.get('target', None))
        if target == "/":
            self.assertEqual(cmd, popen_args[0])
        else:
            self.assertEqual(['chroot', target] + list(cmd), popen_args[0])
        return calls

    def test_with_target_gets_chroot(self):
        args, kwargs = self._subp_wrap_popen(["my-command"],
                                             {'target': "/mytarget"})[0]
        self.assertIn('chroot', args[0])

    def test_with_target_as_slash_does_not_chroot(self):
        args, kwargs = self._subp_wrap_popen(
            ['whatever'], {'capture': True, 'target': "/"})[0]
        self.assertNotIn('chroot', args[0])

    def test_with_no_target_does_not_chroot(self):
        r = self._subp_wrap_popen(['whatever'], {'capture': True})
        args, kwargs = r[0]
        # note this path is reasonably tested with all of the above
        # tests that do not mock Popen as if we did try to chroot the
        # unit tests would fail unless they were run as root.
        self.assertNotIn('chroot', args[0])

    def test_retry_none_does_not_retry(self):
        rcfail = 7
        try:
            self._subp_wrap_popen(
                ['succeeds-second-time'], {'capture': True, 'retries': None},
                returncodes=[rcfail, 0])
            raise Exception("did not raise a ProcessExecutionError!")
        except util.ProcessExecutionError as e:
            self.assertEqual(e.exit_code, rcfail)

    def test_retry_does_retry(self):
        # test subp with retries does retry
        rcs = [7, 8, 9, 0]
        # these are our very short sleeps
        retries = [0] * len(rcs)
        r = self._subp_wrap_popen(
            ['succeeds-eventually'], {'capture': True, 'retries': retries},
            returncodes=rcs)
        # r is a list of all args, kwargs to Popen that happend.
        # since we fail a few times, it needs to have been called again.
        self.assertEqual(len(r), len(rcs))


class TestHuman2Bytes(TestCase):
    GB = 1024 * 1024 * 1024
    MB = 1024 * 1024

    def test_float_equal_int_is_allowed(self):
        self.assertEqual(1000, util.human2bytes(1000.0))

    def test_float_in_string_nonequal_int_raises_type_error(self):
        self.assertRaises(ValueError, util.human2bytes, "1000.4B")

    def test_float_nonequal_int_raises_type_error(self):
        self.assertRaises(ValueError, util.human2bytes, 1000.4)

    def test_int_gets_int(self):
        self.assertEqual(100, util.human2bytes(100))

    def test_no_suffix_is_bytes(self):
        self.assertEqual(100, util.human2bytes("100"))

    def test_suffix_M(self):
        self.assertEqual(100 * self.MB, util.human2bytes("100M"))

    def test_suffix_B(self):
        self.assertEqual(100, util.human2bytes("100B"))

    def test_suffix_G(self):
        self.assertEqual(int(10 * self.GB), util.human2bytes("10G"))

    def test_float_in_string(self):
        self.assertEqual(int(3.5 * self.GB), util.human2bytes("3.5G"))

    def test_GB_equals_G(self):
        self.assertEqual(util.human2bytes("3GB"), util.human2bytes("3G"))

    def test_b2h_errors(self):
        self.assertRaises(ValueError, util.bytes2human, 10.4)
        self.assertRaises(ValueError, util.bytes2human, 'notint')
        self.assertRaises(ValueError, util.bytes2human, -1)
        self.assertRaises(ValueError, util.bytes2human, -1.0)

    def test_b2h_values(self):
        self.assertEqual('10G', util.bytes2human(10 * self.GB))
        self.assertEqual('10M', util.bytes2human(10 * self.MB))
        self.assertEqual('1000B', util.bytes2human(1000))
        self.assertEqual('1K', util.bytes2human(1024))
        self.assertEqual('1K', util.bytes2human(1024.0))
        self.assertEqual('1T', util.bytes2human(float(1024 * self.GB)))

    def test_h2b_b2b(self):
        for size_str in ['10G', '20G', '2T', '12K', '1M', '1023K']:
            self.assertEqual(
                util.bytes2human(util.human2bytes(size_str)), size_str)


class TestSetUnExecutable(TestCase):
    tmpf = None
    tmpd = None

    def tearDown(self):
        if self.tmpf:
            if os.path.exists(self.tmpf):
                os.unlink(self.tmpf)
            self.tmpf = None
        if self.tmpd:
            shutil.rmtree(self.tmpd)
            self.tmpd = None

    def tempfile(self, data=None):
        fp, self.tmpf = tempfile.mkstemp()
        if data:
            fp.write(data)
        os.close(fp)
        return self.tmpf

    def test_change_needed_returns_original_mode(self):
        tmpf = self.tempfile()
        os.chmod(tmpf, 0o755)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, 0o0755)

    def test_no_change_needed_returns_none(self):
        tmpf = self.tempfile()
        os.chmod(tmpf, 0o600)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, None)

    def test_change_does_as_expected(self):
        tmpf = self.tempfile()
        os.chmod(tmpf, 0o755)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, 0o0755)
        self.assertEqual(stat.S_IMODE(os.stat(tmpf).st_mode), 0o0644)

    def test_strict_no_exists_raises_exception(self):
        self.tmpd = tempfile.mkdtemp()
        bogus = os.path.join(self.tmpd, 'bogus')
        self.assertRaises(ValueError, util.set_unexecutable, bogus, True)


class TestTargetPath(TestCase):
    def test_target_empty_string(self):
        self.assertEqual("/etc/passwd", util.target_path("", "/etc/passwd"))

    def test_target_non_string_raises(self):
        self.assertRaises(ValueError, util.target_path, False)
        self.assertRaises(ValueError, util.target_path, 9)
        self.assertRaises(ValueError, util.target_path, True)

    def test_lots_of_slashes_is_slash(self):
        self.assertEqual("/", util.target_path("/"))
        self.assertEqual("/", util.target_path("//"))
        self.assertEqual("/", util.target_path("///"))
        self.assertEqual("/", util.target_path("////"))

    def test_empty_string_is_slash(self):
        self.assertEqual("/", util.target_path(""))

    def test_recognizes_relative(self):
        self.assertEqual("/", util.target_path("/foo/../"))
        self.assertEqual("/", util.target_path("/foo//bar/../../"))

    def test_no_path(self):
        self.assertEqual("/my/target", util.target_path("/my/target"))

    def test_no_target_no_path(self):
        self.assertEqual("/", util.target_path(None))

    def test_no_target_with_path(self):
        self.assertEqual("/my/path", util.target_path(None, "/my/path"))

    def test_trailing_slash(self):
        self.assertEqual("/my/target/my/path",
                         util.target_path("/my/target/", "/my/path"))

    def test_bunch_of_slashes_in_path(self):
        self.assertEqual("/target/my/path/",
                         util.target_path("/target/", "//my/path/"))
        self.assertEqual("/target/my/path/",
                         util.target_path("/target/", "///my/path/"))


class TestRunInChroot(TestCase):
    """Test the legacy 'RunInChroot'.

    The test works by mocking ChrootableTarget's __enter__ to do nothing.
    The assumptions made are:
      a.) RunInChroot is a subclass of ChrootableTarget
      b.) ChrootableTarget's __exit__ only un-does work that its __enter__
          did.  Meaning for our mocked case, it does nothing."""

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    def test_run_in_chroot_with_target_slash(self):
        with util.RunInChroot("/") as i:
            out, err = i(['echo', 'HI MOM'], capture=True)
        self.assertEqual('HI MOM\n', out)

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch("curtin.util.subp")
    def test_run_in_chroot_with_target(self, m_subp):
        my_stdout = "my output"
        my_stderr = "my stderr"
        cmd = ['echo', 'HI MOM']
        target = "/foo"
        m_subp.return_value = (my_stdout, my_stderr)
        with util.RunInChroot(target) as i:
            out, err = i(cmd)
        self.assertEqual(my_stdout, out)
        self.assertEqual(my_stderr, err)
        m_subp.assert_called_with(cmd, target=target)


class TestLoadFile(TestCase):
    """Test utility 'load_file'"""

    def test_load_file_simple(self):
        fname = 'test.cfg'
        contents = "#curtin-config"
        with simple_mocked_open(content=contents) as m_open:
            loaded_contents = util.load_file(fname, decode=False)
            self.assertEqual(contents, loaded_contents)
            m_open.assert_called_with(fname, 'rb')

    @skipIf(mock.__version__ < '2.0.0', "mock version < 2.0.0")
    def test_load_file_handles_utf8(self):
        fname = 'test.cfg'
        contents = b'd\xc3\xa9j\xc8\xa7'
        with simple_mocked_open(content=contents) as m_open:
            with open(fname, 'rb') as f:
                self.assertEqual(f.read(), contents)
            m_open.assert_called_with(fname, 'rb')

    @skipIf(mock.__version__ < '2.0.0', "mock version < 2.0.0")
    @mock.patch('curtin.util.decode_binary')
    def test_load_file_respects_decode_false(self, mock_decode):
        fname = 'test.cfg'
        contents = b'start \xc3\xa9 end'
        with simple_mocked_open(contents):
            loaded_contents = util.load_file(fname, decode=False)
            self.assertEqual(type(loaded_contents), bytes)
            self.assertEqual(loaded_contents, contents)


class TestIpAddress(TestCase):
    """Test utility 'is_valid_ip{,v4,v6}_address'"""

    def test_is_valid_ipv6_address(self):
        self.assertFalse(util.is_valid_ipv6_address('192.168'))
        self.assertFalse(util.is_valid_ipv6_address('69.89.31.226'))
        self.assertFalse(util.is_valid_ipv6_address('254.254.254.254'))
        self.assertTrue(util.is_valid_ipv6_address('2001:db8::1'))
        self.assertTrue(util.is_valid_ipv6_address('::1'))
        self.assertTrue(util.is_valid_ipv6_address(
            '1200:0000:AB00:1234:0000:2552:7777:1313'))
        self.assertFalse(util.is_valid_ipv6_address(
            '1200::AB00:1234::2552:7777:1313'))
        self.assertTrue(util.is_valid_ipv6_address(
            '21DA:D3:0:2F3B:2AA:FF:FE28:9C5A'))
        self.assertFalse(util.is_valid_ipv6_address(
            '1200:0000:AB00:1234:O000:2552:7777:1313'))
        self.assertTrue(util.is_valid_ipv6_address(
            '2002:4559:1FE2::4559:1FE2'))
        self.assertTrue(util.is_valid_ipv6_address(
            '2002:4559:1fe2:0:0:0:4559:1fe2'))
        self.assertTrue(util.is_valid_ipv6_address(
            '2002:4559:1FE2:0000:0000:0000:4559:1FE2'))


class TestLoadCommandEnvironment(TestCase):
    def setUp(self):
        self.tmpd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpd)
        all_names = {
            'CONFIG',
            'OUTPUT_FSTAB',
            'OUTPUT_INTERFACES',
            'OUTPUT_NETWORK_CONFIG',
            'OUTPUT_NETWORK_STATE',
            'CURTIN_REPORTSTACK',
            'WORKING_DIR',
            'TARGET_MOUNT_POINT',
        }
        self.full_env = {v: os.path.join(self.tmpd, v.lower())
                         for v in all_names}

    def test_strict_with_missing(self):
        my_env = self.full_env.copy()
        del my_env['OUTPUT_FSTAB']
        del my_env['WORKING_DIR']
        exc = None
        try:
            util.load_command_environment(my_env, strict=True)
        except KeyError as e:
            self.assertIn("OUTPUT_FSTAB", str(e))
            self.assertIn("WORKING_DIR", str(e))
            exc = e

        self.assertTrue(exc)

    def test_nostrict_with_missing(self):
        my_env = self.full_env.copy()
        del my_env['OUTPUT_FSTAB']
        try:
            util.load_command_environment(my_env, strict=False)
        except KeyError as e:
            self.fail("unexpected key error raised: %s" % e)

    def test_full_and_strict(self):
        try:
            util.load_command_environment(self.full_env, strict=False)
        except KeyError as e:
            self.fail("unexpected key error raised: %s" % e)


class TestWaitForRemoval(TestCase):
    def test_wait_for_removal_missing_path(self):
        with self.assertRaises(ValueError):
            util.wait_for_removal(None)

    @mock.patch('curtin.util.time')
    @mock.patch('curtin.util.os')
    def test_wait_for_removal(self, mock_os, mock_time):
        path = "/file/to/remove"
        mock_os.path.exists.side_effect = iter([
            True,    # File is not yet removed
            False,   # File has  been removed
        ])

        util.wait_for_removal(path)

        self.assertEqual(2, len(mock_os.path.exists.call_args_list))
        self.assertEqual(1, len(mock_time.sleep.call_args_list))
        mock_os.path.exists.assert_has_calls([
            mock.call(path),
            mock.call(path),
        ])
        mock_time.sleep.assert_has_calls([
            mock.call(1),
        ])

    @mock.patch('curtin.util.time')
    @mock.patch('curtin.util.os')
    def test_wait_for_removal_timesout(self, mock_os, mock_time):
        path = "/file/to/remove"
        mock_os.path.exists.return_value = True

        with self.assertRaises(OSError):
            util.wait_for_removal(path)

        self.assertEqual(5, len(mock_os.path.exists.call_args_list))
        self.assertEqual(4, len(mock_time.sleep.call_args_list))
        mock_os.path.exists.assert_has_calls(5 * [mock.call(path)])
        mock_time.sleep.assert_has_calls([
            mock.call(1),
            mock.call(3),
            mock.call(5),
            mock.call(7),
        ])

    @mock.patch('curtin.util.time')
    @mock.patch('curtin.util.os')
    def test_wait_for_removal_custom_retry(self, mock_os, mock_time):
        path = "/file/to/remove"
        timeout = 100
        mock_os.path.exists.side_effect = iter([
            True,    # File is not yet removed
            False,   # File has  been removed
        ])

        util.wait_for_removal(path, retries=[timeout])

        self.assertEqual(2, len(mock_os.path.exists.call_args_list))
        self.assertEqual(1, len(mock_time.sleep.call_args_list))
        mock_os.path.exists.assert_has_calls([
            mock.call(path),
            mock.call(path),
        ])
        mock_time.sleep.assert_has_calls([
            mock.call(timeout),
        ])


# vi: ts=4 expandtab syntax=python
