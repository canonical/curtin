""" test_apt_source
Testing various config variations of the apt_source custom config
"""
import glob
import os
import re
import shutil
import tempfile

from unittest import TestCase

try:
    from unittest import mock
except ImportError:
    import mock
from mock import call

from curtin import util
from curtin.commands import apt_source


EXPECTEDKEY = """-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1

mI0ESuZLUgEEAKkqq3idtFP7g9hzOu1a8+v8ImawQN4TrvlygfScMU1TIS1eC7UQ
NUA8Qqgr9iUaGnejb0VciqftLrU9D6WYHSKz+EITefgdyJ6SoQxjoJdsCpJ7o9Jy
8PQnpRttiFm4qHu6BVnKnBNxw/z3ST9YMqW5kbMQpfxbGe+obRox59NpABEBAAG0
HUxhdW5jaHBhZCBQUEEgZm9yIFNjb3R0IE1vc2VyiLYEEwECACAFAkrmS1ICGwMG
CwkIBwMCBBUCCAMEFgIDAQIeAQIXgAAKCRAGILvPA2g/d3aEA/9tVjc10HOZwV29
OatVuTeERjjrIbxflO586GLA8cp0C9RQCwgod/R+cKYdQcHjbqVcP0HqxveLg0RZ
FJpWLmWKamwkABErwQLGlM/Hwhjfade8VvEQutH5/0JgKHmzRsoqfR+LMO6OS+Sm
S0ORP6HXET3+jC8BMG4tBWCTK/XEZw==
=ACB2
-----END PGP PUBLIC KEY BLOCK-----"""

ADD_APT_REPO_MATCH = r"^[\w-]+:\w"


def load_tfile(filename):
    """ load_tfile
    load file and return content after decoding
    """
    try:
        content = util.load_file(filename, mode="r")
    except Exception as error:
        print('failed to load file content for test: %s' % error)
        raise

    return content


