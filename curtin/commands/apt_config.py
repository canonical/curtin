# This file is part of curtin. See LICENSE file for copyright and license info.

"""
apt.py
Handle the setup of apt related tasks like proxies, mirrors, repositories.
"""

import argparse
import glob
import os
import re
import sys

from aptsources.sourceslist import SourceEntry

from debian.deb822 import Deb822

from curtin.log import LOG
from curtin import (config, distro, gpg, paths, util)

from . import populate_one_subcmd

# this will match 'XXX:YYY' (ie, 'cloud-archive:foo' or 'ppa:bar')
ADD_APT_REPO_MATCH = r"^[\w-]+:\w"

# place where apt stores cached repository data
APT_LISTS = "/var/lib/apt/lists"

# Files to store proxy information
APT_CONFIG_FN = "/etc/apt/apt.conf.d/94curtin-config"
APT_PROXY_FN = "/etc/apt/apt.conf.d/90curtin-aptproxy"

# Files to store pinning information
APT_PREFERENCES_FN = "/etc/apt/preferences.d/90curtin.pref"

# Default keyserver to use
DEFAULT_KEYSERVER = "keyserver.ubuntu.com"

# Default archive mirrors
PRIMARY_ARCH_MIRRORS = {"PRIMARY": "http://archive.ubuntu.com/ubuntu/",
                        "SECURITY": "http://security.ubuntu.com/ubuntu/"}
PORTS_MIRRORS = {"PRIMARY": "http://ports.ubuntu.com/ubuntu-ports",
                 "SECURITY": "http://ports.ubuntu.com/ubuntu-ports"}
PRIMARY_ARCHES = ['amd64', 'i386']
PORTS_ARCHES = ['s390x', 'arm64', 'armhf', 'powerpc', 'ppc64el', 'riscv64']

APT_SOURCES_PROPOSED = (
    "deb $MIRROR $RELEASE-proposed main restricted universe multiverse")

APT_SOURCES_PROPOSED_DEB822 = (
    'Types: deb\n'
    'URIs: $MIRROR\n'
    'Suites: $RELEASE-proposed\n'
    'Components: main restricted universe multiverse\n'
    'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
)


def get_default_mirrors(arch=None):
    """returns the default mirrors for the target. These depend on the
       architecture, for more see:
       https://wiki.ubuntu.com/UbuntuDevelopment/PackageArchive#Ports"""
    if arch is None:
        arch = distro.get_architecture()
    if arch in PRIMARY_ARCHES:
        return PRIMARY_ARCH_MIRRORS.copy()
    if arch in PORTS_ARCHES:
        return PORTS_MIRRORS.copy()
    raise ValueError("No default mirror known for arch %s" % arch)


def want_deb822(target=None):
    """
    Return True if we want to use deb822 apt sources on the target, and
    False otherwise.

    This is determined by the version of Ubuntu: deb822 is the default starting
    with Ubuntu 24.04 (Noble Numbat).
    """
    os_release = distro.os_release(target)

    if os_release.get('ID') != 'ubuntu':
        return False

    try:
        version = [int(n) for n in os_release.get('VERSION_ID', '').split('.')]
    except ValueError:
        return False

    if len(version) != 2:
        return False

    return version[0] >= 24


class Deb822SourceFormatException(Exception):
    pass


def deb822_field_sort_key(name):
    ordering = ['Enabled', 'Types', 'URIs', 'Suites', 'Components']
    try:
        return (0, ordering.index(name))
    except ValueError:
        return (1, name)


def component_sort_key(comp):
    ordering = ['main', 'restricted', 'universe', 'multiverse']
    try:
        return (0, ordering.index(comp))
    except ValueError:
        return (1, comp)


def suite_sort_key(suite):
    ordering = ['', 'updates', 'security', 'backports', 'proposed']
    pocket = suite.partition('-')[2]
    try:
        return (0, ordering.index(pocket))
    except ValueError:
        return (1, pocket)


def deb_type_sort_key(entry_type):
    ordering = ['deb', 'deb-src']
    try:
        return (0, ordering.index(entry_type))
    except ValueError:
        return (1, entry_type)


def _normalize_deb822_key(key):
    if key.lower() == 'uris':
        return 'URIs'

    return key.title()


