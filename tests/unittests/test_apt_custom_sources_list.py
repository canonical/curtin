""" test_apt_custom_sources_list
Test templating of custom sources list
"""
import logging
import os
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

# the custom and builtin templates converted on mocked fakerel
EXPECTED_CONVERTED_CONTENT = """
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu fakerel main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel main restricted
deb http://archive.ubuntu.com/ubuntu fakerel universe restricted
deb http://archive.ubuntu.com/ubuntu fakerel-security multiverse
# FIND_SOMETHING_SPECIAL
"""

EXPECTED_BASE_CONTENT = ("""
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu fakerel main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel main restricted

## Major bug fix updates produced after the final release of the
## distribution.
deb http://archive.ubuntu.com/ubuntu fakerel-updates main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel universe
deb-src http://archive.ubuntu.com/ubuntu fakerel universe
deb http://archive.ubuntu.com/ubuntu fakerel-updates universe
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb http://archive.ubuntu.com/ubuntu fakerel multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel multiverse
deb http://archive.ubuntu.com/ubuntu fakerel-updates multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel-backports"""
                         """ main restricted universe multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-backports"""
                         """ main restricted universe multiverse

deb http://security.ubuntu.com/ubuntu fakerel-security main restricted
deb-src http://security.ubuntu.com/ubuntu fakerel-security main restricted
deb http://security.ubuntu.com/ubuntu fakerel-security universe
deb-src http://security.ubuntu.com/ubuntu fakerel-security universe
deb http://security.ubuntu.com/ubuntu fakerel-security multiverse
deb-src http://security.ubuntu.com/ubuntu fakerel-security multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu fakerel partner
# deb-src http://archive.canonical.com/ubuntu fakerel partner
""")

EXPECTED_MIRROR_CONTENT = ("""
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu fakerel main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel main restricted

## Major bug fix updates produced after the final release of the
## distribution.
deb http://archive.ubuntu.com/ubuntu fakerel-updates main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel universe
deb-src http://archive.ubuntu.com/ubuntu fakerel universe
deb http://archive.ubuntu.com/ubuntu fakerel-updates universe
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb http://archive.ubuntu.com/ubuntu fakerel multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel multiverse
deb http://archive.ubuntu.com/ubuntu fakerel-updates multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel-backports"""
                           """ main restricted universe multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-backports"""
                           """ main restricted universe multiverse

deb http://archive.ubuntu.com/ubuntu fakerel-security main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel-security main restricted
deb http://archive.ubuntu.com/ubuntu fakerel-security universe
deb-src http://archive.ubuntu.com/ubuntu fakerel-security universe
deb http://archive.ubuntu.com/ubuntu fakerel-security multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-security multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu fakerel partner
# deb-src http://archive.canonical.com/ubuntu fakerel partner
""")

EXPECTED_PRIMSEC_CONTENT = ("""
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://archive.ubuntu.com/ubuntu fakerel main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel main restricted

## Major bug fix updates produced after the final release of the
## distribution.
deb http://archive.ubuntu.com/ubuntu fakerel-updates main restricted
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel universe
deb-src http://archive.ubuntu.com/ubuntu fakerel universe
deb http://archive.ubuntu.com/ubuntu fakerel-updates universe
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb http://archive.ubuntu.com/ubuntu fakerel multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel multiverse
deb http://archive.ubuntu.com/ubuntu fakerel-updates multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb http://archive.ubuntu.com/ubuntu fakerel-backports"""
                            """ main restricted universe multiverse
deb-src http://archive.ubuntu.com/ubuntu fakerel-backports"""
                            """ main restricted universe multiverse

deb http://security.ubuntu.com/ubuntu fakerel-security main restricted
deb-src http://security.ubuntu.com/ubuntu fakerel-security main restricted
deb http://security.ubuntu.com/ubuntu fakerel-security universe
deb-src http://security.ubuntu.com/ubuntu fakerel-security universe
deb http://security.ubuntu.com/ubuntu fakerel-security multiverse
deb-src http://security.ubuntu.com/ubuntu fakerel-security multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu fakerel partner
# deb-src http://archive.canonical.com/ubuntu fakerel partner
""")


def load_tfile_or_url(*args, **kwargs):
    """ load_tfile_or_url
    load file and return content after decoding
    """
    return util.decode_binary(util.read_file_or_url(*args, **kwargs).contents)


class TestAptSourceConfigSourceList(TestCase):
    """TestAptSourceConfigSourceList - Class to test sources list rendering"""
    def setUp(self):
        super(TestAptSourceConfigSourceList, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        # self.patchUtils(self.new_root)

    @staticmethod
    def _apt_source_list(cfg, expected):
        "_apt_source_list - Test rendering from template (generic)"

        with mock.patch.object(util, 'write_file') as mockwrite:
            # keep it side effect free and avoid permission errors
            with mock.patch.object(os, 'rename'):
                with mock.patch.object(util, 'lsb_release',
                                       return_value={'codename': 'fakerel'}):
                    apt_source.handle_apt_source(cfg)

        mockwrite.assert_called_once_with(
            '/etc/apt/sources.list',
            expected,
            mode=420)

    def test_apt_source_list(self):
        """test_apt_source_list - Test builtin sources without parms"""
        cfg = {}

        self._apt_source_list(cfg, EXPECTED_BASE_CONTENT)

    def test_apt_source_list_mirror(self):
        """test_apt_source_list_mirror - Test builtin sources with mirror"""
        cfg = {'apt_mirror': 'http://archive.ubuntu.com/ubuntu'}
        self._apt_source_list(cfg, EXPECTED_MIRROR_CONTENT)

    def test_apt_source_list_psm(self):
        """test_apt_source_list_psm - Test builtin with prim+sec mirrors"""
        cfg = {'apt_primary_mirror': 'http://archive.ubuntu.com/ubuntu',
               'apt_security_mirror': 'http://security.ubuntu.com/ubuntu'}

        self._apt_source_list(cfg, EXPECTED_PRIMSEC_CONTENT)

    @staticmethod
    def test_apt_srcl_custom():
        """test_apt_srcl_custom - Test rendering a custom source template"""
        cfg = yaml.safe_load(YAML_TEXT_CUSTOM_SL)

        with mock.patch.object(util, 'write_file') as mockwrite:
            # keep it side effect free and avoid permission errors
            with mock.patch.object(os, 'rename'):
                with mock.patch.object(util, 'lsb_release',
                                       return_value={'codename': 'fakerel'}):
                    apt_source.handle_apt_source(cfg)

        mockwrite.assert_called_once_with(
            '/etc/apt/sources.list',
            EXPECTED_CONVERTED_CONTENT,
            mode=420)


# vi: ts=4 expandtab
