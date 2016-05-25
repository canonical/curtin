""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import shutil
import tempfile
import yaml

from unittest import TestCase

try:
    from unittest import mock
except ImportError:
    import mock

from curtin import util
from curtin.commands import apt_source

LOG = logging.getLogger(__name__)

YAML_TEXT_CUSTOM_SL = """
apt_mirror: http://archive.ubuntu.com/ubuntu
apt_custom_sources_list: |
    ## template:jinja
    ## Note, this file is written by cloud-init on first boot of an instance
    ## modifications made here will not survive a re-bundle.
    ## if you wish to make changes you can:
    ## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
    ##     or do the same in user-data
    ## b.) add sources in /etc/apt/sources.list.d
    ## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

    # See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
    # newer versions of the distribution.
    deb {{mirror}} {{codename}} main restricted
    deb-src {{mirror}} {{codename}} main restricted
    deb {{primary}} {{codename}} universe restricted
    deb {{security}} {{codename}}-security multiverse
    # FIND_SOMETHING_SPECIAL
"""

# the custom template above converted on mocked fakerelease
EXPECTED_CONVERTED_CONTENT = (
    """## Note, this file is written by cloud-init on first boot of an instance
## modifications made here will not survive a re-bundle.
## if you wish to make changes you can:
## a.) add 'apt_preserve_sources_list: true' to /etc/cloud/cloud.cfg
##     or do the same in user-data
## b.) add sources in /etc/apt/sources.list.d
## c.) make changes to template file /etc/cloud/templates/sources.list.tmpl

# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu fakerelease main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerelease main restricted
deb http://archive.ubuntu.com/ubuntu xenial universe restricted
deb http://archive.ubuntu.com/ubuntu xenial-security multiverse
# FIND_SOMETHING_SPECIAL
""")

EXPECTED_BASE_CONTENT = ""
EXPECTED_MIRROR_CONTENT = ""
EXPECTED_PRIMSEC_CONTENT = ""


def load_tfile_or_url(*args, **kwargs):
    """ load_tfile_or_url
    load file and return content after decoding
    """
    return util.decode_binary(util.read_file_or_url(*args, **kwargs).contents)


class TestAptSourceConfigSourceList(TestCase):
    """ TestAptSourceConfigSourceList
    Main Class to test sources list rendering
    """
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.subp = util.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        # self.patchUtils(self.new_root)

    def _apt_source_list(self, cfg, expected):
        """ test_apt_source_list
        Test rendering from template
        """

        with mock.patch.object(util, 'write_file') as mockwrite:
            with mock.patch.object(util, 'subp', self.subp):
                apt_source.handle_apt_source(cfg)

        mockwrite.assert_called_once_with(
            '/etc/apt/sources.list',
            expected,
            mode=420)

    def test_apt_source_list(self):
        """ test_apt_source_list
        Test rendering of default a source.list without extra parms
        """
        cfg = {}

        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT)

    def test_apt_source_list_mirror(self):
        """ test_apt_source_list_mirror
        Test rendering of default source.list with mirrors set
        """
        cfg = {'apt_mirror': 'http://archive.ubuntu.com/ubuntu'}
        self._apt_source_list(cfg, EXPECTED_MIRROR_CONTENT)

    def test_apt_source_list_psmirrors(self):
        """ test_apt_source_list_psmirrors
        Test rendering of default source.list with prim+sec mirrors set
        """
        cfg = {'apt_primary_mirror': 'http://archive.ubuntu.com/ubuntu',
               'apt_security_mirror': 'http://security.ubuntu.com/ubuntu'}

        self._apt_source_list(cfg, EXPECTED_PRIMSEC_CONTENT)

    def test_apt_srcl_custom(self):
        """ test_apt_srcl_custom
        Test rendering from a custom source.list template
        """
        cfg = yaml.safe_load(YAML_TEXT_CUSTOM_SL)

        # the second mock restores the original subp
        with mock.patch.object(util, 'write_file') as mockwrite:
            with mock.patch.object(util, 'subp', self.subp):
                with mock.patch.object(apt_source, 'get_release',
                                       return_value='fakerelease'):
                    apt_source.handle_apt_source(cfg)

        mockwrite.assert_called_once_with(
            '/etc/apt/sources.list',
            EXPECTED_CONVERTED_CONTENT,
            mode=420)


# vi: ts=4 expandtab