def parse_deb822_sources(data):
    sources = []

    for para in Deb822.iter_paragraphs(data):
        # debian.deb822.Deb822 does not actually support iterable
        # values, so we need to put this back in a plain dict.
        entry = {_normalize_deb822_key(k): v for (k, v) in para.items()}

        for key in ('Types', 'URIs', 'Suites', 'Components'):
            try:
                entry[key] = entry[key].split()
            except KeyError:
                raise Deb822SourceFormatException(
                    'Source entry is missing required field "{}"'.format(key)
                )

        sources.append(entry)

    if not sources:
        raise Deb822SourceFormatException('No valid sources found')

    return sources


def deb822_entry_to_str(entry):
    stanza = ''

    sort_key_fns = {
        'Types': deb_type_sort_key,
        'Suites': suite_sort_key,
        'Components': component_sort_key,
    }

    for k in sorted(entry.keys(), key=deb822_field_sort_key):
        v = entry[k]
        if k == 'Enabled':
            if v.lower() == 'no':
                stanza += 'Enabled: no\n'
        elif isinstance(v, set) or isinstance(v, list):
            key_fn = sort_key_fns.get(k)
            stanza += '{}: {}\n'.format(k, ' '.join(sorted(v, key=key_fn)))
        else:
            stanza += '{}: {}\n'.format(k, v)

    return stanza


def maybe_convert_sources_to_deb822(sources):
    try:
        parse_deb822_sources(sources)

        return sources
    except Deb822SourceFormatException:
        return convert_sources_to_deb822(sources)


def convert_sources_to_deb822(sources):
    index = {}

    for entry in [SourceEntry(e) for e in sources.splitlines(True)]:
        if entry.invalid:
            continue

        # Remove disabled deb-src entries, because stylistically it makes
        # more sense to add/remove deb-src in the Types: field, rather than
        # having a deb-src entry with Enabled: no.
        if entry.type == 'deb-src' and entry.disabled:
            continue

        # Start by making the existing sources as "flat" as possible. Later
        # we can consolidate by suite and type if possible.
        key = (entry.disabled, entry.type, entry.uri, entry.dist)
        try:
            e = index[key]
            e['Components'] |= set(entry.comps)
        except KeyError:
            e = {}
            e['Enabled'] = 'no' if entry.disabled else 'yes'
            e['Types'] = set([entry.type])
            e['URIs'] = set([entry.uri])
            e['Suites'] = set([entry.dist])
            e['Components'] = set(entry.comps)
            index[key] = e

    for suite in [k[-1] for k in index.keys()]:
        for k in [k for k in index.keys() if k[-1] != suite]:
            try:
                e = index[(*k[:-1], suite)]

                if e['Components'] == index[k]['Components']:
                    e['Suites'] |= index[k]['Suites']

                    del index[k]
            except KeyError:
                continue

    for (ks, se) in [(k, e) for (k, e) in index.items() if k[1] == 'deb-src']:
        for (kb, be) in [(k, e) for (k, e) in index.items() if k[1] == 'deb']:
            can_combine = True
            can_combine &= se['Enabled'] == be['Enabled']
            can_combine &= se['URIs'] == be['URIs']
            can_combine &= se['Suites'] == be['Suites']
            can_combine &= se['Components'] == be['Components']

            if can_combine:
                be['Types'] = set(['deb', 'deb-src'])
                del index[ks]

    # Add Signed-By field if URI is default or will render to a configured one.
    mirrors = list(get_default_mirrors().values())
    mirrors += [m.rstrip('/') for m in mirrors]
    mirrors += ['$MIRROR', '$SECURITY', '$PRIMARY']

    for entry in index.values():
        if entry.get('Signed-By'):
            continue

        if not entry['URIs'] - set(mirrors):
            entry['Signed-By'] = (
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg'
            )

    return '\n'.join([deb822_entry_to_str(e) for e in index.values()])


