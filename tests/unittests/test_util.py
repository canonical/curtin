from unittest import TestCase
import mock
import os
import stat
import shutil
import tempfile

from curtin import util


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

    def test_subp_target_as_different_fors_of_slash_works(self):
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

    def test_subp_respects_decode_false(self):
        (out, err) = util.subp(self.stdin2out, capture=True, decode=False,
                               data=self.utf8_valid)
        self.assertTrue(isinstance(out, bytes))
        self.assertTrue(isinstance(err, bytes))
        self.assertEqual(out, self.utf8_valid)

    def test_subp_decode_ignore(self):
        # this executes a string that writes invalid utf-8 to stdout
        (out, _err) = util.subp(self.printf_cmd('abc\\xaadef'),
                                capture=True, decode='ignore')
        self.assertEqual(out, 'abcdef')

    def test_subp_decode_strict_valid_utf8(self):
        (out, _err) = util.subp(self.stdin2out, capture=True,
                                decode='strict', data=self.utf8_valid)
        self.assertEqual(out, self.utf8_valid.decode('utf-8'))

    def test_subp_decode_invalid_utf8_replaces(self):
        (out, _err) = util.subp(self.stdin2out, capture=True,
                                data=self.utf8_invalid)
        expected = self.utf8_invalid.decode('utf-8', errors='replace')
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
                         returncode=0, stdout=b'', stderr=b''):
        # mocks the subprocess.Popen as expected from subp
        # checks that subp returned the output of 'communicate' and
        # returns the (args, kwargs) that Popen() was called with.

        capture = kwargs.get('capture')

        with mock.patch("curtin.util.subprocess.Popen") as m_popen:
            sp = mock.Mock()
            m_popen.return_value = sp
            if capture:
                sp.communicate.return_value = (stdout, stderr)
            else:
                sp.communicate.return_value = (None, None)
            sp.returncode = returncode
            ret = util.subp(cmd, **kwargs)

        # popen should only ever be called once
        self.assertTrue(m_popen.called)
        self.assertEqual(1, m_popen.call_count)
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

        popen_args, popen_kwargs = m_popen.call_args

        # if target is not provided or is /, chroot should not be used
        target = util.target_path(kwargs.get('target', None))
        if target == "/":
            self.assertEqual(cmd, popen_args[0])
        else:
            self.assertEqual(['chroot', target] + list(cmd), popen_args[0])
        return m_popen.call_args

    def test_with_target_gets_chroot(self):
        args, kwargs = self._subp_wrap_popen(["my-command"],
                                             {'target': "/mytarget"})
        self.assertIn('chroot', args[0])

    def test_with_target_as_slash_does_not_chroot(self):
        args, kwargs = self._subp_wrap_popen(
            ['whatever'], {'capture': True, 'target': "/"})
        self.assertNotIn('chroot', args[0])

    def test_with_no_target_does_not_chroot(self):
        args, kwargs = self._subp_wrap_popen(['whatever'], {'capture': True})
        # note this path is reasonably tested with all of the above
        # tests that do not mock Popen as if we did try to chroot the
        # unit tests would fail unless they were run as root.
        self.assertNotIn('chroot', args[0])


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


# vi: ts=4 expandtab syntax=python
