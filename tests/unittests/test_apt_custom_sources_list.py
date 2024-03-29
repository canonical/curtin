# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os
import yaml

from unittest import mock
from unittest.mock import call
import textwrap

from curtin import distro
from curtin import paths
from curtin import util
from curtin.commands import apt_config
from curtin.config import load_config
from .helpers import CiTestCase

LOG = logging.getLogger(__name__)

TARGET = "/"

# Input and expected output for the custom template
YAML_TEXT_CUSTOM_SL = """
preserve_sources_list: false
primary:
  - arches: [default]
    uri: http://test.ubuntu.com/ubuntu/
security:
  - arches: [default]
    uri: http://testsec.ubuntu.com/ubuntu/
sources_list: |

    ## Note, this file is written by curtin at install time. It should not end
    ## up on the installed system itself.
    #
    # See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
    # newer versions of the distribution.
    deb $MIRROR $RELEASE main restricted
    deb-src $MIRROR $RELEASE main restricted
    deb $PRIMARY $RELEASE universe restricted
    deb $SECURITY $RELEASE-security multiverse
    # FIND_SOMETHING_SPECIAL
"""

EXPECTED_CONVERTED_CONTENT = """
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb-src http://test.ubuntu.com/ubuntu/ fakerel main restricted
deb http://test.ubuntu.com/ubuntu/ fakerel universe restricted
deb http://testsec.ubuntu.com/ubuntu/ fakerel-security multiverse
# FIND_SOMETHING_SPECIAL
"""

# Input and expected output for the custom template with deb822 sources
YAML_TEXT_CUSTOM_SL_DEB822 = """
preserve_sources_list: false
primary:
  - arches: [default]
    uri: http://test.ubuntu.com/ubuntu/
security:
  - arches: [default]
    uri: http://testsec.ubuntu.com/ubuntu/
sources_list: |
    Types: deb deb-src
    URIs: $MIRROR
    Suites: $RELEASE
    Components: main restricted
    Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

    Types: deb
    URIs: $MIRROR
    Suites: $RELEASE
    Components: restricted universe
    Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

    Types: deb
    URIs: $SECURITY
    Suites: $RELEASE-security
    Components: multiverse
    Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""

EXPECTED_CONVERTED_CONTENT_DEB822 = """Types: deb deb-src
URIs: http://test.ubuntu.com/ubuntu/
Suites: fakerel
Components: main restricted
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://test.ubuntu.com/ubuntu/
Suites: fakerel
Components: restricted universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://testsec.ubuntu.com/ubuntu/
Suites: fakerel-security
Components: multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""

# mocked to be independent to the unittest system
MOCKED_APT_SRC_LIST = """
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
"""

EXPECTED_BASE_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
""")

EXPECTED_MIRROR_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-security main restricted
""")

EXPECTED_PRIMSEC_CONTENT = ("""
deb http://test.ubuntu.com/ubuntu/ notouched main restricted
deb-src http://test.ubuntu.com/ubuntu/ notouched main restricted
deb http://test.ubuntu.com/ubuntu/ notouched-updates main restricted
deb http://testsec.ubuntu.com/ubuntu/ notouched-security main restricted
""")


def mock_want_deb822(return_value):
    def inner(test_func):
        def patched_test_func(*args, **kwargs):
            with mock.patch('curtin.commands.apt_config.want_deb822') as m:
                m.return_value = return_value
                test_func(*args, **kwargs)

        return patched_test_func

    return inner


