from unittest import TestCase
import mock
import os
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

        def fake_subp(cmd, capture=False):
            return output, 'No LSB modules are available.'

        mock_subp.side_effect = fake_subp
        found = util.lsb_release()
        mock_subp.assert_called_with(['lsb_release', '--all'], capture=True)
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

    def test_subp_handles_utf8(self):
        # The given bytes contain utf-8 accented characters as seen in e.g.
        # the "deja dup" package in Ubuntu.
        input_bytes = b'd\xc3\xa9j\xc8\xa7'
        cmd = ['echo', '-n', input_bytes]
        (out, _err) = util.subp(cmd, capture=True)
        self.assertEqual(out, input_bytes.decode('utf-8'))

# vi: ts=4 expandtab syntax=python
