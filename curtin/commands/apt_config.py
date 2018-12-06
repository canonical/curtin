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

# Default keyserver to use
DEFAULT_KEYSERVER = "keyserver.ubuntu.com"

# Default archive mirrors
PRIMARY_ARCH_MIRRORS = {"PRIMARY": "http://archive.ubuntu.com/ubuntu/",
                        "SECURITY": "http://security.ubuntu.com/ubuntu/"}
PORTS_MIRRORS = {"PRIMARY": "http://ports.ubuntu.com/ubuntu-ports",
                 "SECURITY": "http://ports.ubuntu.com/ubuntu-ports"}
PRIMARY_ARCHES = ['amd64', 'i386']
PORTS_ARCHES = ['s390x', 'arm64', 'armhf', 'powerpc', 'ppc64el']

APT_SOURCES_PROPOSED = (
    "deb $MIRROR $RELEASE-proposed main restricted universe multiverse")


def get_default_mirrors(arch=None):
    """returns the default mirrors for the target. These depend on the
       architecture, for more see:
       https://wiki.ubuntu.com/UbuntuDevelopment/PackageArchive#Ports"""
    if arch is None:
        arch = util.get_architecture()
    if arch in PRIMARY_ARCHES:
        return PRIMARY_ARCH_MIRRORS.copy()
    if arch in PORTS_ARCHES:
        return PORTS_MIRRORS.copy()
    raise ValueError("No default mirror known for arch %s" % arch)


def handle_apt(cfg, target=None):
    """ handle_apt
        process the config for apt_config. This can be called from
        curthooks if a global apt config was provided or via the "apt"
        standalone command.
    """
    release = distro.lsb_release(target=target)['codename']
    arch = util.get_architecture(target)
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

    LOG.debug("pkgs_cfgd: %s", pkgs_cfgd)
    LOG.debug("pkgs_installed: %s", pkgs_installed)
    need_reconfig = pkgs_cfgd.intersection(pkgs_installed)

    if len(need_reconfig) == 0:
        LOG.debug("no need for reconfig")
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


def rename_apt_lists(new_mirrors, target=None):
    """rename_apt_lists - rename apt lists to preserve old cache data"""
    default_mirrors = get_default_mirrors(util.get_architecture(target))

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


def mirror_to_placeholder(tmpl, mirror, placeholder):
    """ mirror_to_placeholder
        replace the specified mirror in a template with a placeholder string
        Checks for existance of the expected mirror and warns if not found
    """
    if mirror not in tmpl:
        if mirror.endswith("/") and mirror[:-1] in tmpl:
            LOG.debug("mirror_to_placeholder: '%s' did not exist in tmpl, "
                      "did without a trailing /.  Accomodating.", mirror)
            mirror = mirror[:-1]
        else:
            LOG.warn("Expected mirror '%s' not found in: %s", mirror, tmpl)
    return tmpl.replace(mirror, placeholder)


def map_known_suites(suite):
    """there are a few default names which will be auto-extended.
       This comes at the inability to use those names literally as suites,
       but on the other hand increases readability of the cfg quite a lot"""
    mapping = {'updates': '$RELEASE-updates',
               'backports': '$RELEASE-backports',
               'security': '$RELEASE-security',
               'proposed': '$RELEASE-proposed',
               'release': '$RELEASE'}
    try:
        retsuite = mapping[suite]
    except KeyError:
        retsuite = suite
    return retsuite


def disable_suites(disabled, src, release):
    """reads the config for suites to be disabled and removes those
       from the template"""
    if not disabled:
        return src

    retsrc = src
    for suite in disabled:
        suite = map_known_suites(suite)
        releasesuite = util.render_string(suite, {'RELEASE': release})
        LOG.debug("Disabling suite %s as %s", suite, releasesuite)

        newsrc = ""
        for line in retsrc.splitlines(True):
            if line.startswith("#"):
                newsrc += line
                continue

            # sources.list allow options in cols[1] which can have spaces
            # so the actual suite can be [2] or later. example:
            # deb [ arch=amd64,armel k=v ] http://example.com/debian
            cols = line.split()
            if len(cols) > 1:
                pcol = 2
                if cols[1].startswith("["):
                    for col in cols[1:]:
                        pcol += 1
                        if col.endswith("]"):
                            break

                if cols[pcol] == releasesuite:
                    line = '# suite disabled by curtin: %s' % line
            newsrc += line
        retsrc = newsrc

    return retsrc


