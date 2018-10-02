# This file is part of curtin. See LICENSE file for copyright and license info.

from unittest import skipIf
import mock
import os
import stat
from textwrap import dedent

from curtin import util
from curtin import paths
from .helpers import CiTestCase, simple_mocked_open


class TestLogTimer(CiTestCase):
    def test_logger_called(self):
        data = {}

        def mylog(msg):
            data['msg'] = msg

        with util.LogTimer(mylog, "mymessage"):
            pass

        self.assertIn("msg", data)
        self.assertIn("mymessage", data['msg'])


class TestDisableDaemons(CiTestCase):
    prcpath = "usr/sbin/policy-rc.d"

    def setUp(self):
        super(TestDisableDaemons, self).setUp()
        self.target = self.tmp_dir()
        self.temp_prc = os.path.join(self.target, self.prcpath)

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


class TestWhich(CiTestCase):

    def setUp(self):
        super(TestWhich, self).setUp()
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


class TestSubp(CiTestCase):

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

    def setUp(self):
        super(TestSubp, self).setUp()
        self.add_patch(
            'curtin.util._get_unshare_pid_args', 'mock_get_unshare_pid_args',
            return_value=[])

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

    def test_subp_combined_stderr_stdout(self):
        """Providing combine_capture as True redirects stderr to stdout."""
        data = b'hello world'
        (out, err) = util.subp(self.stdin2err, combine_capture=True,
                               decode=False, data=data)
        self.assertEqual(err, b'')
        self.assertEqual(out, data)

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
        target = paths.target_path(kwargs.get('target', None))
        unshcmd = self.mock_get_unshare_pid_args.return_value
        if target == "/":
            self.assertEqual(unshcmd + list(cmd), popen_args[0])
        else:
            self.assertEqual(unshcmd + ['chroot', target] + list(cmd),
                             popen_args[0])
        return calls

    def test_args_can_be_a_tuple(self):
        """subp can take a tuple for cmd rather than a list."""
        my_cmd = tuple(['echo', 'hi', 'mom'])
        calls = self._subp_wrap_popen(my_cmd, {})
        args, kwargs = calls[0]
        # subp was called with cmd as a tuple.  That may get converted to
        # a list before subprocess.popen.  So only compare as lists.
        self.assertEqual(1, len(calls))
        self.assertEqual(list(my_cmd), list(args[0]))

    def test_args_can_be_a_string(self):
        """subp("cat") is acceptable, as suprocess.call("cat") works fine."""
        out, err = util.subp("cat", data=b'hi mom', capture=True, decode=False)
        self.assertEqual(b'hi mom', out)

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

    def test_unshare_pid_return_is_used(self):
        """The return of _get_unshare_pid_return needs to be in command."""
        my_unshare_cmd = ['do-unshare-command', 'arg0', 'arg1', '--']
        self.mock_get_unshare_pid_args.return_value = my_unshare_cmd
        my_kwargs = {'target': '/target', 'unshare_pid': True}
        r = self._subp_wrap_popen(['apt-get', 'install'], my_kwargs)
        self.assertEqual(1, len(r))
        args, kwargs = r[0]
        self.assertEqual(
            [mock.call(my_kwargs['unshare_pid'], my_kwargs['target'])],
            self.mock_get_unshare_pid_args.call_args_list)
        expected = (my_unshare_cmd + ['chroot', '/target'] +
                    ['apt-get', 'install'])
        self.assertEqual(expected, args[0])