def handle_apt(cfg, target=None):
    """ handle_apt
        process the config for apt_config. This can be called from
        curthooks if a global apt config was provided or via the "apt"
        standalone command.
    """
    release = distro.lsb_release(target=target)['codename']
    arch = distro.get_architecture(target)
    mirrors = find_apt_mirror_info(cfg, arch)
    LOG.debug("Apt Mirror info: %s", mirrors)

    apply_debconf_selections(cfg, target)

    if not config.value_as_boolean(cfg.get('preserve_sources_list',
                                           True)):
        generate_sources_list(cfg, release, mirrors, target)
        apply_preserve_sources_list(target)
        rename_apt_lists(mirrors, target)

    try:
        apply_apt_proxy_config(cfg, target + APT_PROXY_FN,
                               target + APT_CONFIG_FN)
    except (IOError, OSError):
        LOG.exception("Failed to apply proxy or apt config info:")

    try:
        apply_apt_preferences(cfg, target + APT_PREFERENCES_FN)
    except (IOError, OSError):
        LOG.exception("Failed to apply apt preferences.")

    # Process 'apt_source -> sources {dict}'
    if 'sources' in cfg:
        params = mirrors
        params['RELEASE'] = release
        params['MIRROR'] = mirrors["MIRROR"]

        matcher = None
        matchcfg = cfg.get('add_apt_repo_match', ADD_APT_REPO_MATCH)
        if matchcfg:
            matcher = re.compile(matchcfg).search

        add_apt_sources(cfg['sources'], target,
                        template_params=params, aa_repo_match=matcher)


def debconf_set_selections(selections, target=None):
    util.subp(['debconf-set-selections'], data=selections, target=target,
              capture=True)


def dpkg_reconfigure(packages, target=None):
    # For any packages that are already installed, but have preseed data
    # we populate the debconf database, but the filesystem configuration
    # would be preferred on a subsequent dpkg-reconfigure.
    # so, what we have to do is "know" information about certain packages
    # to unconfigure them.
    unhandled = []
    to_config = []
    for pkg in packages:
        if pkg in CONFIG_CLEANERS:
            LOG.debug("unconfiguring %s", pkg)
            CONFIG_CLEANERS[pkg](target)
            to_config.append(pkg)
        else:
            unhandled.append(pkg)

    if len(unhandled):
        LOG.warn("The following packages were installed and preseeded, "
                 "but cannot be unconfigured: %s", unhandled)

    if len(to_config):
        util.subp(['dpkg-reconfigure', '--frontend=noninteractive'] +
                  list(to_config), data=None, target=target, capture=True)


def apply_debconf_selections(cfg, target=None):
    """apply_debconf_selections - push content to debconf"""
    # debconf_selections:
    #  set1: |
    #   cloud-init cloud-init/datasources multiselect MAAS
    #  set2: pkg pkg/value string bar
    selsets = cfg.get('debconf_selections')
    if not selsets:
        LOG.debug("debconf_selections was not set in config")
        return

    LOG.debug('Applying debconf selections')
    selections = '\n'.join(
        [selsets[key] for key in sorted(selsets.keys())])
    debconf_set_selections(selections.encode() + b"\n", target=target)

    # get a complete list of packages listed in input
    pkgs_cfgd = set()
    for key, content in selsets.items():
        for line in content.splitlines():
            if line.startswith("#"):
                continue
            pkg = re.sub(r"[:\s].*", "", line)
            pkgs_cfgd.add(pkg)

    pkgs_installed = distro.get_installed_packages(target)
    need_reconfig = pkgs_cfgd.intersection(pkgs_installed)
    if len(need_reconfig) == 0:
        return

    dpkg_reconfigure(need_reconfig, target=target)


def clean_cloud_init(target):
    """clean out any local cloud-init config"""
    flist = glob.glob(
        paths.target_path(target, "/etc/cloud/cloud.cfg.d/*dpkg*"))

    LOG.debug("cleaning cloud-init config from: %s", flist)
    for dpkg_cfg in flist:
        os.unlink(dpkg_cfg)


def mirrorurl_to_apt_fileprefix(mirror):
    """ mirrorurl_to_apt_fileprefix
        Convert a mirror url to the file prefix used by apt on disk to
        store cache information for that mirror.
        To do so do:
        - take off ???://
        - drop tailing /
        - convert in string / to _
    """
    string = mirror
    if string.endswith("/"):
        string = string[0:-1]
    pos = string.find("://")
    if pos >= 0:
        string = string[pos + 3:]
    string = string.replace("/", "_")
    return string