def generate_sources_list(cfg, release, mirrors, target=None):
    """ generate_sources_list
        create a source.list file based on a custom or default template
        by replacing mirrors and release in the template
    """
    default_mirrors = get_default_mirrors(util.get_architecture(target))
    aptsrc = "/etc/apt/sources.list"
    params = {'RELEASE': release}
    for k in mirrors:
        params[k] = mirrors[k]

    tmpl = cfg.get('sources_list', None)
    if tmpl is None:
        LOG.info("No custom template provided, fall back to modify"
                 "mirrors in %s on the target system", aptsrc)
        tmpl = util.load_file(paths.target_path(target, aptsrc))
        # Strategy if no custom template was provided:
        # - Only replacing mirrors
        # - no reason to replace "release" as it is from target anyway
        # - The less we depend upon, the more stable this is against changes
        # - warn if expected original content wasn't found
        tmpl = mirror_to_placeholder(tmpl, default_mirrors['PRIMARY'],
                                     "$MIRROR")
        tmpl = mirror_to_placeholder(tmpl, default_mirrors['SECURITY'],
                                     "$SECURITY")

    orig = paths.target_path(target, aptsrc)
    if os.path.exists(orig):
        os.rename(orig, orig + ".curtin.old")

    rendered = util.render_string(tmpl, params)
    disabled = disable_suites(cfg.get('disable_suites'), rendered, release)
    util.write_file(paths.target_path(target, aptsrc), disabled, mode=0o644)


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


def add_apt_key_raw(key, target=None):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    LOG.debug("Adding key:\n'%s'", key)
    try:
        util.subp(['apt-key', 'add', '-'], data=key.encode(), target=target)
    except util.ProcessExecutionError:
        LOG.exception("failed to add apt GPG Key to apt keyring")
        raise


def add_apt_key(ent, target=None):
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
        add_apt_key_raw(ent['key'], target)


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

    for filename in srcdict:
        ent = srcdict[filename]
        if 'filename' not in ent:
            ent['filename'] = filename

        add_apt_key(ent, target)

        if 'source' not in ent:
            continue
        source = ent['source']
        if source == 'proposed':
            source = APT_SOURCES_PROPOSED
        source = util.render_string(source, template_params)

        if not ent['filename'].startswith("/"):
            ent['filename'] = os.path.join("/etc/apt/sources.list.d/",
                                           ent['filename'])
        if not ent['filename'].endswith(".list"):
            ent['filename'] += ".list"

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

        sourcefn = paths.target_path(target, ent['filename'])
        try:
            contents = "%s\n" % (source)
            util.write_file(sourcefn, contents, omode="a")
        except IOError as detail:
            LOG.exception("failed write to file %s: %s", sourcefn, detail)
            raise

    distro.apt_update(target=target, force=True,
                      comment="apt-source changed config")

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
        arch = util.get_architecture()
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
       Applies any apt*proxy config from if specified
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
    """translate the few old apt related features into the new config format"""
    predef_apt_cfg = cfg.get("apt")
    if predef_apt_cfg is None:
        cfg['apt'] = {}
        predef_apt_cfg = cfg.get("apt")

    if cfg.get('apt_proxy') is not None:
        if predef_apt_cfg.get('proxy') is not None:
            msg = ("Error in apt_proxy configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        cfg['apt']['proxy'] = cfg.get('apt_proxy')
        LOG.debug("Transferred %s into new format: %s", cfg.get('apt_proxy'),
                  cfg.get('apte'))
        del cfg['apt_proxy']

    if cfg.get('apt_mirrors') is not None:
        if predef_apt_cfg.get('mirrors') is not None:
            msg = ("Error in apt_mirror configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        old = cfg.get('apt_mirrors')
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
        cfg['apt']['preserve_sources_list'] = False

    if cfg.get('debconf_selections') is not None:
        if predef_apt_cfg.get('debconf_selections') is not None:
            msg = ("Error in debconf_selections configuration: "
                   "old and new format of apt features "
                   "are mutually exclusive")
            LOG.error(msg)
            raise ValueError(msg)

        selsets = cfg.get('debconf_selections')
        cfg['apt']['debconf_selections'] = selsets
        LOG.info("Transferred %s into new format: %s",
                 cfg.get('debconf_selections'),
                 cfg.get('apt'))
        del cfg['debconf_selections']

    return cfg


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
}

# vi: ts=4 expandtab syntax=python