class TestGetUnsharePidArgs(CiTestCase):
    """Test the internal implementation for when to unshare."""

    def setUp(self):
        super(TestGetUnsharePidArgs, self).setUp()
        self.add_patch('curtin.util._has_unshare_pid', 'mock_has_unshare_pid',
                       return_value=True)
        # our trusty tox environment with mock 1.0.1 will stack trace
        # if autospec is not disabled here.
        self.add_patch('curtin.util.os.geteuid', 'mock_geteuid',
                       autospec=False, return_value=0)

    def assertOff(self, result):
        self.assertEqual([], result)

    def assertOn(self, result):
        self.assertEqual(['unshare', '--fork', '--pid', '--'], result)

    def test_unshare_pid_none_and_not_root_means_off(self):
        """If not root, then expect off."""
        self.assertOff(util._get_unshare_pid_args(None, "/foo", 500))
        self.assertOff(util._get_unshare_pid_args(None, "/", 500))

        self.mock_geteuid.return_value = 500
        self.assertOff(util._get_unshare_pid_args(None, "/"))
        self.assertOff(
            util._get_unshare_pid_args(unshare_pid=None, target="/foo"))

    def test_unshare_pid_none_and_no_unshare_pid_means_off(self):
        """No unshare support and unshare_pid is None means off."""
        self.mock_has_unshare_pid.return_value = False
        self.assertOff(util._get_unshare_pid_args(None, "/target", 0))

    def test_unshare_pid_true_and_no_unshare_pid_raises(self):
        """Passing unshare_pid in as True and no command should raise."""
        self.mock_has_unshare_pid.return_value = False
        expected_msg = 'no unshare command'
        with self.assertRaisesRegexp(RuntimeError, expected_msg):
            util._get_unshare_pid_args(True)

        with self.assertRaisesRegexp(RuntimeError, expected_msg):
            util._get_unshare_pid_args(True, "/foo", 0)

    def test_unshare_pid_true_and_not_root_raises(self):
        """When unshare_pid is True for non-root an error is raised."""
        expected_msg = 'euid.* != 0'
        with self.assertRaisesRegexp(RuntimeError, expected_msg):
            util._get_unshare_pid_args(True, "/foo", 500)

        self.mock_geteuid.return_value = 500
        with self.assertRaisesRegexp(RuntimeError, expected_msg):
            util._get_unshare_pid_args(True)

    def test_euid0_target_not_slash(self):
        """If root and target is not /, then expect on."""
        self.assertOn(util._get_unshare_pid_args(None, target="/foo", euid=0))

    def test_euid0_target_slash(self):
        """If root and target is /, then expect off."""
        self.assertOff(util._get_unshare_pid_args(None, "/", 0))
        self.assertOff(util._get_unshare_pid_args(None, target=None, euid=0))

    def test_unshare_pid_of_false_means_off(self):
        """Any unshare_pid value false-ish other than None means no unshare."""
        self.assertOff(
            util._get_unshare_pid_args(unshare_pid=False, target=None))
        self.assertOff(util._get_unshare_pid_args(False, "/target", 1))
        self.assertOff(util._get_unshare_pid_args(False, "/", 0))
        self.assertOff(util._get_unshare_pid_args("", "/target", 0))


class TestHuman2Bytes(CiTestCase):
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


class TestSetUnExecutable(CiTestCase):
    tmpf = None
    tmpd = None

    def setUp(self):
        super(CiTestCase, self).setUp()
        self.tmpd = self.tmp_dir()

    def test_change_needed_returns_original_mode(self):
        tmpf = self.tmp_path('testfile')
        util.write_file(tmpf, '')
        os.chmod(tmpf, 0o755)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, 0o0755)

    def test_no_change_needed_returns_none(self):
        tmpf = self.tmp_path('testfile')
        util.write_file(tmpf, '')
        os.chmod(tmpf, 0o600)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, None)

    def test_change_does_as_expected(self):
        tmpf = self.tmp_path('testfile')
        util.write_file(tmpf, '')
        os.chmod(tmpf, 0o755)
        ret = util.set_unexecutable(tmpf)
        self.assertEqual(ret, 0o0755)
        self.assertEqual(stat.S_IMODE(os.stat(tmpf).st_mode), 0o0644)

    def test_strict_no_exists_raises_exception(self):
        bogus = os.path.join(self.tmpd, 'bogus')
        self.assertRaises(ValueError, util.set_unexecutable, bogus, True)


class TestTargetPath(CiTestCase):
    def test_target_empty_string(self):
        self.assertEqual("/etc/passwd", paths.target_path("", "/etc/passwd"))

    def test_target_non_string_raises(self):
        self.assertRaises(ValueError, paths.target_path, False)
        self.assertRaises(ValueError, paths.target_path, 9)
        self.assertRaises(ValueError, paths.target_path, True)

    def test_lots_of_slashes_is_slash(self):
        self.assertEqual("/", paths.target_path("/"))
        self.assertEqual("/", paths.target_path("//"))
        self.assertEqual("/", paths.target_path("///"))
        self.assertEqual("/", paths.target_path("////"))

    def test_empty_string_is_slash(self):
        self.assertEqual("/", paths.target_path(""))

    def test_recognizes_relative(self):
        self.assertEqual("/", paths.target_path("/foo/../"))
        self.assertEqual("/", paths.target_path("/foo//bar/../../"))

    def test_no_path(self):
        self.assertEqual("/my/target", paths.target_path("/my/target"))

    def test_no_target_no_path(self):
        self.assertEqual("/", paths.target_path(None))

    def test_no_target_with_path(self):
        self.assertEqual("/my/path", paths.target_path(None, "/my/path"))

    def test_trailing_slash(self):
        self.assertEqual("/my/target/my/path",
                         paths.target_path("/my/target/", "/my/path"))

    def test_bunch_of_slashes_in_path(self):
        self.assertEqual("/target/my/path/",
                         paths.target_path("/target/", "//my/path/"))
        self.assertEqual("/target/my/path/",
                         paths.target_path("/target/", "///my/path/"))


