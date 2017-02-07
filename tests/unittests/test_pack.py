from unittest import TestCase

from curtin import version
from curtin import util
from curtin.commands.install import INSTALL_PASS_MSG, INSTALL_START_MSG

import json
import os
import shutil
import sys
import tempfile


class TestPack(TestCase):
    """Test code in the output of pack.
       This executes pack, extracts its output, and then runs parts
       of curtin with python to test that it is functional.

       This uses setUpClass to pack so that we can get the most out
       of one of the calls to pack, which is a slow operation for
       a unit test.
    """
    @classmethod
    def setUpClass(cls):
        cls.tmpd = tempfile.mkdtemp(prefix="curtin-%s." % cls.__name__)
        cls.pack_out = os.path.join(cls.tmpd, "pack-out")
        util.subp([sys.executable, '-m', 'curtin.commands.main',
                   'pack', '--output={}'.format(cls.pack_out)])
        os.chmod(cls.pack_out, 0o755)
        util.subp([cls.pack_out, 'extract', '--no-execute'], capture=True,
                  cwd=cls.tmpd)
        cls.extract_dir = os.path.join(cls.tmpd, 'curtin')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpd)

    def run_python(self, args):
        start_dir = os.getcwd()
        cmd = [sys.executable]
        for i in args:
            cmd.append(i)

        env = os.environ.copy()
        env['CURTIN_STACKTRACE'] = "1"
        try:
            os.chdir(self.extract_dir)
            return util.subp(cmd, capture=True, env=env)
        finally:
            os.chdir(start_dir)

    def run_main(self, args):
        return self.run_python(
            ['-m', 'curtin.commands.main'] + [a for a in args])

    def run_install(self, cfg):
        # runs an install with a provided config
        # return stdout, stderr, exit_code, log_file_contents

        # src_url is required by arg parser, but not used here.
        src_url = 'file://' + self.tmpd + '/NOT_USED'
        mcfg = cfg.copy()
        log_file = cfg_file = None
        rc = None
        try:
            log_file = tempfile.mktemp(dir=self.tmpd)
            cfg_file = tempfile.mktemp(dir=self.tmpd)
            mcfg['install'] = {'log_file': log_file}
            mcfg['sources'] = {'testsrc': src_url}
            util.write_file(cfg_file, json.dumps(mcfg))
            try:
                out, err = self.run_main(['install', '--config=' + cfg_file])
                rc = 0
            except util.ProcessExecutionError as e:
                out = e.stdout
                err = e.stderr
                rc = e.exit_code
            log_contents = util.load_file(log_file)
        finally:
            for f in [f for f in (log_file, cfg_file) if f]:
                os.unlink(f)

        return out, err, rc, log_contents

    def test_psuedo_install(self):
        # do a install that has only a early stage and only one command.
        mystr = "HI MOM"
        cfg = {
            'stages': ['early'],
            'early_commands': {
                'mycmd': ["sh", "-c", "echo " + mystr]
            }}

        out, err, rc, log_contents = self.run_install(cfg)

        # the version string and users command output should be in output
        self.assertIn(version.version_string(), out)
        self.assertIn(mystr, out)
        self.assertEqual(0, rc)

        self.assertIn(INSTALL_START_MSG, out)
        self.assertIn(INSTALL_START_MSG, log_contents)
        self.assertIn(INSTALL_PASS_MSG, out)
        self.assertIn(INSTALL_PASS_MSG, log_contents)
        # log should also have the version string.
        self.assertIn(version.version_string(), log_contents)

    def test_psuedo_install_fail(self):
        # do a psuedo install that fails
        mystr = "GOODBYE MOM"
        cfg = {
            'stages': ['early'],
            'early_commands': {
                'mycmd': ["sh", "-c", "echo " + mystr + "; exit 9;"]
            }}

        out, err, rc, log_contents = self.run_install(cfg)

        # the version string and users command output should be in output
        self.assertIn(version.version_string(), out)
        self.assertIn(version.version_string(), log_contents)
        self.assertIn(mystr, out)
        # rc is not expected to match the 'exit 9' above, but should not be 0.
        self.assertNotEqual(0, rc)

        self.assertIn(INSTALL_START_MSG, out)
        self.assertIn(INSTALL_START_MSG, log_contents)

        # from INSTALL_FAIL_MSG, without exception
        failmsg = "curtin: Installation failed"
        self.assertIn(failmsg, err)
        self.assertIn(failmsg, log_contents)

    def test_curtin_help_has_version(self):
        # test curtin --help has version
        out, err = self.run_main(['--help'])
        self.assertIn(version.version_string(), out)

    def test_curtin_version(self):
        # test curtin version subcommand outputs expected version.
        out, err = self.run_main(['version'])
        self.assertEqual(version.version_string(), out.strip())

    def test_curtin_help_has_hacked_version(self):
        # ensure that we are running the output of pack, and not the venv
        # Change 'version.py' to contain a different string than the venv
        # has, and verify that python --help has that changed string, then
        # change it back for other tests.
        version_py = os.path.join(self.extract_dir, 'curtin', 'version.py')
        version_pyc = version_py + "c"
        hack_version_str = "MY_VERSION_STRING"
        orig_contents = util.load_file(version_py)
        hacked_contents = orig_contents.replace(
            version.version_string(), hack_version_str)
        self.assertIn(hack_version_str, hacked_contents)
        try:
            util.write_file(version_py, hacked_contents)
            util.del_file(version_pyc)
            out, err = self.run_main(['--help'])
        finally:
            util.del_file(version_pyc)
            util.write_file(version_py, orig_contents)

        self.assertIn(hack_version_str, out)

    def test_curtin_expected_dirs(self):
        # after extract, top level curtin dir, then curtin/{bin,curtin}
        tld = os.path.join(self.tmpd, 'curtin')
        self.assertTrue(os.path.isdir(tld))
        self.assertTrue(os.path.isdir(os.path.join(tld, 'curtin')))
        self.assertTrue(os.path.isdir(os.path.join(tld, 'bin')))

# vi: ts=4 expandtab syntax=python