def rename_apt_lists(new_mirrors, target=None, arch=None):
    """rename_apt_lists - rename apt lists to preserve old cache data"""
    if arch is None:
        arch = distro.get_architecture(target)
    default_mirrors = get_default_mirrors(arch)

    pre = paths.target_path(target, APT_LISTS)
    for (name, omirror) in default_mirrors.items():
        nmirror = new_mirrors.get(name)
        if not nmirror:
            continue

        oprefix = pre + os.path.sep + mirrorurl_to_apt_fileprefix(omirror)
        nprefix = pre + os.path.sep + mirrorurl_to_apt_fileprefix(nmirror)
        if oprefix == nprefix:
            continue
        olen = len(oprefix)
        for filename in glob.glob("%s_*" % oprefix):
            newname = "%s%s" % (nprefix, filename[olen:])
            LOG.debug("Renaming apt list %s to %s", filename, newname)
            try:
                os.rename(filename, newname)
            except OSError:
                # since this is a best effort task, warn with but don't fail
                LOG.warn("Failed to rename apt list:", exc_info=True)


def make_mirrors_replacement(mirrors, target, arch=None):
    if arch is None:
        arch = distro.get_architecture(target)
    defaults = get_default_mirrors(arch)
    mirrors_replacement = {}

    uri = mirrors.get('MIRROR')
    if uri is not None:
        mirrors_replacement[defaults['PRIMARY']] = uri

    uri = mirrors.get('SECURITY')
    if uri is not None:
        mirrors_replacement[defaults['SECURITY']] = uri

    # allow original file URIs without the trailing slash to match mirror
    # specifications that have it
    noslash = {}
    for key in mirrors_replacement.keys():
        if key[-1] == '/':
            noslash[key[:-1]] = mirrors_replacement[key]

    mirrors_replacement.update(noslash)

    return mirrors_replacement


def update_default_mirrors(entries, mirrors, target, arch=None):
    """replace existing default repos with the configured mirror"""
    mirrors_replacement = make_mirrors_replacement(mirrors, target, arch)

    for entry in entries:
        entry.uri = mirrors_replacement.get(entry.uri, entry.uri)
    return entries


def update_mirrors(entries, mirrors):
    """perform template replacement of mirror placeholders with configured
       values"""
    for entry in entries:
        entry.uri = util.render_string(entry.uri, mirrors)
    return entries


def map_known_suites(suite, release):
    """there are a few default names which will be auto-extended.
       This comes at the inability to use those names literally as suites,
       but on the other hand increases readability of the cfg quite a lot"""
    mapping = {'updates': '$RELEASE-updates',
               'backports': '$RELEASE-backports',
               'security': '$RELEASE-security',
               'proposed': '$RELEASE-proposed',
               'release': '$RELEASE'}
    try:
        template_suite = mapping[suite]
    except KeyError:
        template_suite = suite
    return util.render_string(template_suite, {'RELEASE': release})


def commentify(entry):
    # handle commenting ourselves - it handles lines with
    # options better
    return SourceEntry('# ' + str(entry))


def disable_suites(disabled, entries, release):
    """reads the config for suites to be disabled and removes those
       from the template"""
    if not disabled:
        return entries

    suites_to_disable = []
    for suite in disabled:
        release_suite = map_known_suites(suite, release)
        LOG.debug("Disabling suite %s as %s", suite, release_suite)
        suites_to_disable.append(release_suite)

    output = []
    for entry in entries:
        if not entry.disabled and entry.dist in suites_to_disable:
            entry = commentify(entry)
        output.append(entry)
    return output


def disable_components(disabled, entries):
    """reads the config for components to be disabled and remove those
       from the entries"""
    if not disabled:
        return entries

    # purposefully skip disabling the main component
    comps_to_disable = {comp for comp in disabled if comp != 'main'}

    output = []
    for entry in entries:
        if not entry.disabled and comps_to_disable.intersection(entry.comps):
            output.append(commentify(entry))
            entry.comps = [comp for comp in entry.comps
                           if comp not in comps_to_disable]
            if entry.comps:
                output.append(entry)
        else:
            output.append(entry)
    return output


def update_dist(entries, release):
    for entry in entries:
        entry.dist = util.render_string(entry.dist, {'RELEASE': release})
    return entries


def entries_to_str(entries):
    return ''.join([str(entry) + '\n' for entry in entries])


