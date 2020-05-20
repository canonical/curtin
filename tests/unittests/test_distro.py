# This file is part of curtin. See LICENSE file for copyright and license info.

from unittest import skipIf
import mock
import sys

from curtin import distro
from curtin import paths
from curtin import util
from .helpers import CiTestCase


class TestLsbRelease(CiTestCase):

    def setUp(self):
        super(TestLsbRelease, self).setUp()
        self._reset_cache()

    def _reset_cache(self):
        keys = [k for k in distro._LSB_RELEASE.keys()]
        for d in keys:
            del distro._LSB_RELEASE[d]

    @mock.patch("curtin.distro.subp")
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
        found = distro.lsb_release()
        mock_subp.assert_called_with(
            ['lsb_release', '--all'], capture=True, target=None)
        self.assertEqual(found, rdata)

    @mock.patch("curtin.distro.subp")
    def test_lsb_release_unavailable(self, mock_subp):
        def doraise(*args, **kwargs):
            raise util.ProcessExecutionError("foo")
        mock_subp.side_effect = doraise

        expected = {k: "UNAVAILABLE" for k in
                    ('id', 'description', 'codename', 'release')}
        self.assertEqual(distro.lsb_release(), expected)


class TestParseDpkgVersion(CiTestCase):
    """test parse_dpkg_version."""

    def test_none_raises_type_error(self):
        self.assertRaises(TypeError, distro.parse_dpkg_version, None)

    @skipIf(sys.version_info.major < 3, "python 2 bytes are strings.")
    def test_bytes_raises_type_error(self):
        self.assertRaises(TypeError, distro.parse_dpkg_version, b'1.2.3-0')

    def test_simple_native_package_version(self):
        """dpkg versions must have a -. If not present expect value error."""
        self.assertEqual(
            {'major': 2, 'minor': 28, 'micro': 0, 'extra': None,
             'raw': '2.28', 'upstream': '2.28', 'name': 'germinate',
             'semantic_version': 22800},
            distro.parse_dpkg_version('2.28', name='germinate'))

    def test_complex_native_package_version(self):
        dver = '1.0.106ubuntu2+really1.0.97ubuntu1'
        self.assertEqual(
            {'major': 1, 'minor': 0, 'micro': 106,
             'extra': 'ubuntu2+really1.0.97ubuntu1',
             'raw': dver, 'upstream': dver, 'name': 'debootstrap',
             'semantic_version': 100106},
            distro.parse_dpkg_version(dver, name='debootstrap',
                                      semx=(100000, 1000, 1)))

    def test_simple_valid(self):
        self.assertEqual(
            {'major': 1, 'minor': 2, 'micro': 3, 'extra': None,
             'raw': '1.2.3-0', 'upstream': '1.2.3', 'name': 'foo',
             'semantic_version': 10203},
            distro.parse_dpkg_version('1.2.3-0', name='foo'))

    def test_simple_valid_with_semx(self):
        self.assertEqual(
            {'major': 1, 'minor': 2, 'micro': 3, 'extra': None,
             'raw': '1.2.3-0', 'upstream': '1.2.3',
             'semantic_version': 123},
            distro.parse_dpkg_version('1.2.3-0', semx=(100, 10, 1)))

    def test_upstream_with_hyphen(self):
        """upstream versions may have a hyphen."""
        cver = '18.2-14-g6d48d265-0ubuntu1'
        self.assertEqual(
            {'major': 18, 'minor': 2, 'micro': 0, 'extra': '-14-g6d48d265',
             'raw': cver, 'upstream': '18.2-14-g6d48d265',
             'name': 'cloud-init', 'semantic_version': 180200},
            distro.parse_dpkg_version(cver, name='cloud-init'))

    def test_upstream_with_plus(self):
        """multipath tools has a + in it."""
        mver = '0.5.0+git1.656f8865-5ubuntu2.5'
        self.assertEqual(
            {'major': 0, 'minor': 5, 'micro': 0, 'extra': '+git1.656f8865',
             'raw': mver, 'upstream': '0.5.0+git1.656f8865',
             'semantic_version': 500},
            distro.parse_dpkg_version(mver))