class TestAptSourceConfig(TestCase):
    """ TestAptSourceConfig
    Main Class to test apt_source configs
    """
    def setUp(self):
        super(TestAptSourceConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.aptlistfile = os.path.join(self.tmp, "single-deb.list")
        self.aptlistfile2 = os.path.join(self.tmp, "single-deb2.list")
        self.aptlistfile3 = os.path.join(self.tmp, "single-deb3.list")
        self.join = os.path.join
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search

    @staticmethod
    def _get_default_params():
        """ get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = apt_source.get_release()
        params['MIRROR'] = "http://archive.ubuntu.com/ubuntu"
        return params

    def _myjoin(self, *args, **kwargs):
        """ _myjoin - redir into writable tmpdir"""
        if (args[0] == "/etc/apt/sources.list.d/" and
                args[1] == "cloud_config_sources.list" and
                len(args) == 2):
            return self.join(self.tmp, args[0].lstrip("/"), args[1])
        else:
            return self.join(*args, **kwargs)

    def _apt_src_basic(self, filename, cfg):
        """ _apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_basic(self):
        "test_apt_src_basic - Test fix deb source string"
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://archive.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

    def test_apt_src_basic_tri(self):
        "test_apt_src_basic_tri - Test multiple fix deb source strings"
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://archive.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')},
               self.aptlistfile2: {'source':
                                   ('deb http://archive.ubuntu.com/ubuntu'
                                    ' precise-backports'
                                    ' main universe multiverse restricted')},
               self.aptlistfile3: {'source':
                                   ('deb http://archive.ubuntu.com/ubuntu'
                                    ' lucid-backports'
                                    ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://archive.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def _apt_src_replacement(self, filename, cfg):
        """ apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace(self):
        "test_apt_src_replace - Test Autoreplacement of MIRROR and RELEASE"
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'}}
        self._apt_src_replacement(self.aptlistfile, cfg)

    def test_apt_src_replace_fn(self):
        "test_apt_src_replace_fn - Test filename key being overwritten in dict"
        cfg = {'ignored': {'source': 'deb $MIRROR $RELEASE multiverse',
                           'filename': self.aptlistfile}}
        # second file should overwrite the dict key
        self._apt_src_replacement(self.aptlistfile, cfg)

    def _apt_src_replace_tri(self, cfg):
        """ _apt_src_replace_tri
        Test three autoreplacements of MIRROR and RELEASE in source specs with
        generic part
        """
        self._apt_src_replacement(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        params = self._get_default_params()
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "main"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "universe"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_replace_tri(self):
        "test_apt_src_replace_tri - Test multiple replacements / overwrites"
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused':        {'source': 'deb $MIRROR $RELEASE main',
                                  'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self._apt_src_replace_tri(cfg)

    def _apt_src_keyid(self, filename, cfg, keynum):
        """ _apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1234', '')) as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        # check if it added the right ammount of keys
        calls = []
        for _ in range(keynum):
            calls.append(call(('apt-key', 'add', '-'), b'fakekey 1234'))
        mockobj.assert_has_calls(calls, any_order=True)

        self.assertTrue(os.path.isfile(filename))

        contents = load_tfile(filename)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyid(self):
        "test_apt_src_keyid - Test source + keyid with filename being set"
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"}}
        self._apt_src_keyid(self.aptlistfile, cfg, 1)

    def test_apt_src_keyid_tri(self):
        "test_apt_src_keyid_tri - Test multiple src+keyid's+filename overwrite"
        cfg = {self.aptlistfile:  {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial main'),
                                   'keyid': "03683F77"},
               'ignored':         {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial universe'),
                                   'keyid': "03683F77",
                                   'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': ('deb '
                                              'http://ppa.launchpad.net/'
                                              'smoser/cloud-init-test/ubuntu'
                                              ' xenial multiverse'),
                                   'keyid': "03683F77"}}

        self._apt_src_keyid(self.aptlistfile, cfg, 3)
        contents = load_tfile(self.aptlistfile2)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "universe"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self.aptlistfile3)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "multiverse"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_key(self):
        "test_apt_src_key - Test source + key"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'key': "fakekey 4321"}}

        with mock.patch.object(util, 'subp') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        mockobj.assert_called_with(('apt-key', 'add', '-'), b'fakekey 4321')

        self.assertTrue(os.path.isfile(self.aptlistfile))

        contents = load_tfile(self.aptlistfile)
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    def test_apt_src_keyonly(self):
        "test_apt_src_keyonly - Test key without source"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'key': "fakekey 4242"}}

        with mock.patch.object(util, 'subp') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        mockobj.assert_called_once_with(('apt-key', 'add', '-'),
                                        b'fakekey 4242')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyidonly(self):
        "test_apt_src_keyidonly - Test keyid without source"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': "03683F77"}}

        with mock.patch.object(util, 'subp',
                               return_value=('fakekey 1212', '')) as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        mockobj.assert_called_with(('apt-key', 'add', '-'), b'fakekey 1212')

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_keyid_real(self):
        "test_apt_src_keyid_real - Test keyid including key content"
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': keyid}}

        with mock.patch.object(apt_source, 'add_key_raw') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        mockobj.assert_called_with(EXPECTEDKEY)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_longkeyid_real(self):
        "test_apt_src_longkeyid_real Test long keyid including key content"
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': keyid}}

        with mock.patch.object(apt_source, 'add_key_raw') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)

        mockobj.assert_called_with(EXPECTEDKEY)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_ppa(self):
        "test_apt_src_ppa - Test specification of a ppa"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'}}

        with mock.patch.object(util, 'subp') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)
        mockobj.assert_called_once_with(['add-apt-repository',
                                         'ppa:smoser/cloud-init-test'])

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))

    def test_apt_src_ppa_tri(self):
        "test_apt_src_ppa_tri - Test specification of multiple ppa's"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'},
               self.aptlistfile2: {'source': 'ppa:smoser/cloud-init-test2'},
               self.aptlistfile3: {'source': 'ppa:smoser/cloud-init-test3'}}

        with mock.patch.object(util, 'subp') as mockobj:
            apt_source.add_sources(cfg, params, aa_repo_match=self.matcher)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test']),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2']),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'])]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(self.aptlistfile))
        self.assertFalse(os.path.isfile(self.aptlistfile2))
        self.assertFalse(os.path.isfile(self.aptlistfile3))

    def test_mir_apt_list_rename(self):
        "test_mir_apt_list_rename - Test find mirrors and apt list renaming"
        cfg = {"apt_primary_mirror": "http://us.archive.ubuntu.com/ubuntu/",
               "apt_security_mirror": "http://security.ubuntu.com/ubuntu/"}
        mirrors = apt_source.find_apt_mirror_info(cfg)

        self.assertEqual(mirrors['MIRROR'],
                         "http://us.archive.ubuntu.com/ubuntu/")
        self.assertEqual(mirrors['PRIMARY'],
                         "http://us.archive.ubuntu.com/ubuntu/")
        self.assertEqual(mirrors['SECURITY'],
                         "http://security.ubuntu.com/ubuntu/")

        pre = "/var/lib/apt/lists"
        post = "ubuntu_dists_%s-proposed_InRelease" % apt_source.get_release()
        fromfn = ("%s/archive.ubuntu.com_%s" % (pre, post))
        tofn = ("%s/us.archive.ubuntu.com_%s" % (pre, post))

        with mock.patch.object(os, 'rename') as mockren:
            with mock.patch.object(glob, 'glob',
                                   return_value=[fromfn]):
                apt_source.rename_apt_lists(mirrors)

        mockren.assert_any_call(fromfn, tofn)

    @staticmethod
    def test_apt_proxy():
        "test_mir_apt_list_rename - Test apt_*proxy configuration"
        cfg = {"apt_proxy": "foobar1",
               "apt_http_proxy": "foobar2",
               "apt_ftp_proxy": "foobar3",
               "apt_https_proxy": "foobar4"}

        with mock.patch.object(util, 'write_file') as mockobj:
            apt_source.apply_apt_proxy_config(cfg, "proxyfn", "notused")

        mockobj.assert_called_with('proxyfn',
                                   ('Acquire::HTTP::Proxy "foobar1";\n'
                                    'Acquire::HTTP::Proxy "foobar2";\n'
                                    'Acquire::FTP::Proxy "foobar3";\n'
                                    'Acquire::HTTPS::Proxy "foobar4";\n'))


# vi: ts=4 expandtab