class TestAptSourceConfigSourceList(CiTestCase):
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.new_root = self.tmp_dir()
        self.add_patch('curtin.util.subp', 'm_subp')
        # self.patchUtils(self.new_root)
        self.m_subp.return_value = ("amd64", "")

    def _apt_source_list(self, cfg, expected):
        "_apt_source_list - Test rendering from template (generic)"

        arch = distro.get_architecture()
        # would fail inside the unittest context
        bpath = "curtin.commands.apt_config."
        upath = bpath + "util."
        dpath = bpath + 'distro.'
        self.add_patch(dpath + "get_architecture", "mockga", return_value=arch)
        self.add_patch(upath + "write_file", "mockwrite")
        self.add_patch(bpath + "os.rename", "mockrename")
        self.add_patch(upath + "load_file", "mockload_file",
                       return_value=MOCKED_APT_SRC_LIST)
        self.add_patch(bpath + "distro.lsb_release", "mock_lsb_release",
                       return_value={'codename': 'fakerel'})
        self.add_patch(bpath + "apply_preserve_sources_list",
                       "mock_apply_preserve_sources_list")

        apt_config.handle_apt(cfg, TARGET)

        self.mockga.assert_called_with(TARGET)
        self.mock_apply_preserve_sources_list.assert_called_with(TARGET)
        calls = [call(paths.target_path(TARGET, '/etc/apt/sources.list'),
                      expected, mode=0o644)]
        self.mockwrite.assert_has_calls(calls)

    @mock_want_deb822(False)
    def test_apt_source_list(self):
        """test_apt_source_list - Test with neither custom sources nor parms"""
        cfg = {'preserve_sources_list': False}

        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT)

    @mock_want_deb822(False)
    def test_apt_source_list_psm(self):
        """test_apt_source_list_psm - Test specifying prim+sec mirrors"""
        cfg = {'preserve_sources_list': False,
               'primary': [{'arches': ["default"],
                            'uri': 'http://test.ubuntu.com/ubuntu/'}],
               'security': [{'arches': ["default"],
                             'uri': 'http://testsec.ubuntu.com/ubuntu/'}]}

        self._apt_source_list(cfg, EXPECTED_PRIMSEC_CONTENT)

    @mock_want_deb822(False)
    def test_apt_srcl_custom(self):
        """test_apt_srcl_custom - Test rendering a custom source template"""
        cfg = yaml.safe_load(YAML_TEXT_CUSTOM_SL)
        target = self.new_root

        arch = distro.get_architecture()
        # would fail inside the unittest context
        with mock.patch.object(distro, 'get_architecture', return_value=arch):
            with mock.patch.object(distro, 'lsb_release',
                                   return_value={'codename': 'fakerel'}):
                apt_config.handle_apt(cfg, target)

        self.assertEqual(
            EXPECTED_CONVERTED_CONTENT,
            util.load_file(paths.target_path(target, "/etc/apt/sources.list")))

    @mock_want_deb822(False)
    @mock.patch("curtin.distro.lsb_release")
    @mock.patch("curtin.distro.get_architecture", return_value="amd64")
    def test_trusty_source_lists(self, m_get_arch, m_lsb_release):
        """Support mirror equivalency with and without trailing /.

        Trusty official images do not have a trailing slash on
            http://archive.ubuntu.com/ubuntu ."""

        orig_primary = apt_config.PRIMARY_ARCH_MIRRORS['PRIMARY']
        orig_security = apt_config.PRIMARY_ARCH_MIRRORS['SECURITY']
        msg = "Test is invalid. %s mirror does not end in a /."
        self.assertEqual(orig_primary[-1], "/", msg % "primary")
        self.assertEqual(orig_security[-1], "/", msg % "security")
        orig_primary = orig_primary[:-1]
        orig_security = orig_security[:-1]

        m_lsb_release.return_value = {
            'codename': 'trusty', 'description': 'Ubuntu 14.04.5 LTS',
            'id': 'Ubuntu', 'release': '14.04'}

        target = self.new_root
        my_primary = 'http://fixed-primary.ubuntu.com/ubuntu'
        my_security = 'http://fixed-security.ubuntu.com/ubuntu'
        cfg = {
            'preserve_sources_list': False,
            'primary': [{'arches': ['amd64'], 'uri': my_primary}],
            'security': [{'arches': ['amd64'], 'uri': my_security}]}

        # this is taken from a trusty image /etc/apt/sources.list
        tmpl = textwrap.dedent("""\
            deb {mirror} {release} {comps}
            deb {mirror} {release}-updates {comps}
            deb {mirror} {release}-backports {comps}
            deb {security} {release}-security {comps}
            # not modified
            deb http://my.example.com/updates testing main
            """)

        release = 'trusty'
        comps = 'main universe multiverse restricted'
        easl = paths.target_path(target, 'etc/apt/sources.list')

        orig_content = tmpl.format(
            mirror=orig_primary, security=orig_security,
            release=release, comps=comps)
        orig_content_slash = tmpl.format(
            mirror=orig_primary + "/", security=orig_security + "/",
            release=release, comps=comps)
        expected = tmpl.format(
            mirror=my_primary, security=my_security,
            release=release, comps=comps)

        # Avoid useless test. Make sure the strings don't start out equal.
        self.assertNotEqual(expected, orig_content)

        util.write_file(easl, orig_content)
        apt_config.handle_apt(cfg, target)
        self.assertEqual(expected, util.load_file(easl))

        util.write_file(easl, orig_content_slash)
        apt_config.handle_apt(cfg, target)
        self.assertEqual(expected, util.load_file(easl))

    @mock_want_deb822(True)
    def test_apt_srcl_custom_deb22(self):
        # Test both deb822 input and migration from classic sources.
        for custom in (YAML_TEXT_CUSTOM_SL, YAML_TEXT_CUSTOM_SL_DEB822):
            cfg = yaml.safe_load(custom)
            target = self.new_root

            arch = distro.get_architecture()
            # would fail inside the unittest context
            with mock.patch.object(
                distro,
                'get_architecture',
                return_value=arch
            ):
                with mock.patch.object(distro, 'lsb_release',
                                       return_value={'codename': 'fakerel'}):
                    apt_config.handle_apt(cfg, target)

            self.assertEqual(
                EXPECTED_CONVERTED_CONTENT_DEB822,
                util.load_file(
                    paths.target_path(
                        target,
                        "/etc/apt/sources.list.d/ubuntu.sources"
                    )
                )
            )