class TestDistros(CiTestCase):

    def test_distro_names(self):
        all_distros = list(distro.DISTROS)
        for distro_name in distro.DISTRO_NAMES:
            distro_enum = getattr(distro.DISTROS, distro_name)
            self.assertIn(distro_enum, all_distros)

    def test_distro_names_unknown(self):
        distro_name = "ImNotADistro"
        self.assertNotIn(distro_name, distro.DISTRO_NAMES)
        with self.assertRaises(AttributeError):
            getattr(distro.DISTROS, distro_name)

    def test_distro_osfamily(self):
        for variant, family in distro.OS_FAMILIES.items():
            self.assertNotEqual(variant, family)
            self.assertIn(variant, distro.DISTROS)
            for dname in family:
                self.assertIn(dname, distro.DISTROS)

    def test_distro_osfmaily_identity(self):
        for family, variants in distro.OS_FAMILIES.items():
            self.assertIn(family, variants)

    def test_name_to_distro(self):
        for distro_name in distro.DISTRO_NAMES:
            dobj = distro.name_to_distro(distro_name)
            self.assertEqual(dobj, getattr(distro.DISTROS, distro_name))

    def test_name_to_distro_unknown_value(self):
        with self.assertRaises(ValueError):
            distro.name_to_distro(None)

    def test_name_to_distro_unknown_attr(self):
        with self.assertRaises(ValueError):
            distro.name_to_distro('NotADistro')

    def test_distros_unknown_attr(self):
        with self.assertRaises(AttributeError):
            distro.DISTROS.notadistro

    def test_distros_unknown_index(self):
        with self.assertRaises(IndexError):
            distro.DISTROS[len(distro.DISTROS)+1]


class TestDistroInfo(CiTestCase):

    def setUp(self):
        super(TestDistroInfo, self).setUp()
        self.add_patch('curtin.distro.os_release', 'mock_os_release')

    def test_get_distroinfo(self):
        for distro_name in distro.DISTRO_NAMES:
            self.mock_os_release.return_value = {'ID': distro_name}
            variant = distro.name_to_distro(distro_name)
            family = distro.DISTRO_TO_OSFAMILY[variant]
            distro_info = distro.get_distroinfo()
            self.assertEqual(variant, distro_info.variant)
            self.assertEqual(family, distro_info.family)

    def test_get_distro(self):
        for distro_name in distro.DISTRO_NAMES:
            self.mock_os_release.return_value = {'ID': distro_name}
            variant = distro.name_to_distro(distro_name)
            distro_obj = distro.get_distro()
            self.assertEqual(variant, distro_obj)

    def test_get_osfamily(self):
        for distro_name in distro.DISTRO_NAMES:
            self.mock_os_release.return_value = {'ID': distro_name}
            variant = distro.name_to_distro(distro_name)
            family = distro.DISTRO_TO_OSFAMILY[variant]
            distro_obj = distro.get_osfamily()
            self.assertEqual(family, distro_obj)