def _generate_sources_list_compat(
    cfg,
    release,
    mirrors,
    target=None,
    arch=None
):
    """ generate_sources_list
        create a source.list file based on a custom or default template
        by replacing mirrors and release in the template
    """
    aptsrc = "/etc/apt/sources.list"

    tmpl = cfg.get('sources_list', None)
    from_file = False
    if tmpl is None:
        LOG.info("No custom template provided, fall back to modify"
                 "mirrors in %s on the target system", aptsrc)
        tmpl = util.load_file(paths.target_path(target, aptsrc))
        from_file = True

    entries = [SourceEntry(line) for line in tmpl.splitlines(True)]
    if from_file:
        # when loading from an existing file, we also replace default
        # URIs with configured mirrors
        entries = update_default_mirrors(entries, mirrors, target, arch)

    entries = update_mirrors(entries, mirrors)
    entries = update_dist(entries, release)
    entries = disable_suites(cfg.get('disable_suites'), entries, release)
    entries = disable_components(cfg.get('disable_components'), entries)
    output = entries_to_str(entries)

    orig = paths.target_path(target, aptsrc)
    if os.path.exists(orig):
        os.rename(orig, orig + ".curtin.orig")
    util.write_file(paths.target_path(target, aptsrc), output, mode=0o644)


def _generate_sources_deb822(cfg, release, mirrors, target=None, arch=None):
    sources_deb822 = '/etc/apt/sources.list.d/ubuntu.sources'
    sources_list = '/etc/apt/sources.list'

    tmpl = cfg.get('sources_list', None)
    from_file = False

    if tmpl is None:
        LOG.info('No custom template provided, fall back to modify'
                 'mirrors in %s on the target system', sources_deb822)

        # If we don't already have the deb82 sources file, we will need to read
        # from sources.list and do the migration.
        target_path = paths.target_path(target, sources_deb822)
        if not os.path.exists(target_path):
            target_path = paths.target_path(target, sources_list)

        tmpl = util.load_file(target_path)
        from_file = True

    # Convert to deb822 sources if needed.
    tmpl = maybe_convert_sources_to_deb822(tmpl)

    suites_to_disable = set()
    if cfg.get('disable_suites') is not None:
        suites_to_disable = set(
            [map_known_suites(s, release) for s in cfg.get('disable_suites')]
        )

    comps_to_disable = set()
    if cfg.get('disable_components') is not None:
        comps_to_disable = set(
            [c for c in cfg.get('disable_components') if c != 'main']
        )

    mirrors_replacement = make_mirrors_replacement(mirrors, target, arch)

    stanzas = []
    for entry in parse_deb822_sources(tmpl):
        if from_file:
            # when loading from an existing file, we also replace default
            # URIs with configured mirrors
            entry['URIs'] = [mirrors_replacement.get(u, u)
                             for u in entry['URIs']]

        # Update mirrors
        entry['URIs'] = [util.render_string(u, mirrors)
                         for u in entry['URIs']]
        # Update dist
        entry['Suites'] = [util.render_string(s, {'RELEASE': release})
                           for s in entry['Suites']]

        # Disable suites and components
        entry['Suites'] = list(set(entry['Suites']) - suites_to_disable)
        entry['Components'] = list(set(entry['Components']) - comps_to_disable)

        if not entry['Suites']:
            # It is invalid for a stanza to have zero suite configured. In
            # practise, it can happen when -security is disabled.
            continue

        stanzas.append(deb822_entry_to_str(entry))

    target_path = paths.target_path(target, sources_deb822)
    if os.path.exists(target_path):
        os.rename(target_path, target_path + '.curtin.orig')

    output = '\n'.join(stanzas)
    util.write_file(target_path, output, mode=0o644)

    # If sources.list still exists, leave a note about the migration.
    target_path = paths.target_path(target, sources_list)
    if os.path.exists(target_path):
        output = '# Ubuntu sources have moved to {}\n'.format(sources_deb822)
        util.write_file(target_path, output, mode=0o644)


def generate_sources_list(cfg, release, mirrors, target=None, arch=None):
    if want_deb822(target):
        _generate_sources_deb822(cfg, release, mirrors, target, arch)
    else:
        _generate_sources_list_compat(cfg, release, mirrors, target, arch)