class TestRunInChroot(CiTestCase):
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


class TestLoadFile(CiTestCase):
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


class TestIpAddress(CiTestCase):
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


class TestLoadCommandEnvironment(CiTestCase):

    def setUp(self):
        super(TestLoadCommandEnvironment, self).setUp()
        self.tmpd = self.tmp_dir()
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


class TestWaitForRemoval(CiTestCase):
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


class TestGetEFIBootMGR(CiTestCase):

    def setUp(self):
        super(TestGetEFIBootMGR, self).setUp()
        self.add_patch(
            'curtin.util.ChrootableTarget', 'mock_chroot', autospec=False)
        self.mock_in_chroot = mock.MagicMock()
        self.mock_in_chroot.__enter__.return_value = self.mock_in_chroot
        self.in_chroot_subp_output = []
        self.mock_in_chroot_subp = self.mock_in_chroot.subp
        self.mock_in_chroot_subp.side_effect = self.in_chroot_subp_output
        self.mock_chroot.return_value = self.mock_in_chroot

    def test_calls_efibootmgr_verbose(self):
        self.in_chroot_subp_output.append(('', ''))
        util.get_efibootmgr('target')
        self.assertEquals(
            (['efibootmgr', '-v'],),
            self.mock_in_chroot_subp.call_args_list[0][0])

    def test_parses_output(self):
        self.in_chroot_subp_output.append((dedent(
            """\
            BootCurrent: 0000
            Timeout: 1 seconds
            BootOrder: 0000,0002,0001,0003,0004,0005
            Boot0000* ubuntu	HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)
            Boot0001* CD/DVD Drive 	BBS(CDROM,,0x0)
            Boot0002* Hard Drive 	BBS(HD,,0x0)
            Boot0003* UEFI:CD/DVD Drive	BBS(129,,0x0)
            Boot0004* UEFI:Removable Device	BBS(130,,0x0)
            Boot0005* UEFI:Network Device	BBS(131,,0x0)
            """), ''))
        observed = util.get_efibootmgr('target')
        self.assertEquals({
            'current': '0000',
            'timeout': '1 seconds',
            'order': ['0000', '0002', '0001', '0003', '0004', '0005'],
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': 'HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)',
                },
                '0001': {
                    'name': 'CD/DVD Drive',
                    'path': 'BBS(CDROM,,0x0)',
                },
                '0002': {
                    'name': 'Hard Drive',
                    'path': 'BBS(HD,,0x0)',
                },
                '0003': {
                    'name': 'UEFI:CD/DVD Drive',
                    'path': 'BBS(129,,0x0)',
                },
                '0004': {
                    'name': 'UEFI:Removable Device',
                    'path': 'BBS(130,,0x0)',
                },
                '0005': {
                    'name': 'UEFI:Network Device',
                    'path': 'BBS(131,,0x0)',
                },
            }
        }, observed)

    def test_parses_output_filter_missing(self):
        """ensure parsing ignores items in order that don't have entries"""
        self.in_chroot_subp_output.append((dedent(
            """\
            BootCurrent: 0000
            Timeout: 1 seconds
            BootOrder: 0000,0002,0001,0003,0004,0005,0006,0007
            Boot0000* ubuntu	HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)
            Boot0001* CD/DVD Drive 	BBS(CDROM,,0x0)
            Boot0002* Hard Drive 	BBS(HD,,0x0)
            Boot0003* UEFI:CD/DVD Drive	BBS(129,,0x0)
            Boot0004* UEFI:Removable Device	BBS(130,,0x0)
            Boot0005* UEFI:Network Device	BBS(131,,0x0)
            """), ''))
        observed = util.get_efibootmgr('target')
        self.assertEquals({
            'current': '0000',
            'timeout': '1 seconds',
            'order': ['0000', '0002', '0001', '0003', '0004', '0005'],
            'entries': {
                '0000': {
                    'name': 'ubuntu',
                    'path': 'HD(1,GPT)/File(\\EFI\\ubuntu\\shimx64.efi)',
                },
                '0001': {
                    'name': 'CD/DVD Drive',
                    'path': 'BBS(CDROM,,0x0)',
                },
                '0002': {
                    'name': 'Hard Drive',
                    'path': 'BBS(HD,,0x0)',
                },
                '0003': {
                    'name': 'UEFI:CD/DVD Drive',
                    'path': 'BBS(129,,0x0)',
                },
                '0004': {
                    'name': 'UEFI:Removable Device',
                    'path': 'BBS(130,,0x0)',
                },
                '0005': {
                    'name': 'UEFI:Network Device',
                    'path': 'BBS(131,,0x0)',
                },
            }
        }, observed)