class TestDistroIdentity(CiTestCase):

    ubuntu_core_os_path_side_effects = [
        [True, True, True],
        [True, True, False],
        [True, False, True],
        [True, False, False],
        [False, True, True],
        [False, True, False],
        [False, False, True],
    ]

    def setUp(self):
        super(TestDistroIdentity, self).setUp()
        self.add_patch('curtin.distro.os.path.exists', 'mock_os_path')

    def test_is_ubuntu_core_16(self):
        for exists in [True, False]:
            self.mock_os_path.return_value = exists
            self.assertEqual(exists, distro.is_ubuntu_core_16())
            self.mock_os_path.assert_called_with('/system-data/var/lib/snapd')

    def test_is_ubuntu_core_18(self):
        for exists in [True, False]:
            self.mock_os_path.return_value = exists
            self.assertEqual(exists, distro.is_ubuntu_core_18())
            self.mock_os_path.assert_called_with('/system-data/var/lib/snapd')

    def test_is_ubuntu_core_is_core20(self):
        for exists in [True, False]:
            self.mock_os_path.return_value = exists
            self.assertEqual(exists, distro.is_ubuntu_core_20())
            self.mock_os_path.assert_called_with('/snaps')

    def test_is_ubuntu_core_true(self):
        side_effects = self.ubuntu_core_os_path_side_effects
        for true_effect in side_effects:
            self.mock_os_path.side_effect = iter(true_effect)
            self.assertTrue(distro.is_ubuntu_core())

        expected_calls = [
            mock.call('/system-data/var/lib/snapd'),
            mock.call('/system-data/var/lib/snapd'),
            mock.call('/snaps')]
        expected_nr_calls = len(side_effects) * len(expected_calls)
        self.assertEqual(expected_nr_calls, self.mock_os_path.call_count)
        self.mock_os_path.assert_has_calls(
            expected_calls * len(side_effects))

    def test_is_ubuntu_core_false(self):
        self.mock_os_path.return_value = False
        self.assertFalse(distro.is_ubuntu_core())

        expected_calls = [
            mock.call('/system-data/var/lib/snapd'),
            mock.call('/system-data/var/lib/snapd'),
            mock.call('/snaps')]
        expected_nr_calls = 3
        self.assertEqual(expected_nr_calls, self.mock_os_path.call_count)
        self.mock_os_path.assert_has_calls(expected_calls)

    def test_is_centos(self):
        for exists in [True, False]:
            self.mock_os_path.return_value = exists
            self.assertEqual(exists, distro.is_centos())
            self.mock_os_path.assert_called_with('/etc/centos-release')

    def test_is_rhel(self):
        for exists in [True, False]:
            self.mock_os_path.return_value = exists
            self.assertEqual(exists, distro.is_rhel())
            self.mock_os_path.assert_called_with('/etc/redhat-release')