def apply_preserve_sources_list(target):
    # protect the just generated sources.list from cloud-init
    cloudfile = "/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg"

    target_ver = distro.get_package_version('cloud-init', target=target)
    if not target_ver:
        LOG.info("Attempt to read cloud-init version from target returned "
                 "'%s', not writing preserve_sources_list config.",
                 target_ver)
        return

    cfg = {'apt': {'preserve_sources_list': True}}
    if target_ver['major'] < 1:
        # anything cloud-init 0.X.X will get the old config key.
        cfg = {'apt_preserve_sources_list': True}

    try:
        util.write_file(paths.target_path(target, cloudfile),
                        config.dump_config(cfg), mode=0o644)
        LOG.debug("Set preserve_sources_list to True in %s with: %s",
                  cloudfile, cfg)
    except IOError:
        LOG.exception(
            "Failed to protect /etc/apt/sources.list from cloud-init in '%s'",
            cloudfile)
        raise


def add_apt_key_raw(keyname, key, target=None):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    if '-----BEGIN PGP PUBLIC KEY BLOCK-----' in str(key):
        keyfile_ext = 'asc'
        omode = 'w'
        key = key.rstrip()
    else:
        keyfile_ext = 'gpg'
        omode = 'wb'

    keyfile = '/etc/apt/trusted.gpg.d/{}.{}'.format(keyname, keyfile_ext)
    target_keyfile = paths.target_path(target, keyfile)
    util.write_file(target_keyfile, key, mode=0o644, omode=omode)
    LOG.debug("Adding key to '%s':\n'%s'", target_keyfile, key)


def add_apt_key(keyname, ent, target=None):
    """
    Add key to the system as defined in ent (if any).
    Supports raw keys or keyid's
    The latter will as a first step fetched to get the raw key
    """
    if 'keyid' in ent and 'key' not in ent:
        keyserver = DEFAULT_KEYSERVER
        if 'keyserver' in ent:
            keyserver = ent['keyserver']

        ent['key'] = gpg.getkeybyid(ent['keyid'], keyserver,
                                    retries=(1, 2, 5, 10))

    if 'key' in ent:
        add_apt_key_raw(keyname, ent['key'], target)