class TestUsesSystemd(CiTestCase):

    def setUp(self):
        super(TestUsesSystemd, self).setUp()
        self._reset_cache()
        self.add_patch('curtin.util.os.path.isdir', 'mock_isdir')

    def _reset_cache(self):
        util._USES_SYSTEMD = None

    def test_uses_systemd_on_systemd(self):
        """ Test that uses_systemd returns True if sdpath is a dir """
        # systemd_enabled
        self.mock_isdir.return_value = True
        result = util.uses_systemd()
        self.assertEqual(True, result)
        self.assertEqual(1, len(self.mock_isdir.call_args_list))

    def test_uses_systemd_cached(self):
        """Test that we cache the uses_systemd result"""

        # reset_cache should ensure it's unset
        self.assertEqual(None, util._USES_SYSTEMD)

        # systemd enabled
        self.mock_isdir.return_value = True

        # first time
        first_result = util.uses_systemd()

        # check the cache value
        self.assertEqual(first_result, util._USES_SYSTEMD)

        # second time
        second_result = util.uses_systemd()

        # results should match between tries
        self.assertEqual(True, first_result)
        self.assertEqual(True, second_result)

        # isdir should only be called once
        self.assertEqual(1, len(self.mock_isdir.call_args_list))

    def test_uses_systemd_on_non_systemd(self):
        """ Test that uses_systemd returns False if sdpath is not a dir """
        # systemd not available
        self.mock_isdir.return_value = False
        result = util.uses_systemd()
        self.assertEqual(False, result)


class TestIsKmodLoaded(CiTestCase):

    def setUp(self):
        super(TestIsKmodLoaded, self).setUp()
        self.add_patch('curtin.util.os.path.isdir', 'm_path_isdir')
        self.modname = 'fake_module'

    def test_is_kmod_loaded_invalid_module(self):
        """test raise ValueError on invalid module parameter"""
        for module_name in ['', None]:
            with self.assertRaises(ValueError):
                util.is_kmod_loaded(module_name)

    def test_is_kmod_loaded_path_checked(self):
        """ test /sys/modules/<modname> path is checked """
        util.is_kmod_loaded(self.modname)
        self.m_path_isdir.assert_called_with('/sys/module/%s' % self.modname)

    def test_is_kmod_loaded_already_loaded(self):
        """ test returns True if /sys/module/modname exists """
        self.m_path_isdir.return_value = True
        is_loaded = util.is_kmod_loaded(self.modname)
        self.assertTrue(is_loaded)
        self.m_path_isdir.assert_called_with('/sys/module/%s' % self.modname)

    def test_is_kmod_loaded_not_loaded(self):
        """ test returns False if /sys/module/modname does not exist """
        self.m_path_isdir.return_value = False
        is_loaded = util.is_kmod_loaded(self.modname)
        self.assertFalse(is_loaded)
        self.m_path_isdir.assert_called_with('/sys/module/%s' % self.modname)


class TestLoadKernelModule(CiTestCase):

    def setUp(self):
        super(TestLoadKernelModule, self).setUp()
        self.add_patch('curtin.util.is_kmod_loaded', 'm_is_kmod_loaded')
        self.add_patch('curtin.util.subp', 'm_subp')
        self.modname = 'fake_module'

    def test_load_kernel_module_invalid_module(self):
        """ test raise ValueError on invalid module parameter"""
        for module_name in ['', None]:
            with self.assertRaises(ValueError):
                util.load_kernel_module(module_name)

    def test_load_kernel_module_unloaded(self):
        """ test unloaded kmod is loaded via call to modprobe"""
        self.m_is_kmod_loaded.return_value = False

        util.load_kernel_module(self.modname)

        self.m_is_kmod_loaded.assert_called_with(self.modname)
        self.m_subp.assert_called_with(['modprobe', '--use-blacklist',
                                        self.modname])

    def test_load_kernel_module_loaded(self):
        """ test modprobe called with check_loaded=False"""
        self.m_is_kmod_loaded.return_value = True
        util.load_kernel_module(self.modname, check_loaded=False)

        self.assertEqual(0, self.m_is_kmod_loaded.call_count)
        self.m_subp.assert_called_with(['modprobe', '--use-blacklist',
                                        self.modname])

    def test_load_kernel_module_skips_modprobe_if_loaded(self):
        """ test modprobe skipped if module already loaded"""
        self.m_is_kmod_loaded.return_value = True
        util.load_kernel_module(self.modname)

        self.assertEqual(1, self.m_is_kmod_loaded.call_count)
        self.m_is_kmod_loaded.assert_called_with(self.modname)
        self.assertEqual(0, self.m_subp.call_count)


# vi: ts=4 expandtab syntax=python