class TestYumInstall(CiTestCase):

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.util.subp')
    def test_yum_install(self, m_subp):
        pkglist = ['foobar', 'wark']
        target = 'mytarget'
        mode = 'install'
        expected_calls = [
            mock.call(['yum', '--assumeyes', '--quiet', 'install',
                       '--downloadonly', '--setopt=keepcache=1'] + pkglist,
                      env=None, retries=[1] * 10,
                      target=paths.target_path(target)),
            mock.call(['yum', '--assumeyes', '--quiet', 'install',
                       '--cacheonly'] + pkglist, env=None,
                      target=paths.target_path(target))
        ]

        # call yum_install directly
        self.assertFalse(m_subp.called)
        distro.yum_install(mode, pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call yum_install through run_yum_command; expect the same calls
        # so clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        distro.run_yum_command('install', pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call yum_install through install_packages; expect the same calls
        # so clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        osfamily = distro.DISTROS.redhat
        distro.install_packages(pkglist, osfamily=osfamily, target=target)
        m_subp.assert_has_calls(expected_calls)

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.util.subp')
    @mock.patch('curtin.distro.which')
    def test_dnf_install(self, m_which, m_subp):
        pkglist = ['foobar', 'wark']
        target = 'mytarget'
        mode = 'install'
        m_which.return_value = '/usr/bin/dnf'
        expected_calls = [
            mock.call(['dnf', '--assumeyes', '--quiet', 'install',
                       '--downloadonly', '--setopt=keepcache=1'] + pkglist,
                      env=None, retries=[1] * 10,
                      target=paths.target_path(target)),
            mock.call(['dnf', '--assumeyes', '--quiet', 'install',
                       '--cacheonly'] + pkglist, env=None,
                      target=paths.target_path(target))
        ]

        # call yum_install directly
        self.assertFalse(m_subp.called)
        distro.yum_install(mode, pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call yum_install through run_yum_command; expect the same calls
        # so clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        distro.run_yum_command('install', pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call yum_install through install_packages; expect the same calls
        # so clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        osfamily = distro.DISTROS.redhat
        distro.install_packages(pkglist, osfamily=osfamily, target=target)
        m_subp.assert_has_calls(expected_calls)


class TestSystemUpgrade(CiTestCase):

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.util.subp')
    def test_system_upgrade_redhat(self, m_subp):
        """system_upgrade osfamily=redhat calls run_yum_command mode=upgrade"""
        osfamily = distro.DISTROS.redhat
        target = 'mytarget'
        mode = 'upgrade'
        pkglist = []
        expected_calls = [
            mock.call(['yum', '--assumeyes', '--quiet', mode,
                       '--downloadonly', '--setopt=keepcache=1'] + pkglist,
                      env=None, retries=[1] * 10,
                      target=paths.target_path(target)),
            mock.call(['yum', '--assumeyes', '--quiet', mode,
                       '--cacheonly'] + pkglist, env=None,
                      target=paths.target_path(target))
        ]
        # call system_upgrade via osfamily; note that we expect the same calls
        # call system_upgrade via osfamily; note that we expect the same calls

        # call yum_install through run_yum_command
        distro.run_yum_command(mode, pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call system_upgrade via osfamily; note that we expect the same calls
        # but to prevent a false positive we clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        distro.system_upgrade(target=target, osfamily=osfamily)
        m_subp.assert_has_calls(expected_calls)

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.util.subp')
    @mock.patch('curtin.distro.which')
    def test_system_upgrade_redhat_dnf(self, m_which, m_subp):
        """system_upgrade osfamily=redhat calls run_yum_command mode=upgrade"""
        osfamily = distro.DISTROS.redhat
        target = 'mytarget'
        mode = 'upgrade'
        m_which.return_value = '/usr/bin/dnf'
        pkglist = []
        expected_calls = [
            mock.call(['dnf', '--assumeyes', '--quiet', mode,
                       '--downloadonly', '--setopt=keepcache=1'] + pkglist,
                      env=None, retries=[1] * 10,
                      target=paths.target_path(target)),
            mock.call(['dnf', '--assumeyes', '--quiet', mode,
                       '--cacheonly'] + pkglist, env=None,
                      target=paths.target_path(target))
        ]
        # call system_upgrade via osfamily; note that we expect the same calls
        # call system_upgrade via osfamily; note that we expect the same calls

        # call yum_install through run_yum_command
        distro.run_yum_command(mode, pkglist, target=target)
        m_subp.assert_has_calls(expected_calls)

        # call system_upgrade via osfamily; note that we expect the same calls
        # but to prevent a false positive we clear m_subp's call stack.
        m_subp.reset_mock()
        self.assertFalse(m_subp.called)
        distro.system_upgrade(target=target, osfamily=osfamily)
        m_subp.assert_has_calls(expected_calls)

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.distro.os.environ')
    @mock.patch('curtin.distro.apt_update')
    @mock.patch('curtin.distro.which')
    @mock.patch('curtin.util.subp')
    def test_system_upgrade_debian(self, m_subp, m_which, m_apt_update, m_env):
        """system_upgrade osfamily=debian calls run_apt_command mode=upgrade"""
        osfamily = distro.DISTROS.debian
        target = 'mytarget'
        m_env.copy.return_value = {}
        m_which.return_value = None
        env = {'DEBIAN_FRONTEND': 'noninteractive'}
        pkglist = []
        apt_base = [
            'apt-get', '--quiet', '--assume-yes',
            '--option=Dpkg::options::=--force-unsafe-io',
            '--option=Dpkg::Options::=--force-confold']
        apt_cmd = apt_base + ['dist-upgrade'] + pkglist
        auto_remove = apt_base + ['autoremove']
        expected_calls = [
            mock.call(apt_cmd, env=env, target=paths.target_path(target)),
            mock.call(auto_remove, env=env, target=paths.target_path(target)),
        ]
        which_calls = [mock.call('eatmydata', target=target)]
        apt_update_calls = [
            mock.call(target, env=env, comment=' '.join(apt_cmd))]

        distro.system_upgrade(target=target, osfamily=osfamily)
        m_which.assert_has_calls(which_calls)
        m_apt_update.assert_has_calls(apt_update_calls)
        m_subp.assert_has_calls(expected_calls)


class TestHasPkgAvailable(CiTestCase):

    def setUp(self):
        super(TestHasPkgAvailable, self).setUp()
        self.package = 'foobar'
        self.target = paths.target_path('mytarget')

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.distro.subp')
    def test_has_pkg_available_debian(self, m_subp):
        osfamily = distro.DISTROS.debian
        m_subp.return_value = (self.package, '')
        result = distro.has_pkg_available(self.package, self.target, osfamily)
        self.assertTrue(result)
        m_subp.assert_has_calls([mock.call(['apt-cache', 'pkgnames'],
                                           capture=True,
                                           target=self.target)])

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.distro.subp')
    def test_has_pkg_available_debian_returns_false_not_avail(self, m_subp):
        pkg = 'wark'
        osfamily = distro.DISTROS.debian
        m_subp.return_value = (pkg, '')
        result = distro.has_pkg_available(self.package, self.target, osfamily)
        self.assertEqual(pkg == self.package, result)
        m_subp.assert_has_calls([mock.call(['apt-cache', 'pkgnames'],
                                           capture=True,
                                           target=self.target)])

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.distro.run_yum_command')
    def test_has_pkg_available_redhat(self, m_subp):
        osfamily = distro.DISTROS.redhat
        m_subp.return_value = (self.package, '')
        result = distro.has_pkg_available(self.package, self.target, osfamily)
        self.assertTrue(result)
        m_subp.assert_has_calls([mock.call('list', opts=['--cacheonly'])])

    @mock.patch.object(util.ChrootableTarget, "__enter__", new=lambda a: a)
    @mock.patch('curtin.distro.run_yum_command')
    def test_has_pkg_available_redhat_returns_false_not_avail(self, m_subp):
        pkg = 'wark'
        osfamily = distro.DISTROS.redhat
        m_subp.return_value = (pkg, '')
        result = distro.has_pkg_available(self.package, self.target, osfamily)
        self.assertEqual(pkg == self.package, result)
        m_subp.assert_has_calls([mock.call('list', opts=['--cacheonly'])])


class TestGetArchitecture(CiTestCase):

    def setUp(self):
        super(TestGetArchitecture, self).setUp()
        self.target = paths.target_path('mytarget')
        self.add_patch('curtin.util.subp', 'm_subp')
        self.add_patch('curtin.distro.get_osfamily', 'm_get_osfamily')
        self.add_patch('curtin.distro.dpkg_get_architecture',
                       'm_dpkg_get_arch')
        self.add_patch('curtin.distro.rpm_get_architecture',
                       'm_rpm_get_arch')
        self.m_get_osfamily.return_value = distro.DISTROS.debian

    def test_osfamily_none_calls_get_osfamily(self):
        distro.get_architecture(target=self.target, osfamily=None)
        self.assertEqual([mock.call(target=self.target)],
                         self.m_get_osfamily.call_args_list)

    def test_unhandled_osfamily_raises_value_error(self):
        osfamily = distro.DISTROS.arch
        with self.assertRaises(ValueError):
            distro.get_architecture(target=self.target, osfamily=osfamily)
        self.assertEqual(0, self.m_dpkg_get_arch.call_count)
        self.assertEqual(0, self.m_rpm_get_arch.call_count)

    def test_debian_osfamily_calls_dpkg_get_arch(self):
        osfamily = distro.DISTROS.debian
        expected_result = self.m_dpkg_get_arch.return_value
        result = distro.get_architecture(target=self.target, osfamily=osfamily)
        self.assertEqual(expected_result, result)
        self.assertEqual([mock.call(target=self.target)],
                         self.m_dpkg_get_arch.call_args_list)
        self.assertEqual(0, self.m_rpm_get_arch.call_count)

    def test_redhat_osfamily_calls_rpm_get_arch(self):
        osfamily = distro.DISTROS.redhat
        expected_result = self.m_rpm_get_arch.return_value
        result = distro.get_architecture(target=self.target, osfamily=osfamily)
        self.assertEqual(expected_result, result)
        self.assertEqual([mock.call(target=self.target)],
                         self.m_rpm_get_arch.call_args_list)
        self.assertEqual(0, self.m_dpkg_get_arch.call_count)

# vi: ts=4 expandtab syntax=python
