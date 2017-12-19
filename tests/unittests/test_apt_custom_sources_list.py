""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os


import yaml
import mock
from mock import call

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

    @staticmethod
    def test_apt_srcl_custom():
        """test_apt_srcl_custom - Test rendering a custom source template"""
        cfg = yaml.safe_load(YAML_TEXT_CUSTOM_SL)

        arch = util.get_architecture()
        # would fail inside the unittest context
        with mock.patch.object(util, 'get_architecture',
                               return_value=arch) as mockga:
            with mock.patch.object(util, 'write_file') as mockwrite:
                # keep it side effect free and avoid permission errors
                with mock.patch.object(os, 'rename'):
                    with mock.patch.object(util, 'lsb_release',
                                           return_value={'codename':
                                                         'fakerel'}):
                        apt_config.handle_apt(cfg, TARGET)

        mockga.assert_called_with("/")
        cloudfile = '/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg'
        cloudconf = yaml.dump({'apt_preserve_sources_list': True}, indent=1)
        calls = [call(util.target_path(TARGET, '/etc/apt/sources.list'),
                      EXPECTED_CONVERTED_CONTENT, mode=0o644),
                 call(util.target_path(TARGET, cloudfile), cloudconf,
                      mode=0o644)]
        mockwrite.assert_has_calls(calls)


# vi: ts=4 expandtab