def add_apt_sources(srcdict, target=None, template_params=None,
                    aa_repo_match=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srcdict'.  When rendering template, also
    include the values in dictionary searchList
    """
    if template_params is None:
        template_params = {}

    if aa_repo_match is None:
        raise ValueError('did not get a valid repo matcher')

    if not isinstance(srcdict, dict):
        raise TypeError('unknown apt format: %s' % (srcdict))

    target_wants_deb822 = want_deb822(target)

    for filename in srcdict:
        ent = srcdict[filename]
        if 'filename' not in ent:
            ent['filename'] = filename

        # Derive a suggested key file name from the sources.list name.
        # The filename may be a full path.
        keyname = os.path.basename(ent['filename'])
        add_apt_key(keyname, ent, target)

        source = ent.get('source')
        if source is None:
            continue

        if aa_repo_match(source):
            with util.ChrootableTarget(
                    target, sys_resolvconf=True) as in_chroot:
                try:
                    in_chroot.subp(["add-apt-repository", source],
                                   retries=(1, 2, 5, 10))
                except util.ProcessExecutionError:
                    LOG.exception("add-apt-repository failed.")
                    raise
            continue

        if source == 'proposed':
            if target_wants_deb822:
                source = APT_SOURCES_PROPOSED_DEB822
            else:
                source = APT_SOURCES_PROPOSED

        source = util.render_string(source, template_params)

        if not ent['filename'].startswith("/"):
            ent['filename'] = os.path.join("/etc/apt/sources.list.d/",
                                           ent['filename'])

        # Convert this source to deb822 format if needed.
        if target_wants_deb822:
            source = maybe_convert_sources_to_deb822(source)

        ext = '.sources' if target_wants_deb822 else '.list'
        splext = os.path.splitext(ent['filename'])
        if splext[1] != ext:
            ent['filename'] = splext[0] + ext

        sourcefn = paths.target_path(target, ent['filename'])
        try:
            contents = "%s\n" % (source.rstrip())
            util.write_file(sourcefn, contents, omode="a")
        except IOError as detail:
            LOG.exception("failed write to file %s: %s", sourcefn, detail)
            raise

    distro.apt_update(target=target)

    return


def search_for_mirror(candidates):
    """
    Search through a list of mirror urls for one that works
    This needs to return quickly.
    """
    if candidates is None:
        return None

    LOG.debug("search for mirror in candidates: '%s'", candidates)
    for cand in candidates:
        try:
            if util.is_resolvable_url(cand):
                LOG.debug("found working mirror: '%s'", cand)
                return cand
        except Exception:
            pass
    return None


def update_mirror_info(pmirror, smirror, arch):
    """sets security mirror to primary if not defined.
       returns defaults if no mirrors are defined"""
    if pmirror is not None:
        if smirror is None:
            smirror = pmirror
        return {'PRIMARY': pmirror,
                'SECURITY': smirror}
    return get_default_mirrors(arch)


def get_arch_mirrorconfig(cfg, mirrortype, arch):
    """out of a list of potential mirror configurations select
       and return the one matching the architecture (or default)"""
    # select the mirror specification (if-any)
    mirror_cfg_list = cfg.get(mirrortype, None)
    if mirror_cfg_list is None:
        return None

    # select the specification matching the target arch
    default = None
    for mirror_cfg_elem in mirror_cfg_list:
        arches = mirror_cfg_elem.get("arches")
        if arch in arches:
            return mirror_cfg_elem
        if "default" in arches:
            default = mirror_cfg_elem
    return default


def get_mirror(cfg, mirrortype, arch):
    """pass the three potential stages of mirror specification
       returns None is neither of them found anything otherwise the first
       hit is returned"""
    mcfg = get_arch_mirrorconfig(cfg, mirrortype, arch)
    if mcfg is None:
        return None

    # directly specified
    mirror = mcfg.get("uri", None)

    # fallback to search if specified
    if mirror is None:
        # list of mirrors to try to resolve
        mirror = search_for_mirror(mcfg.get("search", None))

    return mirror


def find_apt_mirror_info(cfg, arch=None):
    """find_apt_mirror_info
       find an apt_mirror given the cfg provided.
       It can check for separate config of primary and security mirrors
       If only primary is given security is assumed to be equal to primary
       If the generic apt_mirror is given that is defining for both
    """

    if arch is None:
        arch = distro.get_architecture()
        LOG.debug("got arch for mirror selection: %s", arch)
    pmirror = get_mirror(cfg, "primary", arch)
    LOG.debug("got primary mirror: %s", pmirror)
    smirror = get_mirror(cfg, "security", arch)
    LOG.debug("got security mirror: %s", smirror)

    # Note: curtin has no cloud-datasource fallback

    mirror_info = update_mirror_info(pmirror, smirror, arch)

    # less complex replacements use only MIRROR, derive from primary
    mirror_info["MIRROR"] = mirror_info["PRIMARY"]

    return mirror_info


def apply_apt_proxy_config(cfg, proxy_fname, config_fname):
    """apply_apt_proxy_config
       Applies any apt*proxy from config if specified
    """
    # Set up any apt proxy
    cfgs = (('proxy', 'Acquire::http::Proxy "%s";'),
            ('http_proxy', 'Acquire::http::Proxy "%s";'),
            ('ftp_proxy', 'Acquire::ftp::Proxy "%s";'),
            ('https_proxy', 'Acquire::https::Proxy "%s";'))

    proxies = [fmt % cfg.get(name) for (name, fmt) in cfgs if cfg.get(name)]
    if len(proxies):
        LOG.debug("write apt proxy info to %s", proxy_fname)
        util.write_file(proxy_fname, '\n'.join(proxies) + '\n')
    elif os.path.isfile(proxy_fname):
        util.del_file(proxy_fname)
        LOG.debug("no apt proxy configured, removed %s", proxy_fname)

    if cfg.get('conf', None):
        LOG.debug("write apt config info to %s", config_fname)
        util.write_file(config_fname, cfg.get('conf'))
    elif os.path.isfile(config_fname):
        util.del_file(config_fname)
        LOG.debug("no apt config configured, removed %s", config_fname)


def preference_to_str(preference):
    """ Return a textual representation of a given preference as specified in
    apt_preferences(5).
    """

    return """\
Package: {package}
Pin: {pin}
Pin-Priority: {pin_priority}
""".format(package=preference["package"],
           pin=preference["pin"],
           pin_priority=preference["pin-priority"])


def apply_apt_preferences(cfg, pref_fname):
    """ Apply apt preferences if any is provided.
    """

    prefs = cfg.get("preferences")
    if not prefs:
        if os.path.isfile(pref_fname):
            util.del_file(pref_fname)
            LOG.debug("no apt preferences configured, removed %s", pref_fname)
        return
    prefs_as_strings = [preference_to_str(pref) for pref in prefs]
    LOG.debug("write apt preferences info to %s.", pref_fname)
    util.write_file(pref_fname, "\n".join(prefs_as_strings))


def apt_command(args):
    """ Main entry point for curtin apt-config standalone command
        This does not read the global config as handled by curthooks, but
        instead one can specify a different "target" and a new cfg via --config
        """
    cfg = config.load_command_config(args, {})

    if args.target is not None:
        target = args.target
    else:
        state = util.load_command_environment()
        target = state['target']

    if target is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    apt_cfg = cfg.get("apt")
    # if no apt config section is available, do nothing
    if apt_cfg is not None:
        LOG.debug("Handling apt to target %s with config %s",
                  target, apt_cfg)
        try:
            with util.ChrootableTarget(target, sys_resolvconf=True):
                handle_apt(apt_cfg, target)
        except (RuntimeError, TypeError, ValueError, IOError):
            LOG.exception("Failed to configure apt features '%s'", apt_cfg)
            sys.exit(1)
    else:
        LOG.info("No apt config provided, skipping")

    sys.exit(0)


def translate_old_apt_features(cfg):
    """translate the few old apt related features into the new config format ;
    by mutating the cfg object. """
    predef_apt_cfg = cfg.get("apt", {})

    if cfg.get('apt_proxy') is not None:
        if predef_apt_cfg.get('proxy') is not None:
            msg = ("Error in apt_proxy configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        cfg.setdefault('apt', {})
        cfg['apt']['proxy'] = cfg.get('apt_proxy')
        LOG.debug("Transferred %s into new format: %s", cfg.get('apt_proxy'),
                  cfg.get('apt'))
        del cfg['apt_proxy']

    if cfg.get('apt_mirrors') is not None:
        if predef_apt_cfg.get('mirrors') is not None:
            msg = ("Error in apt_mirror configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        old = cfg.get('apt_mirrors')
        cfg.setdefault('apt', {})
        cfg['apt']['primary'] = [{"arches": ["default"],
                                  "uri": old.get('ubuntu_archive')}]
        cfg['apt']['security'] = [{"arches": ["default"],
                                   "uri": old.get('ubuntu_security')}]
        LOG.debug("Transferred %s into new format: %s", cfg.get('apt_mirror'),
                  cfg.get('apt'))
        del cfg['apt_mirrors']
        # to work this also needs to disable the default protection
        psl = predef_apt_cfg.get('preserve_sources_list')
        if psl is not None:
            if config.value_as_boolean(psl) is True:
                msg = ("Error in apt_mirror configuration: "
                       "apt_mirrors and preserve_sources_list: True "
                       "are mutually exclusive")
                LOG.error(msg)
                raise ValueError(msg)
        cfg.setdefault('apt', {})
        cfg['apt']['preserve_sources_list'] = False

    if cfg.get('debconf_selections') is not None:
        if predef_apt_cfg.get('debconf_selections') is not None:
            msg = ("Error in debconf_selections configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        selsets = cfg.get('debconf_selections')
        cfg.setdefault('apt', {})
        cfg['apt']['debconf_selections'] = selsets
        LOG.info("Transferred %s into new format: %s",
                 cfg.get('debconf_selections'),
                 cfg.get('apt'))
        del cfg['debconf_selections']


CMD_ARGUMENTS = (
    ((('-c', '--config'),
      {'help': 'read configuration from cfg', 'action': util.MergedCmdAppend,
       'metavar': 'FILE', 'type': argparse.FileType("rb"),
       'dest': 'cfgopts', 'default': []}),
     (('-t', '--target'),
      {'help': 'chroot to target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET',
       'default': os.environ.get('TARGET_MOUNT_POINT')}),)
)


def POPULATE_SUBCMD(parser):
    """Populate subcommand option parsing for apt-config"""
    populate_one_subcmd(parser, CMD_ARGUMENTS, apt_command)


CONFIG_CLEANERS = {
    'cloud-init': clean_cloud_init,
    'cloud-init-base': clean_cloud_init,
}

# vi: ts=4 expandtab syntax=python
