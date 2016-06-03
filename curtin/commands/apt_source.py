"""
apt_source.py
Handling the setup of apt related tasks like proxies, PGP keys, repositories.
"""
#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

import glob
import os
import re
import sys
import traceback

from curtin.log import LOG
from curtin import (config, util)

from . import populate_one_subcmd

CUSTOM = 'custom'

# this will match 'XXX:YYY' (ie, 'cloud-archive:foo' or 'ppa:bar')
ADD_APT_REPO_MATCH = r"^[\w-]+:\w"

# place where apt stores cached repository data
APT_LISTS = "/var/lib/apt/lists"

# Files to store proxy information
APT_CONFIG_FN = "/etc/apt/apt.conf.d/94curtin-config"
APT_PROXY_FN = "/etc/apt/apt.conf.d/95curtin-proxy"

# Default keyserver to use
DEFAULT_KEYSERVER = "keyserver.ubuntu.com"

# Default archive mirror - those fix for the cloud-image curtin runs in
DEFAULT_MIRRORS = {"PRIMARY": "http://archive.ubuntu.com/ubuntu",
                   "SECURITY": "http://security.ubuntu.com/ubuntu"}

DEFAULT_TEMPLATE = """
## Note, this file is written by curtin at install time. It should not end
## up on the installed system itself.
#
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb $MIRROR $RELEASE main restricted
deb-src $MIRROR $RELEASE main restricted

## Major bug fix updates produced after the final release of the
## distribution.
deb $MIRROR $RELEASE-updates main restricted
deb-src $MIRROR $RELEASE-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb $MIRROR $RELEASE universe
deb-src $MIRROR $RELEASE universe
deb $MIRROR $RELEASE-updates universe
deb-src $MIRROR $RELEASE-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb $MIRROR $RELEASE multiverse
deb-src $MIRROR $RELEASE multiverse
deb $MIRROR $RELEASE-updates multiverse
deb-src $MIRROR $RELEASE-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb $MIRROR $RELEASE-backports main restricted universe multiverse
deb-src $MIRROR $RELEASE-backports main restricted universe multiverse

deb $SECURITY $RELEASE-security main restricted
deb-src $SECURITY $RELEASE-security main restricted
deb $SECURITY $RELEASE-security universe
deb-src $SECURITY $RELEASE-security universe
deb $SECURITY $RELEASE-security multiverse
deb-src $SECURITY $RELEASE-security multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu $RELEASE partner
# deb-src http://archive.canonical.com/ubuntu $RELEASE partner
"""


def handle_apt_source(cfg):
    """ handle_apt_source
        process the custom config for apt_sources
    """
    release = util.lsb_release()['codename']
    mirrors = find_apt_mirror_info(cfg)
    LOG.debug("Mirror info: %s", mirrors)

    if not config.value_as_boolean(cfg.get('apt_preserve_sources_list',
                                           False)):
        generate_sources_list(cfg, release, mirrors)
        rename_apt_lists(mirrors)

    try:
        apply_apt_proxy_config(cfg, APT_PROXY_FN, APT_CONFIG_FN)
    except (IOError, OSError) as error:
        LOG.warn("failed to proxy or apt config info: %s", error)

    # Process 'apt_source -> sources {dict}'
    if 'sources' in cfg:
        params = mirrors
        params['RELEASE'] = release
        params['MIRROR'] = mirrors["MIRROR"]

        matcher = None
        matchcfg = cfg.get('add_apt_repo_match', ADD_APT_REPO_MATCH)
        if matchcfg:
            matcher = re.compile(matchcfg).search

        errors = add_apt_sources(cfg['sources'], params,
                                 aa_repo_match=matcher)
        for error in errors:
            LOG.warn("Add source error: %s", ':'.join(error))


