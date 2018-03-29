# This file is part of curtin. See LICENSE file for copyright and license info.

""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os

import mock
from mock import call
import textwrap
import yaml

from curtin import util
from curtin.commands import apt_config
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


class TestAptSourceConfigSourceList(CiTestCase):
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.new_root = self.tmp_dir()
        # self.patchUtils(self.new_root)

    @staticmethod
    def _apt_source_list(cfg, expected):
        "_apt_source_list - Test rendering from template (generic)"

        arch = util.get_architecture()
        # would fail inside the unittest context
        with mock.patch.object(util, 'get_architecture',
                               return_value=arch) as mockga:
            with mock.patch.object(util, 'write_file') as mockwrite:
                # keep it side effect free and avoid permission errors
                with mock.patch.object(os, 'rename'):
                    # make test independent to executing system
                    with mock.patch.object(util, 'load_file',
                                           return_value=MOCKED_APT_SRC_LIST):
                        with mock.patch.object(util, 'lsb_release',
                                               return_value={'codename':
                                                             'fakerel'}):
                            apt_config.handle_apt(cfg, TARGET)

        mockga.assert_called_with("/")

        cloudfile = '/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg'
        cloudconf = yaml.dump({'apt_preserve_sources_list': True}, indent=1)
        calls = [call(util.target_path(TARGET, '/etc/apt/sources.list'),
                      expected,
                      mode=0o644),
                 call(util.target_path(TARGET, cloudfile),
                      cloudconf,
                      mode=0o644)]
        mockwrite.assert_has_calls(calls)

    def test_apt_source_list(self):
        """test_apt_source_list - Test with neither custom sources nor parms"""
        cfg = {'preserve_sources_list': False}

        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT)

    def test_apt_source_list_psm(self):
        """test_apt_source_list_psm - Test specifying prim+sec mirrors"""
        cfg = {'preserve_sources_list': False,
               'primary': [{'arches': ["default"],
                            'uri': 'http://test.ubuntu.com/ubuntu/'}],
               'security': [{'arches': ["default"],
                             'uri': 'http://testsec.ubuntu.com/ubuntu/'}]}

        self._apt_source_list(cfg, EXPECTED_PRIMSEC_CONTENT)

    def test_apt_srcl_custom(self):
        """test_apt_srcl_custom - Test rendering a custom source template"""
        cfg = yaml.safe_load(YAML_TEXT_CUSTOM_SL)
        target = self.new_root

        arch = util.get_architecture()
        # would fail inside the unittest context
        with mock.patch.object(util, 'get_architecture', return_value=arch):
            with mock.patch.object(util, 'lsb_release',
                                   return_value={'codename': 'fakerel'}):
                apt_config.handle_apt(cfg, target)

        self.assertEqual(
            EXPECTED_CONVERTED_CONTENT,
            util.load_file(util.target_path(target, "/etc/apt/sources.list")))
        cloudfile = util.target_path(
            target, '/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg')
        self.assertEqual({'apt_preserve_sources_list': True},
                         yaml.load(util.load_file(cloudfile)))

    @mock.patch("curtin.util.lsb_release")
    @mock.patch("curtin.util.get_architecture", return_value="amd64")
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
        easl = util.target_path(target, 'etc/apt/sources.list')

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

# vi: ts=4 expandtab syntax=python
