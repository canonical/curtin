# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_apt_source
Testing various config variations of the apt_source custom config
"""
import glob
import os
import re
import socket


from unittest import mock
from unittest.mock import call

from aptsources.sourceslist import SourceEntry

from curtin import distro
from curtin import gpg
from curtin import util
from curtin.commands import apt_config
from .helpers import CiTestCase


EXPECTEDKEY = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----
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

EXPECTEDKEY_NOVER = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----

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

EXPECTED_BINKEY = util.load_file("tests/data/test.gpg", decode=False)

ADD_APT_REPO_MATCH = r"^[\w-]+:\w"


def load_tfile(filename, decode=True):
    """ load_tfile
    load file and return content after decoding
    """
    try:
        content = util.load_file(filename, decode=decode)
    except Exception as error:
        print('failed to load file content for test: %s' % error)
        raise

    return content


class PseudoChrootableTarget(util.ChrootableTarget):
    # no-ops the mounting and modifying that ChrootableTarget does
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return


ChrootableTargetStr = "curtin.commands.apt_config.util.ChrootableTarget"


def entryify(data):
    return [SourceEntry(line) for line in data.splitlines()]


def lineify(entries):
    out = apt_config.entries_to_str(entries)
    # the tests are written without the trailing newline,
    # but we don't want to remove multiple of them
    out = out[:-1] if len(out) > 0 and out[-1] == '\n' else out
    return out


def mock_want_deb822(return_value):
    def inner(test_func):
        def patched_test_func(*args, **kwargs):
            with mock.patch('curtin.commands.apt_config.want_deb822') as m:
                m.return_value = return_value
                test_func(*args, **kwargs)

        return patched_test_func

    return inner


class TestAptSourceConfig(CiTestCase):
    """ TestAptSourceConfig
    Main Class to test apt configs
    """
    def setUp(self):
        super(TestAptSourceConfig, self).setUp()
        self.target = self.tmp_dir()
        self.aptlistfile = "single-deb.list"
        self.aptlistfile2 = "single-deb2.list"
        self.aptlistfile3 = "single-deb3.list"
        self.matcher = re.compile(ADD_APT_REPO_MATCH).search

    def _sources_filepath(self, filename):
        # force the paths to be relative to the target
        # let filename decide a different directory path if given a path
        against_target = os.path.join('etc/apt/sources.list.d', filename)
        return self.target + '/' + against_target

    def _key_filepath(self, filename):
        # always to trusted.gpg.d
        basename = os.path.basename(filename)
        return os.path.join(self.target, 'etc/apt/trusted.gpg.d', basename)

    @staticmethod
    def _add_apt_sources(*args, **kwargs):
        with mock.patch.object(distro, 'apt_update'):
            apt_config.add_apt_sources(*args, **kwargs)

    @staticmethod
    def _get_default_params():
        """ get_default_params
        Get the most basic default mrror and release info to be used in tests
        """
        params = {}
        params['RELEASE'] = distro.lsb_release()['codename']
        arch = distro.get_architecture()
        params['MIRROR'] = apt_config.get_default_mirrors(arch)["PRIMARY"]
        params['SECURITY'] = apt_config.get_default_mirrors(arch)["SECURITY"]
        return params

    def _apt_src_basic(self, filename, cfg):
        """ _apt_src_basic
        Test Fix deb source string, has to overwrite mirror conf in params
        """
        params = self._get_default_params()

        self._add_apt_sources(cfg, self.target, template_params=params,
                              aa_repo_match=self.matcher)

        contents = load_tfile(self._sources_filepath(filename))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "karmic-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    def test_apt_src_basic(self):
        """test_apt_src_basic - Test fix deb source string"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

    @mock_want_deb822(False)
    def test_apt_src_fullpath(self):
        """test_apt_src_fullpath - Test fix deb source string to full path"""
        fullpath = '/my/unique/sources.list'
        cfg = {
            fullpath: {
                'source': ('deb http://test.ubuntu.com/ubuntu'
                           ' karmic-backports'
                           ' main universe multiverse restricted')}}
        self._apt_src_basic(fullpath, cfg)

    @mock_want_deb822(False)
    def test_apt_src_basic_tri(self):
        """test_apt_src_basic_tri - Test multiple fix deb source strings"""
        cfg = {self.aptlistfile: {'source':
                                  ('deb http://test.ubuntu.com/ubuntu'
                                   ' karmic-backports'
                                   ' main universe multiverse restricted')},
               self.aptlistfile2: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' precise-backports'
                                    ' main universe multiverse restricted')},
               self.aptlistfile3: {'source':
                                   ('deb http://test.ubuntu.com/ubuntu'
                                    ' lucid-backports'
                                    ' main universe multiverse restricted')}}
        self._apt_src_basic(self.aptlistfile, cfg)

        # extra verify on two extra files of this test
        contents = load_tfile(self._sources_filepath(self.aptlistfile2))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "precise-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self._sources_filepath(self.aptlistfile3))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", "http://test.ubuntu.com/ubuntu",
                                   "lucid-backports",
                                   "main universe multiverse restricted"),
                                  contents, flags=re.IGNORECASE))

    def _apt_src_replacement(self, filename, cfg):
        """ apt_src_replace
        Test Autoreplacement of MIRROR and RELEASE in source specs
        """
        params = self._get_default_params()
        self._add_apt_sources(cfg, self.target, template_params=params,
                              aa_repo_match=self.matcher)

        contents = load_tfile(self._sources_filepath(filename))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "multiverse"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    def test_apt_src_replace(self):
        """test_apt_src_replace - Test Autoreplacement of MIRROR and RELEASE"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'}}
        self._apt_src_replacement(self.aptlistfile, cfg)

    @mock_want_deb822(False)
    def test_apt_src_replace_fn(self):
        """test_apt_src_replace_fn - Test filename being overwritten in dict"""
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
        contents = load_tfile(self._sources_filepath(self.aptlistfile2))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "main"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self._sources_filepath(self.aptlistfile3))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb", params['MIRROR'], params['RELEASE'],
                                   "universe"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    def test_apt_src_replace_tri(self):
        """test_apt_src_replace_tri - Test multiple replacements/overwrites"""
        cfg = {self.aptlistfile: {'source': 'deb $MIRROR $RELEASE multiverse'},
               'notused':        {'source': 'deb $MIRROR $RELEASE main',
                                  'filename': self.aptlistfile2},
               self.aptlistfile3: {'source': 'deb $MIRROR $RELEASE universe'}}
        self._apt_src_replace_tri(cfg)

    def _apt_src_keyid_txt(self, filename, cfg):
        """ _apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch.object(gpg, 'getkeybyid',
                               return_value=EXPECTEDKEY_NOVER):
            self._add_apt_sources(cfg, self.target, template_params=params,
                                  aa_repo_match=self.matcher)

        for ent in cfg:
            key_filename = cfg[ent].get('filename', ent) + '.asc'
            contents = load_tfile(self._key_filepath(key_filename))
            self.assertMultiLineEqual(EXPECTEDKEY_NOVER, contents)

    def _apt_src_keyid_bin(self, filename, cfg):
        """ _apt_src_keyid
        Test specification of a source + keyid
        """
        params = self._get_default_params()

        with mock.patch.object(gpg, 'getkeybyid',
                               return_value=EXPECTED_BINKEY):
            self._add_apt_sources(cfg, self.target, template_params=params,
                                  aa_repo_match=self.matcher)

        for ent in cfg:
            key_filename = cfg[ent].get('filename', ent) + '.gpg'
            contents = load_tfile(self._key_filepath(key_filename), False)
            self.assertEqual(EXPECTED_BINKEY, contents)

    def _apt_src_keyid(self, filename, cfg, key_type="txt"):
        """ _apt_src_keyid
        Test specification of a source + keyid
        """
        if key_type == "txt":
            self._apt_src_keyid_txt(filename, cfg)
        else:
            self._apt_src_keyid_bin(filename, cfg)

        contents = load_tfile(self._sources_filepath(filename))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyid(self):
        """test_apt_src_keyid - Test source + keyid with filename being set"""
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"}}
        self._apt_src_keyid(self.aptlistfile, cfg)

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyid_bin(self):
        """test_apt_src_keyid - Test source + keyid with filename being set"""
        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'keyid': "03683F77"}}
        self._apt_src_keyid(self.aptlistfile, cfg, key_type='bin')

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyid_tri(self):
        """test_apt_src_keyid_tri - Test multiple src+keyid+filen overwrites"""
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

        self._apt_src_keyid(self.aptlistfile, cfg)
        contents = load_tfile(self._sources_filepath(self.aptlistfile2))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "universe"),
                                  contents, flags=re.IGNORECASE))
        contents = load_tfile(self._sources_filepath(self.aptlistfile3))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "multiverse"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_key(self):
        """test_apt_src_key - Test source + key"""
        params = self._get_default_params()
        fake_key = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----
                       fakekey 4321"""

        cfg = {self.aptlistfile: {'source': ('deb '
                                             'http://ppa.launchpad.net/'
                                             'smoser/cloud-init-test/ubuntu'
                                             ' xenial main'),
                                  'key': fake_key}}

        self._add_apt_sources(cfg, self.target, template_params=params,
                              aa_repo_match=self.matcher)

        contents = load_tfile(self._key_filepath(self.aptlistfile + '.asc'))
        self.assertMultiLineEqual(fake_key, contents)

        contents = load_tfile(self._sources_filepath(self.aptlistfile))
        self.assertTrue(re.search(r"%s %s %s %s\n" %
                                  ("deb",
                                   ('http://ppa.launchpad.net/smoser/'
                                    'cloud-init-test/ubuntu'),
                                   "xenial", "main"),
                                  contents, flags=re.IGNORECASE))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyonly(self):
        """test_apt_src_keyonly - Test key without source"""
        params = self._get_default_params()
        fake_key = u"""-----BEGIN PGP PUBLIC KEY BLOCK-----
                       fakekey 4321"""
        cfg = {self.aptlistfile: {'key': fake_key}}

        self._add_apt_sources(cfg, self.target, template_params=params,
                              aa_repo_match=self.matcher)

        contents = load_tfile(self._key_filepath(self.aptlistfile + '.asc'))
        self.assertMultiLineEqual(fake_key, contents)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_keyidonly(self):
        """test_apt_src_keyidonly - Test keyid without source"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': "03683F77"}}

        with mock.patch.object(gpg, 'getkeybyid',
                               return_value=EXPECTEDKEY_NOVER):
            self._add_apt_sources(cfg, self.target, template_params=params,
                                  aa_repo_match=self.matcher)

        contents = load_tfile(self._key_filepath(self.aptlistfile + '.asc'))
        self.assertMultiLineEqual(EXPECTEDKEY_NOVER, contents)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))

    def apt_src_keyid_real(self, cfg, expectedkey):
        """apt_src_keyid_real
        Test specification of a keyid without source including
        up to addition of the key (add_apt_key_raw mocked to keep the
        environment as is)
        """
        params = self._get_default_params()

        with mock.patch.object(apt_config, 'add_apt_key_raw') as mockkey:
            with mock.patch.object(gpg, 'getkeybyid',
                                   return_value=expectedkey) as mockgetkey:
                self._add_apt_sources(cfg, self.target, template_params=params,
                                      aa_repo_match=self.matcher)

        keycfg = cfg[self.aptlistfile]
        mockgetkey.assert_called_with(keycfg['keyid'],
                                      keycfg.get('keyserver',
                                                 'keyserver.ubuntu.com'),
                                      retries=(1, 2, 5, 10))
        mockkey.assert_called_with(self.aptlistfile, expectedkey, self.target)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))

    @mock_want_deb822(False)
    def test_apt_src_keyid_real(self):
        """test_apt_src_keyid_real - Test keyid including key add"""
        keyid = "03683F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    @mock_want_deb822(False)
    def test_apt_src_longkeyid_real(self):
        """test_apt_src_longkeyid_real Test long keyid including key add"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    @mock_want_deb822(False)
    def test_apt_src_longkeyid_ks_real(self):
        """test_apt_src_longkeyid_ks_real Test long keyid from other ks"""
        keyid = "B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77"
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'keys.gnupg.net'}}

        self.apt_src_keyid_real(cfg, EXPECTEDKEY)

    @mock_want_deb822(False)
    def test_apt_src_keyid_keyserver(self):
        """test_apt_src_keyid_keyserver - Test custom keyserver"""
        keyid = "03683F77"
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'keyid': keyid,
                                  'keyserver': 'test.random.com'}}

        # in some test environments only *.ubuntu.com is reachable
        # so mock the call and check if the config got there
        with mock.patch.object(gpg, 'getkeybyid',
                               return_value="fakekey") as mockgetkey:
            with mock.patch.object(apt_config, 'add_apt_key_raw') as mockadd:
                self._add_apt_sources(cfg, self.target, template_params=params,
                                      aa_repo_match=self.matcher)

        mockgetkey.assert_called_with('03683F77', 'test.random.com',
                                      retries=(1, 2, 5, 10))
        mockadd.assert_called_with(self.aptlistfile, 'fakekey', self.target)

        # filename should be ignored on key only
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_ppa(self):
        """test_apt_src_ppa - Test specification of a ppa"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'}}

        with mock.patch("curtin.util.subp") as mockobj:
            self._add_apt_sources(cfg, self.target, template_params=params,
                                  aa_repo_match=self.matcher)
        mockobj.assert_any_call(['add-apt-repository',
                                 'ppa:smoser/cloud-init-test'],
                                retries=(1, 2, 5, 10), target=self.target)

        # adding ppa should ignore filename (uses add-apt-repository)
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))

    @mock_want_deb822(False)
    @mock.patch(ChrootableTargetStr, new=PseudoChrootableTarget)
    def test_apt_src_ppa_tri(self):
        """test_apt_src_ppa_tri - Test specification of multiple ppa's"""
        params = self._get_default_params()
        cfg = {self.aptlistfile: {'source': 'ppa:smoser/cloud-init-test'},
               self.aptlistfile2: {'source': 'ppa:smoser/cloud-init-test2'},
               self.aptlistfile3: {'source': 'ppa:smoser/cloud-init-test3'}}

        with mock.patch("curtin.util.subp") as mockobj:
            self._add_apt_sources(cfg, self.target, template_params=params,
                                  aa_repo_match=self.matcher)
        calls = [call(['add-apt-repository', 'ppa:smoser/cloud-init-test'],
                      retries=(1, 2, 5, 10), target=self.target),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test2'],
                      retries=(1, 2, 5, 10), target=self.target),
                 call(['add-apt-repository', 'ppa:smoser/cloud-init-test3'],
                      retries=(1, 2, 5, 10), target=self.target)]
        mockobj.assert_has_calls(calls, any_order=True)

        # adding ppa should ignore all filenames (uses add-apt-repository)
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile)))
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile2)))
        self.assertFalse(os.path.isfile(
            self._sources_filepath(self.aptlistfile3)))

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_mir_apt_list_rename(self, m_get_architecture):
        """test_mir_apt_list_rename - Test find mirror and apt list renaming"""
        pre = os.path.join(self.target, "var/lib/apt/lists")
        # filenames are archive dependent

        arch = 's390x'
        m_get_architecture.return_value = arch
        component = "ubuntu-ports"
        archive = "ports.ubuntu.com"

        cfg = {'primary': [{'arches': ["default"],
                            'uri':
                            'http://test.ubuntu.com/%s/' % component}],
               'security': [{'arches': ["default"],
                             'uri':
                             'http://testsec.ubuntu.com/%s/' % component}]}
        post = ("%s_dists_%s-updates_InRelease" %
                (component, distro.lsb_release()['codename']))
        fromfn = ("%s/%s_%s" % (pre, archive, post))
        tofn = ("%s/test.ubuntu.com_%s" % (pre, post))

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['MIRROR'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['PRIMARY'],
                         "http://test.ubuntu.com/%s/" % component)
        self.assertEqual(mirrors['SECURITY'],
                         "http://testsec.ubuntu.com/%s/" % component)

        with mock.patch.object(os, 'rename') as mockren:
            with mock.patch.object(glob, 'glob',
                                   return_value=[fromfn]):
                apt_config.rename_apt_lists(mirrors, self.target)

        mockren.assert_any_call(fromfn, tofn)

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_mir_apt_list_rename_non_slash(self, m_get_architecture):
        target = os.path.join(self.target, "rename_non_slash")
        apt_lists_d = os.path.join(target, "./" + apt_config.APT_LISTS)

        m_get_architecture.return_value = 'amd64'

        mirror_path = "some/random/path/"
        primary = "http://test.ubuntu.com/" + mirror_path
        security = "http://test-security.ubuntu.com/" + mirror_path
        mirrors = {'PRIMARY': primary, 'SECURITY': security}

        # these match default archive prefixes
        opri_pre = "archive.ubuntu.com_ubuntu_dists_xenial"
        osec_pre = "security.ubuntu.com_ubuntu_dists_xenial"
        # this one won't match and should not be renamed defaults.
        other_pre = "dl.google.com_linux_chrome_deb_dists_stable"
        # these are our new expected prefixes
        npri_pre = "test.ubuntu.com_some_random_path_dists_xenial"
        nsec_pre = "test-security.ubuntu.com_some_random_path_dists_xenial"

        files = [
            # orig prefix, new prefix, suffix
            (opri_pre, npri_pre, "_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "_main_binary-amd64_InRelease"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_Packages"),
            (opri_pre, npri_pre, "-updates_main_binary-amd64_InRelease"),
            (other_pre, other_pre, "_main_binary-amd64_Packages"),
            (other_pre, other_pre, "_Release"),
            (other_pre, other_pre, "_Release.gpg"),
            (osec_pre, nsec_pre, "_InRelease"),
            (osec_pre, nsec_pre, "_main_binary-amd64_Packages"),
            (osec_pre, nsec_pre, "_universe_binary-amd64_Packages"),
        ]

        expected = sorted([npre + suff for opre, npre, suff in files])
        # create files
        for (opre, npre, suff) in files:
            fpath = os.path.join(apt_lists_d, opre + suff)
            util.write_file(fpath, content=fpath)

        apt_config.rename_apt_lists(mirrors, target)
        found = sorted(os.listdir(apt_lists_d))
        self.assertEqual(expected, found)

    @staticmethod
    def test_apt_proxy():
        """test_apt_proxy - Test apt_*proxy configuration"""
        cfg = {"proxy": "foobar1",
               "http_proxy": "foobar2",
               "ftp_proxy": "foobar3",
               "https_proxy": "foobar4"}

        with mock.patch.object(util, 'write_file') as mockobj:
            apt_config.apply_apt_proxy_config(cfg, "proxyfn", "notused")

        mockobj.assert_called_with('proxyfn',
                                   ('Acquire::http::Proxy "foobar1";\n'
                                    'Acquire::http::Proxy "foobar2";\n'
                                    'Acquire::ftp::Proxy "foobar3";\n'
                                    'Acquire::https::Proxy "foobar4";\n'))

    def test_preference_to_str(self):
        """ test_preference_to_str - Test converting a preference dict to
        textual representation.
        """
        preference = {
            "package": "*",
            "pin": "release a=unstable",
            "pin-priority": 50,
        }

        expected = """\
Package: *
Pin: release a=unstable
Pin-Priority: 50
"""
        self.assertEqual(expected, apt_config.preference_to_str(preference))

    @staticmethod
    def test_apply_apt_preferences():
        """ test_apply_apt_preferences - Test apt preferences configuration
        """
        cfg = {
            "preferences": [
                {
                    "package": "*",
                    "pin": "release a=unstable",
                    "pin-priority": 50,
                }, {
                    "package": "sample-unwanted-package",
                    "pin": "origin *ubuntu.com*",
                    "pin-priority": -1,
                }
            ]
        }

        expected_content = """\
Package: *
Pin: release a=unstable
Pin-Priority: 50

Package: sample-unwanted-package
Pin: origin *ubuntu.com*
Pin-Priority: -1
"""
        with mock.patch.object(util, "write_file") as mockobj:
            apt_config.apply_apt_preferences(cfg, "preferencesfn")

        mockobj.assert_called_with("preferencesfn", expected_content)

    def test_translate_old_apt_features(self):
        cfg = {}
        apt_config.translate_old_apt_features(cfg)
        self.assertEqual(cfg, {})

        cfg = {"debconf_selections": "foo"}
        apt_config.translate_old_apt_features(cfg)
        self.assertEqual(cfg, {"apt": {"debconf_selections": "foo"}})

        cfg = {"apt_proxy": {"http_proxy": "http://proxy:3128"}}
        apt_config.translate_old_apt_features(cfg)
        self.assertEqual(cfg, {
            "apt": {
                "proxy": {"http_proxy": "http://proxy:3128"},
            }}
        )

        cfg = {
            "apt": {"debconf_selections": "foo"},
            "apt_proxy": {"http_proxy": "http://proxy:3128"},
        }
        apt_config.translate_old_apt_features(cfg)
        self.assertEqual(cfg, {
            "apt": {
                "proxy": {"http_proxy": "http://proxy:3128"},
                "debconf_selections": "foo",
            }}
        )

    def test_translate_old_apt_features_conflicts(self):
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            apt_config.translate_old_apt_features({
                "debconf_selections": "foo",
                "apt": {
                    "debconf_selections": "bar",
                }})

        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            apt_config.translate_old_apt_features({
                "apt_proxy": {"http_proxy": "http://proxy:3128"},
                "apt": {
                    "proxy": {"http_proxy": "http://proxy:3128"},
                }})

    def test_mirror(self):
        """test_mirror - Test defining a mirror"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir}],
               "security": [{'arches': ["default"],
                             "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_default(self):
        """test_mirror_default - Test without defining a mirror"""
        arch = distro.get_architecture()
        default_mirrors = apt_config.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        mirrors = apt_config.find_apt_mirror_info({}, arch)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_arches(self):
        """test_mirror_arches - Test arches selection of mirror"""
        pmir = "http://my-primary.ubuntu.com/ubuntu/"
        smir = "http://my-security.ubuntu.com/ubuntu/"
        arch = 'ppc64el'
        cfg = {"primary": [{'arches': ["default"], "uri": "notthis-primary"},
                           {'arches': [arch], "uri": pmir}],
               "security": [{'arches': ["default"], "uri": "nothis-security"},
                            {'arches': [arch], "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_mirror_arches_default(self):
        """test_mirror_arches - Test falling back to default arch"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthis"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["default"],
                             "uri": smir}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    @mock.patch("curtin.commands.apt_config.distro.get_architecture")
    def test_get_default_mirrors_non_intel_no_arch(self, m_get_architecture):
        arch = 'ppc64el'
        m_get_architecture.return_value = arch
        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, apt_config.get_default_mirrors())

    def test_get_default_mirrors_non_intel_with_arch(self):
        found = apt_config.get_default_mirrors('ppc64el')

        expected = {'PRIMARY': 'http://ports.ubuntu.com/ubuntu-ports',
                    'SECURITY': 'http://ports.ubuntu.com/ubuntu-ports'}
        self.assertEqual(expected, found)

    def test_mirror_arches_sysdefault(self):
        """test_mirror_arches - Test arches falling back to sys default"""
        arch = distro.get_architecture()
        default_mirrors = apt_config.get_default_mirrors(arch)
        pmir = default_mirrors["PRIMARY"]
        smir = default_mirrors["SECURITY"]
        cfg = {"primary": [{'arches': ["thisarchdoesntexist_64"],
                            "uri": "notthis"},
                           {'arches': ["thisarchdoesntexist"],
                            "uri": "notthiseither"}],
               "security": [{'arches': ["thisarchdoesntexist"],
                             "uri": "nothat"},
                            {'arches': ["thisarchdoesntexist_64"],
                             "uri": "nothateither"}]}

        mirrors = apt_config.find_apt_mirror_info(cfg, arch)

        self.assertEqual(mirrors['MIRROR'], pmir)
        self.assertEqual(mirrors['PRIMARY'], pmir)
        self.assertEqual(mirrors['SECURITY'], smir)

    def test_mirror_search(self):
        """test_mirror_search - Test searching mirrors in a list
            mock checks to avoid relying on network connectivity"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "search": ["pfailme", pmir]}],
               "security": [{'arches': ["default"],
                             "search": ["sfailme", smir]}]}

        with mock.patch.object(apt_config, 'search_for_mirror',
                               side_effect=[pmir, smir]) as mocksearch:
            mirrors = apt_config.find_apt_mirror_info(cfg, 'amd64')

        calls = [call(["pfailme", pmir]),
                 call(["sfailme", smir])]
        mocksearch.assert_has_calls(calls)

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_mirror_search_many2(self):
        """test_mirror_search_many3 - Test both mirrors specs at once"""
        pmir = "http://us.archive.ubuntu.com/ubuntu/"
        smir = "http://security.ubuntu.com/ubuntu/"
        cfg = {"primary": [{'arches': ["default"],
                            "uri": pmir,
                            "search": ["pfailme", "foo"]}],
               "security": [{'arches': ["default"],
                             "uri": smir,
                             "search": ["sfailme", "bar"]}]}

        arch = 'amd64'

        # should be called only once per type, despite two mirror configs
        with mock.patch.object(apt_config, 'get_mirror',
                               return_value="http://mocked/foo") as mockgm:
            mirrors = apt_config.find_apt_mirror_info(cfg, arch)
        calls = [call(cfg, 'primary', arch), call(cfg, 'security', arch)]
        mockgm.assert_has_calls(calls)

        # should not be called, since primary is specified
        with mock.patch.object(apt_config, 'search_for_mirror') as mockse:
            mirrors = apt_config.find_apt_mirror_info(cfg, arch)
        mockse.assert_not_called()

        self.assertEqual(mirrors['MIRROR'],
                         pmir)
        self.assertEqual(mirrors['PRIMARY'],
                         pmir)
        self.assertEqual(mirrors['SECURITY'],
                         smir)

    def test_url_resolvable(self):
        """test_url_resolvable - Test resolving urls"""

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://1.2.3.4/ubuntu")
        mockresolve.assert_called_with("1.2.3.4")

        with mock.patch.object(util, 'is_resolvable') as mockresolve:
            util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
        mockresolve.assert_called_with("us.archive.ubuntu.com")

        bad = [(None, None, None, "badname", ["10.3.2.1"])]
        good = [(None, None, None, "goodname", ["10.2.3.4"])]
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad, bad, good,
                                            good]) as mocksock:
            ret = util.is_resolvable_url("http://us.archive.ubuntu.com/ubuntu")
            ret2 = util.is_resolvable_url("http://1.2.3.4/ubuntu")
        calls = [call('does-not-exist.example.com.', None, 0, 0, 1, 2),
                 call('example.invalid.', None, 0, 0, 1, 2),
                 call('us.archive.ubuntu.com', None),
                 call('1.2.3.4', None)]
        mocksock.assert_has_calls(calls)
        self.assertTrue(ret)
        self.assertTrue(ret2)

        # side effect need only bad ret after initial call
        with mock.patch.object(socket, 'getaddrinfo',
                               side_effect=[bad]) as mocksock:
            ret3 = util.is_resolvable_url("http://failme.com/ubuntu")
        calls = [call('failme.com', None)]
        mocksock.assert_has_calls(calls)
        self.assertFalse(ret3)

    def test_disable_suites(self):
        """test_disable_suites - disable_suites with many configurations"""
        release = "xenial"

        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""

        # disable nothing
        disabled = []
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable release suite
        disabled = ["$RELEASE"]
        expect = """# deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable other suite
        disabled = ["$RELEASE-updates"]
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # multi disable
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # multi line disable (same suite multiple times in input)
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
# deb http://UBUNTU.com//ubuntu xenial-updates main
# deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # comment in input
        disabled = ["$RELEASE-updates", "$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
#deb http://UBUNTU.com//ubuntu xenial-updates main
deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
#foo
# deb http://UBUNTU.com//ubuntu xenial-updates main
# deb http://UBUNTU.COM//ubuntu xenial-updates main
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable custom suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ foobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
# deb http://ubuntu.com/ubuntu/ foobar main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable non existing suite
        disabled = ["foobar"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb http://ubuntu.com/ubuntu/ notfoobar main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite with option
        disabled = ["$RELEASE-updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb [a=b] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite with more options and auto $RELEASE expansion
        disabled = ["updates"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [a=b c=d] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# deb [a=b c=d] http://ubu.com//ubu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

        # single disable suite while options at others
        disabled = ["$RELEASE-security"]
        orig = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
deb [arch=foo] http://ubuntu.com//ubuntu xenial-updates main
# deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main"""
        result = apt_config.disable_suites(disabled, entryify(orig), release)
        self.assertEqual(expect, lineify(result))

    def test_disable_suites_blank_lines(self):
        """test_disable_suites_blank_lines - ensure blank lines allowed"""
        rel = "trusty"

        orig = """
deb http://example.com/mirrors/ubuntu trusty main universe

deb http://example.com/mirrors/ubuntu trusty-updates main universe

deb http://example.com/mirrors/ubuntu trusty-proposed main universe

#comment here"""
        expect = """
deb http://example.com/mirrors/ubuntu trusty main universe

deb http://example.com/mirrors/ubuntu trusty-updates main universe

# deb http://example.com/mirrors/ubuntu trusty-proposed main universe

#comment here"""
        disabled = ["proposed"]
        result = apt_config.disable_suites(disabled, entryify(orig), rel)
        self.assertEqual(expect, lineify(result))

    def test_disable_components(self):
        orig = """\
deb http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial-security \
main restricted universe multiverse
deb-src http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed \
main restricted universe multiverse"""
        expect = orig

        # no-op
        disabled = []
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # no-op 2
        disabled = None
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # we don't disable main
        disabled = ('main', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # nonsense
        disabled = ('asdf', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # free-only
        expect = """\
# deb http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb http://ubuntu.com/ubuntu xenial main universe
# deb http://ubuntu.com/ubuntu xenial-updates main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates main universe
# deb http://ubuntu.com/ubuntu xenial-security main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu xenial-security main universe
# deb-src http://ubuntu.com/ubuntu xenial main restricted universe multiverse
deb-src http://ubuntu.com/ubuntu xenial main universe
# deb http://ubuntu.com/ubuntu/ xenial-proposed main restricted \
universe multiverse
deb http://ubuntu.com/ubuntu/ xenial-proposed main universe"""
        disabled = ('restricted', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # skip line when this component is the last
        orig = """\
deb http://ubuntu.com/ubuntu xenial main universe multiverse
deb http://ubuntu.com/ubuntu xenial-updates universe
deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        expect = """\
# deb http://ubuntu.com/ubuntu xenial main universe multiverse
deb http://ubuntu.com/ubuntu xenial main
# deb http://ubuntu.com/ubuntu xenial-updates universe
# deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        disabled = ('universe', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # comment everything
        orig = """\
deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        expect = """\
# deb http://ubuntu.com/ubuntu xenial-security universe multiverse"""
        disabled = ('universe', 'multiverse')
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

        # double-hash comment
        orig = """\

## Major bug fix updates produced after the final release of the
## distribution.

deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted
# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted"""
        expect = """\

## Major bug fix updates produced after the final release of the
## distribution.

# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted
deb http://archive.ubuntu.com/ubuntu/ impish-updates main
# deb http://archive.ubuntu.com/ubuntu/ impish-updates main restricted"""
        disabled = ('restricted', )
        result = apt_config.disable_components(disabled, entryify(orig))
        self.assertEqual(expect, lineify(result))

    @mock_want_deb822(False)
    @mock.patch("curtin.util.write_file")
    @mock.patch("curtin.distro.get_architecture")
    def test_generate_with_options(self, get_arch, write_file):
        get_arch.return_value = "amd64"
        orig = """deb http://ubuntu.com//ubuntu $RELEASE main
# stuff things

deb http://ubuntu.com//ubuntu $RELEASE-updates main
deb http://ubuntu.com//ubuntu $RELEASE-security main
deb-src http://ubuntu.com//ubuntu $RELEASE universe multiverse
# deb http://ubuntu.com/ubuntu/ $RELEASE-proposed main
deb [a=b] http://ubuntu.com/ubuntu/ $RELEASE-backports main
"""
        expect = """deb http://ubuntu.com//ubuntu xenial main
# stuff things

deb http://ubuntu.com//ubuntu xenial-updates main
deb http://ubuntu.com//ubuntu xenial-security main
deb-src http://ubuntu.com//ubuntu xenial universe multiverse
# deb http://ubuntu.com/ubuntu/ xenial-proposed main
# deb [a=b] http://ubuntu.com/ubuntu/ $RELEASE-backports main
"""
        # $RELEASE in backports doesn't get expanded because the line is
        # considered invalid because of the options.  So when the line
        # gets commented out, it comments out the original line, not
        # what we've modifed it to.
        rel = 'xenial'
        mirrors = {'PRIMARY': 'http://ubuntu.com/ubuntu/'}

        cfg = {
            'preserve_sources_list': False,
            'sources_list': orig,
            'disable_suites': ['backports'],
        }

        apt_config.generate_sources_list(cfg, rel, mirrors, self.target)
        filepath = os.path.join(self.target, 'etc/apt/sources.list')
        write_file.assert_called_with(filepath, expect, mode=0o644)

    @mock.patch('curtin.distro.os_release')
    def test_want_deb822(self, mock_os_release):
        testdata = [
            # (ID, VERSION_ID, want_deb822())
            ('ubuntu', '22.04', False),
            ('ubuntu', '22.10', False),
            ('ubuntu', '23.04', False),
            ('ubuntu', '23.10', True),
            ('ubuntu', '24.04', True),
            ('ubuntu', '24.10', True),
            ('fedora', '38', False),
            (None, None, False),
            ('ubuntu', '', False),
        ]

        for (dist, version, ret) in testdata:
            mock_os_release.return_value = {
                'ID': dist,
                'VERSION_ID': version,
            }
            self.assertEqual(
                apt_config.want_deb822(),
                ret,
                f'want_deb822() != {ret} (ID={distro}, VERSION_ID={version})'
            )

    @mock_want_deb822(True)
    @mock.patch("curtin.util.write_file")
    @mock.patch("curtin.distro.get_architecture")
    def test_generate_with_options_deb822(self, get_arch, write_file):
        get_arch.return_value = 'amd64'

        # input_filename: (in_data, expect_data)
        data = {
            'etc/apt/sources.list.d/ubuntu.sources': ((
                'Types: deb\n'
                'URIs: $MIRROR\n'
                'Suites: $RELEASE $RELEASE-updates\n'
                'components: main\n'
                'signed-by: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                # This section should be skipped because -backports is disabled
                'Types: deb\n'
                'URIs: $MIRROR\n'
                'Suites: $RELEASE-backports\n'
                'components: main\n'
                'signed-by: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Types: deb-src\n'
                'Uris: $MIRROR\n'
                'Suites: $RELEASE\n'
                'Components: universe multiverse\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Enabled: no\n'
                'Types: deb\n'
                'URIs: {mirror}\n'
                'Suites: $RELEASE-proposed\n'
                'Components: main\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            ), (
                'Types: deb\n'
                'URIs: http://ubuntu.com/ubuntu\n'
                'Suites: mantic mantic-updates\n'
                'Components: main\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Types: deb-src\n'
                'URIs: http://ubuntu.com/ubuntu\n'
                'Suites: mantic\n'
                'Components: universe\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Enabled: no\n'
                'Types: deb\n'
                'URIs: http://ubuntu.com/ubuntu\n'
                'Suites: mantic-proposed\n'
                'Components: main\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            )),
            'etc/apt/sources.list': ((
                'deb $MIRROR $RELEASE main universe\n'
                'deb-src {mirror} $RELEASE main universe\n'
                'deb $MIRROR $RELEASE-updates main universe\n'
                'deb $MIRROR $RELEASE-backports main universe\n'
            ), (
                'Types: deb\n'
                'URIs: http://ubuntu.com/ubuntu\n'
                'Suites: mantic mantic-updates\n'
                'Components: main universe\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Types: deb-src\n'
                'URIs: http://ubuntu.com/ubuntu\n'
                'Suites: mantic\n'
                'Components: main universe\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            )),
        }

        rel = 'mantic'
        mirrors = {'MIRROR': 'http://ubuntu.com/ubuntu'}

        # Test when sources_list is specified in config.
        for (orig, expect) in data.values():
            cfg = {
                'preserve_sources_list': False,
                'sources_list': orig.format(mirror='$MIRROR'),
                'disable_suites': ['backports'],
                'disable_components': ['multiverse'],
            }

            apt_config.generate_sources_list(cfg, rel, mirrors, self.target)
            filepath = os.path.join(
                self.target,
                'etc/apt/sources.list.d/ubuntu.sources'
            )
            write_file.assert_called_with(filepath, expect, mode=0o644)

        default_mirror = apt_config.get_default_mirrors()['PRIMARY']

        # Make sure that default mirrors are replaced correctly when reading
        # from a file.
        for mirror in (default_mirror, default_mirror.rstrip('/')):
            for (in_path, (orig, expect)) in data.items():
                cfg = {
                    'preserve_sources_list': False,
                    'sources_list': None,
                    'disable_suites': ['backports'],
                    'disable_components': ['multiverse'],
                }

                target_path = os.path.join(self.target, in_path)

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, 'w') as f:
                    f.write(orig.format(mirror=mirror))

                apt_config.generate_sources_list(
                    cfg,
                    rel,
                    mirrors,
                    self.target
                )

                filepath = os.path.join(
                    self.target,
                    'etc/apt/sources.list.d/ubuntu.sources'
                )

                if in_path == 'etc/apt/sources.list':
                    write_file.assert_has_calls([
                        mock.call(filepath, expect, mode=0o644),
                        mock.call(
                            target_path,
                            '# Ubuntu sources have moved to '
                            '/etc/apt/sources.list.d/ubuntu.sources\n',
                            mode=0o644
                        )
                    ])
                else:
                    write_file.assert_called_with(filepath, expect, mode=0o644)

                if os.path.exists(target_path):
                    os.remove(target_path)

    @mock_want_deb822(True)
    @mock.patch("curtin.util.write_file")
    @mock.patch("curtin.distro.get_architecture")
    def test_generate_no_cfg_deb822(self, get_arch, write_file):
        get_arch.return_value = 'amd64'

        orig = (
            '# See http://help.ubuntu.com/community/UpgradeNotes '
            'for how to upgrade to\n'
            '# newer versions of the distribution.\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic main restricted\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic main restricted\n'
            '\n'
            '## Major bug fix updates produced after the final release '
            'of the\n'
            '## distribution.\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates main restricted\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates main restricted\n'
            '\n'
            '## N.B. software from this repository is ENTIRELY UNSUPPORTED '
            'by the Ubuntu\n'
            '## team. Also, please note that software in universe '
            'WILL NOT receive any\n'
            '## review or updates from the Ubuntu security team.\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic universe\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic universe\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates universe\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates universe\n'
            '\n'
            '## N.B. software from this repository is ENTIRELY UNSUPPORTED '
            'by the Ubuntu\n'
            '## team, and may not be under a free licence. '
            'Please satisfy yourself as to\n'
            '## your rights to use the software. Also, please note that '
            'software in\n'
            '## multiverse WILL NOT receive any review or '
            'updates from the Ubuntu\n'
            '## security team.\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic multiverse\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic multiverse\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates multiverse\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic-updates multiverse\n'
            '\n'
            '## N.B. software from this repository may not have '
            'been tested as\n'
            '## extensively as that contained in the main release'
            ', although it includes\n'
            '## newer versions of some applications which may provide '
            'useful features.\n'
            '## Also, please note that software in backports '
            'WILL NOT receive any review\n'
            '## or updates from the Ubuntu security team.\n'
            'deb http://archive.ubuntu.com/ubuntu/ '
            'mantic-backports main restricted universe multiverse\n'
            '# deb-src http://archive.ubuntu.com/ubuntu/ '
            'mantic-backports main restricted universe multiverse\n'
            '\n'
            'deb http://security.ubuntu.com/ubuntu/ '
            'mantic-security main restricted\n'
            '# deb-src http://security.ubuntu.com/ubuntu/ '
            'mantic-security main restricted\n'
            'deb http://security.ubuntu.com/ubuntu/ '
            'mantic-security universe\n'
            '# deb-src http://security.ubuntu.com/ubuntu/ '
            'mantic-security universe\n'
            'deb http://security.ubuntu.com/ubuntu/ '
            'mantic-security multiverse\n'
            '# deb-src http://security.ubuntu.com/ubuntu/ '
            'mantic-security multiverse\n'
        )

        expect = (
            'Types: deb\n'
            'URIs: http://archive.ubuntu.com/ubuntu/\n'
            'Suites: mantic mantic-updates mantic-backports\n'
            'Components: main restricted universe multiverse\n'
            'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            '\n'
            'Types: deb\n'
            'URIs: http://security.ubuntu.com/ubuntu/\n'
            'Suites: mantic-security\n'
            'Components: main restricted universe multiverse\n'
            'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
        )

        sources_list = os.path.join(self.target, 'etc/apt/sources.list')
        ubuntu_sources = os.path.join(
            self.target,
            'etc/apt/sources.list.d/ubuntu.sources'
        )

        os.makedirs(os.path.dirname(sources_list), exist_ok=True)
        with open(sources_list, 'w') as f:
            f.write(orig)

        apt_config.generate_sources_list({}, 'mantic', {}, self.target)

        write_file.assert_has_calls([
            mock.call(ubuntu_sources, expect, mode=0o644),
            mock.call(
                sources_list,
                '# Ubuntu sources have moved to '
                '/etc/apt/sources.list.d/ubuntu.sources\n',
                mode=0o644
            )
        ])

        if os.path.exists(sources_list):
            os.remove(sources_list)

    @mock_want_deb822(True)
    def test_apt_src_deb822(self):
        params = self._get_default_params()

        cfg = {
            'test1.sources': {
                'source': (
                    'Types: deb\n'
                    'URIs: http://test.ubuntu.com/ubuntu\n'
                    'Suites: $RELEASE\n'
                    'Components: main universe multiverse restricted\n'
                    'Signed-By: /usr/share/keyrings/keyring.gpg\n'
                ),
            },
            'unset': {
                'source': (
                    'Types: deb\n'
                    'URIs: http://test.ubuntu.com/ubuntu\n'
                    'Suites: jammy-backports\n'
                    'Components: main universe\n'
                ),
                'filename': 'test2.sources',
            },
            '/tmp/test3.sources': {
                'source': (
                    'Types: deb\n'
                    'URIs: $MIRROR\n'
                    'Suites: $RELEASE-backports\n'
                    'Components: main universe multiverse restricted\n'
                ),
            },
            'test4.sources': {
                'source': 'proposed',
            },
            'test5': {
                'source': (
                    'Types: deb-src\n'
                    'URIs: $MIRROR\n'
                    'Suites: $RELEASE $RELEASE-updates\n'
                    'Components: main restricted universe multiverse\n'
                    'Signed-By:\n'
                    ' -----BEGIN PGP PUBLIC KEY BLOCK-----\n'
                    ' .\n'
                    ' zG09Vic7vacENMM/hl6Ms5prLYq0JvykmQIfxTSC6q4MZV35LTZfH3\n'
                    ' lXTJUU8Pu4C7sDlAFhe+1y3Or3dLWNkMigw/3c57xWlStcEF+LPMdX\n'
                    ' gT6CNVGo30+4yunYP3IQFQaTjh9BbnPK66iZhpzsynHZ+daAYD8CX2\n'
                    ' TIsQnGlzozxFiW5pxIiMWAKKC5xGy9MHLqWhsbUUy+dDLN7r58B4pt\n'
                    ' bcQAJ+wzIvCe2qf5C7yveT/ohGfSL1dX9uFK0TbLqIdSaqzmx3t1+S\n'
                    ' MoUgSt1N6mEfT0TSG9AMkRGcyb6uHxOVm05L/BjLDH7ZqFKHkm3d0j\n'
                    ' sTGJerxmpOemf8RAZDwygz5LZ1L5zNfzlkv6beKD60ofBppd28Zxgj\n'
                    ' FQUK6vxZJ19ygbKJDhylNdwjXUaAaCTKnEzzDHGgtUJO22kIFEKk9/\n'
                    ' Te7hBKG2nVYMNBWEWb8Tqh8b1NIYgpwmawcdBjuu6QSnqVIi+YvRmM\n'
                    ' hzaPz2w2nK56ZnCv1f5X0s6MXu9BM7/zLdwEE0K3RHmWvF4G9HN7Xm\n'
                    ' GDY8Gp885LtGdSIXYV4j7NDvEWcuqgPpyQjvpFEB/vDSyqe8yUNGmN\n'
                    ' 10Hv2g9cmkeW0qDiRpDg7nHoFcdUSkAyElzxs++Z8CJMVpzl/TJyJt\n'
                    ' wP8HFWvNcyCGwnk9aYCJRuo+/UgjmQvDnVvoHO+XwrMkjSH7JKJQZv\n'
                    ' vM9FyHYq3n7u3R+ASMBVwxF9yAex9CfwRg/3OhzOnkbDsu9HwEEOrV\n'
                    ' 74fIbGkM3hzws0asNoIV1ec52U1X/NP1W8GT9GRX5OX8uTi\n'
                    ' -----END PGP PUBLIC KEY BLOCK-----\n'
                ),
            },
            'test6': {
                'source': (
                    'deb-src $MIRROR $RELEASE main universe\n'
                ),
            },
            'test7.list': {
                'source': (
                    'deb $MIRROR $RELEASE main universe\n'
                    'deb $MIRROR $RELEASE-updates main universe\n'
                    'deb $SECURITY $RELEASE-security main\n'
                ),
            },
        }

        expect = {
            'test1.sources': (
                'Types: deb\n'
                'URIs: http://test.ubuntu.com/ubuntu\n'
                'Suites: {release}\n'
                'Components: main universe multiverse restricted\n'
                'Signed-By: /usr/share/keyrings/keyring.gpg\n'
            ).format(release=params['RELEASE']),
            'test2.sources': (
                'Types: deb\n'
                'URIs: http://test.ubuntu.com/ubuntu\n'
                'Suites: jammy-backports\n'
                'Components: main universe\n'
            ),
            '/tmp/test3.sources': (
                'Types: deb\n'
                'URIs: {mirror}\n'
                'Suites: {release}-backports\n'
                'Components: main universe multiverse restricted\n'
            ).format(release=params['RELEASE'], mirror=params['MIRROR']),
            'test4.sources': (
                'Types: deb\n'
                'URIs: {mirror}\n'
                'Suites: {release}-proposed\n'
                'Components: main restricted universe multiverse\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            ).format(release=params['RELEASE'], mirror=params['MIRROR']),
            'test5.sources': (
                'Types: deb-src\n'
                'URIs: {mirror}\n'
                'Suites: {release} {release}-updates\n'
                'Components: main restricted universe multiverse\n'
                'Signed-By:\n'
                ' -----BEGIN PGP PUBLIC KEY BLOCK-----\n'
                ' .\n'
                ' zG09Vic7vacENMM/hl6Ms5prLYq0JvykmQIfxTSC6q4MZV35LTZfH3\n'
                ' lXTJUU8Pu4C7sDlAFhe+1y3Or3dLWNkMigw/3c57xWlStcEF+LPMdX\n'
                ' gT6CNVGo30+4yunYP3IQFQaTjh9BbnPK66iZhpzsynHZ+daAYD8CX2\n'
                ' TIsQnGlzozxFiW5pxIiMWAKKC5xGy9MHLqWhsbUUy+dDLN7r58B4pt\n'
                ' bcQAJ+wzIvCe2qf5C7yveT/ohGfSL1dX9uFK0TbLqIdSaqzmx3t1+S\n'
                ' MoUgSt1N6mEfT0TSG9AMkRGcyb6uHxOVm05L/BjLDH7ZqFKHkm3d0j\n'
                ' sTGJerxmpOemf8RAZDwygz5LZ1L5zNfzlkv6beKD60ofBppd28Zxgj\n'
                ' FQUK6vxZJ19ygbKJDhylNdwjXUaAaCTKnEzzDHGgtUJO22kIFEKk9/\n'
                ' Te7hBKG2nVYMNBWEWb8Tqh8b1NIYgpwmawcdBjuu6QSnqVIi+YvRmM\n'
                ' hzaPz2w2nK56ZnCv1f5X0s6MXu9BM7/zLdwEE0K3RHmWvF4G9HN7Xm\n'
                ' GDY8Gp885LtGdSIXYV4j7NDvEWcuqgPpyQjvpFEB/vDSyqe8yUNGmN\n'
                ' 10Hv2g9cmkeW0qDiRpDg7nHoFcdUSkAyElzxs++Z8CJMVpzl/TJyJt\n'
                ' wP8HFWvNcyCGwnk9aYCJRuo+/UgjmQvDnVvoHO+XwrMkjSH7JKJQZv\n'
                ' vM9FyHYq3n7u3R+ASMBVwxF9yAex9CfwRg/3OhzOnkbDsu9HwEEOrV\n'
                ' 74fIbGkM3hzws0asNoIV1ec52U1X/NP1W8GT9GRX5OX8uTi\n'
                ' -----END PGP PUBLIC KEY BLOCK-----\n'
            ).format(release=params['RELEASE'], mirror=params['MIRROR']),
            'test6.sources': (
                'Types: deb-src\n'
                'URIs: {mirror}\n'
                'Suites: {release}\n'
                'Components: main universe\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            ).format(release=params['RELEASE'], mirror=params['MIRROR']),
            'test7.sources': (
                'Types: deb\n'
                'URIs: {mirror}\n'
                'Suites: {release} {release}-updates\n'
                'Components: main universe\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
                '\n'
                'Types: deb\n'
                'URIs: {security}\n'
                'Suites: {release}-security\n'
                'Components: main\n'
                'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
            ).format(
                release=params['RELEASE'],
                mirror=params['MIRROR'],
                security=params['SECURITY']
            ),
        }

        self._add_apt_sources(
            cfg,
            self.target,
            template_params=params,
            aa_repo_match=self.matcher
        )

        for filename, entry in expect.items():
            path = self._sources_filepath(filename)
            self.assertTrue(
                os.path.exists(path),
                f'No such file or directory: {path}'
            )
            contents = load_tfile(path)
            self.assertEqual(
                entry,
                contents,
                '{}\nExpected:\n{}\nActual:\n{}'
                .format(filename, entry, contents)
            )


class TestDebconfSelections(CiTestCase):

    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    def test_no_set_sel_if_none_to_set(self, m_set_sel):
        apt_config.apply_debconf_selections({'foo': 'bar'})
        m_set_sel.assert_not_called()

    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_set_sel_call_has_expected_input(self, m_get_inst, m_set_sel):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1')}
        lines = '\n'.join(data.values()).split('\n')

        m_get_inst.return_value = ["adduser", "apparmor"]
        m_set_sel.return_value = None

        apt_config.apply_debconf_selections({'debconf_selections': data})
        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_set_sel.call_count, 1)

        # assumes called with *args value.
        selections = m_set_sel.call_args_list[0][0][0].decode()

        missing = [line for line in lines
                   if line not in selections.splitlines()]
        self.assertEqual([], missing)

    @mock.patch("curtin.commands.apt_config.dpkg_reconfigure")
    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_reconfigure_if_intersection(self, m_get_inst, m_set_sel,
                                         m_dpkg_r):
        data = {
            'set1': 'pkga pkga/q1 mybool false',
            'set2': ('pkgb\tpkgb/b1\tstr\tthis is a string\n'
                     'pkgc\tpkgc/ip\tstring\t10.0.0.1'),
            'cloud-init': ('cloud-init cloud-init/datasources'
                           'multiselect MAAS')}

        m_set_sel.return_value = None
        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']

        apt_config.apply_debconf_selections({'debconf_selections': data})

        # reconfigure should be called with the intersection
        # of (packages in config, packages installed)
        self.assertEqual(m_dpkg_r.call_count, 1)
        # assumes called with *args (dpkg_reconfigure([a,b,c], target=))
        packages = m_dpkg_r.call_args_list[0][0][0]
        self.assertEqual(set(['cloud-init', 'pkgb']), set(packages))

    @mock.patch("curtin.commands.apt_config.dpkg_reconfigure")
    @mock.patch("curtin.commands.apt_config.debconf_set_selections")
    @mock.patch("curtin.commands.apt_config.distro.get_installed_packages")
    def test_reconfigure_if_no_intersection(self, m_get_inst, m_set_sel,
                                            m_dpkg_r):
        data = {'set1': 'pkga pkga/q1 mybool false'}

        m_get_inst.return_value = ["adduser", "apparmor", "pkgb",
                                   "cloud-init", 'zdog']
        m_set_sel.return_value = None

        apt_config.apply_debconf_selections({'debconf_selections': data})

        self.assertTrue(m_get_inst.called)
        self.assertEqual(m_dpkg_r.call_count, 0)

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_does_reconfigure(self, m_subp):
        target = "/foo-target"

        # due to the way the cleaners are called (via dictionary reference)
        # mocking clean_cloud_init directly does not work.  So we mock
        # the CONFIG_CLEANERS dictionary and assert our cleaner is called.
        ci_cleaner = mock.MagicMock()
        with mock.patch.dict("curtin.commands.apt_config.CONFIG_CLEANERS",
                             values={'cloud-init': ci_cleaner}, clear=True):
            apt_config.dpkg_reconfigure(['pkga', 'cloud-init'],
                                        target=target)
        # cloud-init is actually the only package we have a cleaner for
        # so for now, its the only one that should reconfigured
        self.assertTrue(m_subp.called)
        ci_cleaner.assert_called_with(target)
        self.assertEqual(m_subp.call_count, 1)
        found = m_subp.call_args_list[0][0][0]
        expected = ['dpkg-reconfigure', '--frontend=noninteractive',
                    'cloud-init']
        self.assertEqual(expected, found)

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_not_done_on_no_data(self, m_subp):
        apt_config.dpkg_reconfigure([])
        m_subp.assert_not_called()

    @mock.patch("curtin.commands.apt_config.util.subp")
    def test_dpkg_reconfigure_not_done_if_no_cleaners(self, m_subp):
        apt_config.dpkg_reconfigure(['pkgfoo', 'pkgbar'])
        m_subp.assert_not_called()

# vi: ts=4 expandtab syntax=python