def mirrorurl_to_apt_fileprefix(mirror):
    """ mirrorurl_to_apt_fileprefix
        Convert a mirror url to the fule prefix used by apt on disk to
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


def rename_apt_lists(new_mirrors):
    """rename_apt_lists - rename apt lists to preserve old cache data"""
    for (name, omirror) in DEFAULT_MIRRORS.items():
        nmirror = new_mirrors.get(name)
        if not nmirror:
            continue
        oprefix = os.path.join(APT_LISTS, mirrorurl_to_apt_fileprefix(omirror))
        nprefix = os.path.join(APT_LISTS, mirrorurl_to_apt_fileprefix(nmirror))
        if oprefix == nprefix:
            continue
        olen = len(oprefix)
        for filename in glob.glob("%s_*" % oprefix):
            newname = "%s%s" % (nprefix, filename[olen:])
            LOG.info("Renaming apt list %s to %s", filename, newname)
            try:
                os.rename(filename, newname)
            except OSError:
                # since this is a best effort task, warn with but don't fail
                LOG.warn("failed to rename apt list: %s", exc_info=True)


def generate_sources_list(cfg, release, mirrors):
    """ generate_sources_list
        create a source.list file based on a custom or default template
        by replacing mirrors and release in the template
    """
    params = {'RELEASE': release}
    for k in mirrors:
        params[k] = mirrors[k]

    template = cfg.get('apt_custom_sources_list', None)
    if template is None:
        template = DEFAULT_TEMPLATE

    try:
        os.rename("/etc/apt/sources.list", "/etc/apt/sources.list.curtin")
    except OSError:
        LOG.exception("failed to backup /etc/apt/sources.list")
    util.render_string_to_file(template, '/etc/apt/sources.list', params)


def add_apt_key_raw(key):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    LOG.info("Adding key:\n'%s'", key)
    try:
        util.subp(('apt-key', 'add', '-'), key.encode())
    except util.ProcessExecutionError:
        raise ValueError('failed to add apt GPG Key to apt keyring')


def add_apt_key(ent):
    """
    Add key to the system as defined in ent (if any).
    Supports raw keys or keyid's
    The latter will as a first step fetched to get the raw key
    """
    if 'keyid' in ent and 'key' not in ent:
        keyserver = DEFAULT_KEYSERVER
        if 'keyserver' in ent:
            keyserver = ent['keyserver']

        ent['key'] = util.getkeybyid(ent['keyid'], keyserver)

    if 'key' in ent:
        add_apt_key_raw(ent['key'])


def add_apt_sources(srcdict, template_params=None, aa_repo_match=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srcdict'.  When rendering template, also
    include the values in dictionary searchList
    """
    if template_params is None:
        template_params = {}

    if aa_repo_match is None:
        raise ValueError('did not get a valid repo matcher')

    errorlist = []
    if not isinstance(srcdict, dict):
        raise TypeError('unknown apt_sources format: %s' % (srcdict))

    for filename in srcdict:
        ent = srcdict[filename]
        if 'filename' not in ent:
            ent['filename'] = filename

        # keys can be added without specifying a source
        try:
            add_apt_key(ent)
        except (ValueError, util.ProcessExecutionError) as detail:
            errorlist.append([ent, detail])

        if 'source' not in ent:
            errorlist.append(["", "missing source"])
            continue
        source = ent['source']
        source = util.render_string(source, template_params)

        if not ent['filename'].startswith("/"):
            ent['filename'] = os.path.join("/etc/apt/sources.list.d/",
                                           ent['filename'])

        if aa_repo_match(source):
            try:
                util.subp(["add-apt-repository", source])
            except util.ProcessExecutionError as err:
                errorlist.append([source,
                                  ("add-apt-repository failed. " + str(err))])
            continue

        try:
            contents = "%s\n" % (source)
            util.write_file(ent['filename'], contents, omode="a")
        except IOError as detail:
            errorlist.append([source,
                              "failed write to file %s: %s" % (ent['filename'],
                                                               detail)])

    return errorlist


def find_apt_mirror_info(cfg):
    """find_apt_mirror_info
       find an apt_mirror given the cfg provided.
       It can check for separate config of primary and security mirrors
       If only primary is given security is assumed to be equal to primary
       If the generic apt_mirror is given that is defining for both
    """

    mirror_info = DEFAULT_MIRRORS
    mirror = cfg.get("apt_mirror", None)
    if mirror is not None:
        mirror_info = {'PRIMARY': mirror,
                       'SECURITY': mirror}
    else:
        pmirror = cfg.get("apt_primary_mirror", None)
        smirror = cfg.get("apt_security_mirror", pmirror)
        if pmirror is not None:
            mirror_info = {'PRIMARY': pmirror,
                           'SECURITY': smirror}

    # less complex replacements use only MIRROR, derive from primary
    mirror_info["MIRROR"] = mirror_info["PRIMARY"]

    return mirror_info


def apply_apt_proxy_config(cfg, proxy_fname, config_fname):
    """apply_apt_proxy_config
       Applies any apt*proxy config from if specified
    """
    # Set up any apt proxy
    cfgs = (('apt_proxy', 'Acquire::HTTP::Proxy "%s";'),
            ('apt_http_proxy', 'Acquire::HTTP::Proxy "%s";'),
            ('apt_ftp_proxy', 'Acquire::FTP::Proxy "%s";'),
            ('apt_https_proxy', 'Acquire::HTTPS::Proxy "%s";'))

    proxies = [fmt % cfg.get(name) for (name, fmt) in cfgs if cfg.get(name)]
    if len(proxies):
        util.write_file(proxy_fname, '\n'.join(proxies) + '\n')
    elif os.path.isfile(proxy_fname):
        util.del_file(proxy_fname)

    if cfg.get('apt_config', None):
        util.write_file(config_fname, cfg.get('apt_config'))
    elif os.path.isfile(config_fname):
        util.del_file(config_fname)


def apt_source(args):
    """ apt_source
        Main entry point for curtin apt_source
        Handling of apt_source: dict as custom config for apt. This allows
        writing custom source.list files, adding ppa's and PGP keys.
        It is especially useful to provide a fully isolated derived repository
    """
    #  curtin apt-source custom
    state = util.load_command_environment()
    cfg = config.load_command_config(args, state)

    if args.mode != CUSTOM:
        raise NotImplementedError("mode=%s is not implemented" % args.mode)

    apt_source_cfg = cfg.get("apt_source")
    # if no apt_source config section is available, do nothing
    if apt_source_cfg:
        try:
            handle_apt_source(apt_source_cfg)
        except (RuntimeError, TypeError, ValueError) as error:
            sys.stderr.write("Failed to configure apt_source: '%s'\n" % error)
            traceback.print_exc()
            sys.exit(1)
    else:
        LOG.info("No apt_source custom config provided, skipping")

    sys.exit(0)


CMD_ARGUMENTS = (
    ('mode', {'help': 'meta-mode to use',
              'choices': [CUSTOM]}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, apt_source)

# vi: ts=4 expandtab syntax=python