class TestApplyPreserveSourcesList(CiTestCase):
    """Test apply_preserve_sources_list."""

    cloudfile = "/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg"

    def setUp(self):
        super(TestApplyPreserveSourcesList, self).setUp()
        self.tmp = self.tmp_dir()
        self.tmp_cfg = self.tmp_path(self.cloudfile, self.tmp)

    @mock.patch("curtin.commands.apt_config.distro.get_package_version")
    def test_old_cloudinit_version(self, m_get_pkg_ver):
        """Test installed old cloud-init version."""
        m_get_pkg_ver.return_value = distro.parse_dpkg_version('0.7.7-0')
        apt_config.apply_preserve_sources_list(self.tmp)
        m_get_pkg_ver.assert_has_calls(
            [mock.call('cloud-init', target=self.tmp)])
        self.assertEqual(
            load_config(self.tmp_cfg),
            {'apt_preserve_sources_list': True})

    @mock.patch("curtin.commands.apt_config.distro.get_package_version")
    def test_no_cloudinit(self, m_get_pkg_ver):
        """Test where cloud-init is not installed."""
        m_get_pkg_ver.return_value = None
        apt_config.apply_preserve_sources_list(self.tmp)
        m_get_pkg_ver.assert_has_calls(
            [mock.call('cloud-init', target=self.tmp)])
        self.assertFalse(os.path.exists(self.tmp_cfg))

    @mock.patch("curtin.commands.apt_config.distro.get_package_version")
    def test_new_cloudinit_version(self, m_get_pkg_ver):
        """Test cloud-init > 1.0 with new apt format."""
        m_get_pkg_ver.return_value = distro.parse_dpkg_version('17.1-0ubuntu1')
        apt_config.apply_preserve_sources_list(self.tmp)
        m_get_pkg_ver.assert_has_calls(
            [mock.call('cloud-init', target=self.tmp)])
        self.assertEqual(
            load_config(self.tmp_cfg),
            {'apt': {'preserve_sources_list': True}})

# vi: ts=4 expandtab syntax=python
