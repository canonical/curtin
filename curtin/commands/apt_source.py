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

import collections
import os
import re
import sys
import tempfile

from curtin.log import LOG
from curtin import (config, util)

from . import populate_one_subcmd

CUSTOM = 'custom'

# this will match 'XXX:YYY' (ie, 'cloud-archive:foo' or 'ppa:bar')
ADD_APT_REPO_MATCH = r"^[\w-]+:\w"

# Files to store proxy information
APT_CONFIG_FN = "/etc/apt/apt.conf.d/94curtin-config"
APT_PROXY_FN = "/etc/apt/apt.conf.d/95curtin-proxy"

# A temporary shell program to get a given gpg key
# from a given keyserver
EXPORT_GPG_KEYID = """
    k=${1} ks=${2};
    exec 2>/dev/null
    [ -n "$k" ] || exit 1;
    armour=$(gpg --list-keys --armour "${k}")
    if [ -z "${armour}" ]; then
       gpg --keyserver ${ks} --recv "${k}" >/dev/null &&
          armour=$(gpg --export --armour "${k}") &&
          gpg --batch --yes --delete-keys "${k}"
    fi
    [ -n "${armour}" ] && echo "${armour}"
"""

DEFAULT_TEMPLATE = """
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

## Major bug fix updates produced after the final release of the
## distribution.
deb {{mirror}} {{codename}}-updates main restricted
deb-src {{mirror}} {{codename}}-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb {{mirror}} {{codename}} universe
deb-src {{mirror}} {{codename}} universe
deb {{mirror}} {{codename}}-updates universe
deb-src {{mirror}} {{codename}}-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb {{mirror}} {{codename}} multiverse
deb-src {{mirror}} {{codename}} multiverse
deb {{mirror}} {{codename}}-updates multiverse
deb-src {{mirror}} {{codename}}-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb {{mirror}} {{codename}}-backports main restricted universe multiverse
deb-src {{mirror}} {{codename}}-backports main restricted universe multiverse

deb {{security}} {{codename}}-security main restricted
deb-src {{security}} {{codename}}-security main restricted
deb {{security}} {{codename}}-security universe
deb-src {{security}} {{codename}}-security universe
deb {{security}} {{codename}}-security multiverse
deb-src {{security}} {{codename}}-security multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu {{codename}} partner
# deb-src http://archive.canonical.com/ubuntu {{codename}} partner
"""


def handle_apt_source(cfg):
    """ handle_apt_source
        process the custom config for apt_sources
    """
    release = get_release()
    mirrors = find_apt_mirror_info(cfg)
    if mirrors is None or "primary" not in mirrors:
        LOG.error("Can't get a valid mirror configuration")
        return

    # backwards compatibility
    mirror = mirrors["primary"]
    mirrors["mirror"] = mirror

    LOG.debug("Mirror info: %s", mirrors)

    if not config.value_as_boolean(cfg.get('apt_preserve_sources_list',
                                           False)):
        generate_sources_list(cfg, release, mirrors)

    try:
        apply_apt_proxy_config(cfg, APT_PROXY_FN, APT_CONFIG_FN)
    except Exception as error:
        LOG.warn("failed to proxy or apt config info: %s", error)

    # Process 'apt_sources'
    if 'apt_sources' in cfg:
        params = mirrors
        params['RELEASE'] = release
        params['MIRROR'] = mirror

        matcher = None
        matchcfg = cfg.get('add_apt_repo_match', ADD_APT_REPO_MATCH)
        if matchcfg:
            matcher = re.compile(matchcfg).search

        errors = add_sources(cfg['apt_sources'], params,
                             aa_repo_match=matcher)
        for error in errors:
            LOG.warn("Add source error: %s", ':'.join(error))

    dconf_sel = cfg.get('debconf_selections', False)
    if dconf_sel:
        LOG.debug("Setting debconf selections per cloud config")
        try:
            util.subp(('debconf-set-selections', '-'), dconf_sel)
        except Exception:
            LOG.error("Failed to run debconf-set-selections")


# get gpg keyid from keyserver
def getkeybyid(keyid, keyserver):
    """ getkeybyid
        try to get the raw PGP key data by it's id via network
    """
    with tempfile.NamedTemporaryFile(suffix='.sh', mode="w+", ) as fileh:
        fileh.write(EXPORT_GPG_KEYID)
        fileh.flush()
        cmd = ['/bin/sh', fileh.name, keyid, keyserver]
        (stdout, _unused_stderr) = util.subp(cmd, capture=True)
        return stdout.strip()


def mirror2lists_fileprefix(mirror):
    """ mirror2lists_fileprefix
        take off http:// or ftp://
    """
    string = mirror
    if string.endswith("/"):
        string = string[0:-1]
    pos = string.find("://")
    if pos >= 0:
        string = string[pos + 3:]
    string = string.replace("/", "_")
    return string


def get_release():
    """ get_release
        get the name of the release e.g. xenial
    """
    (stdout, _unused_stderr) = util.subp(['lsb_release', '-cs'], capture=True)
    return stdout.strip()


BASIC_MATCHER = re.compile(r'\$\{([A-Za-z0-9_.]+)\}|\$([A-Za-z0-9_.]+)')


def basic_render(content, params):
    """This does simple replacement of bash variable like templates.

    It identifies patterns like ${a} or $a and can also identify patterns like
    ${a.b} or $a.b which will look for a key 'b' in the dictionary rooted
    by key 'a'.
    """

    def replacer(match):
        """ replacer
            replacer used in regex match to replace content
        """
        # Only 1 of the 2 groups will actually have a valid entry.
        name = match.group(1)
        if name is None:
            name = match.group(2)
        if name is None:
            raise RuntimeError("Match encountered but no valid group present")
        path = collections.deque(name.split("."))
        selected_params = params
        while len(path) > 1:
            key = path.popleft()
            if not isinstance(selected_params, dict):
                raise TypeError("Can not traverse into"
                                " non-dictionary '%s' of type %s while"
                                " looking for subkey '%s'"
                                % (selected_params,
                                   selected_params.__class__.__name__,
                                   key))
            selected_params = selected_params[key]
        key = path.popleft()
        if not isinstance(selected_params, dict):
            raise TypeError("Can not extract key '%s' from non-dictionary"
                            " '%s' of type %s"
                            % (key, selected_params,
                               selected_params.__class__.__name__))
        return str(selected_params[key])

    return BASIC_MATCHER.sub(replacer, content)


def render_string_to_file(content, outfn, params, mode=0o644):
    """ render_string_to_file
        render a string to a file following replacement rules as defined
        in basic_render
    """
    contents = render_string(content, params)
    util.write_file(outfn, contents, mode=mode)


def render_string(content, params):
    """ render_string
        render a string following replacement rules as defined in basic_render
        returning the string
    """
    if not params:
        params = {}
    return basic_render(content, params)


def generate_sources_list(cfg, codename, mirrors):
    """ generate_sources_list
        create a source.list file based on a custom or default template
        by replacing mirrors and release in the template
    """
    params = {'codename': codename}
    for k in mirrors:
        params[k] = mirrors[k]

    template = cfg.get('apt_custom_sources_list', None)
    if template is None:
        template = DEFAULT_TEMPLATE

    render_string_to_file(template, '/etc/apt/sources.list', params)


def add_key_raw(key):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    try:
        util.subp(('apt-key', 'add', '-'), key)
    except:
        raise Exception('failed add key')


def add_key(ent):
    """
    add key to the system as defiend in ent (if any)
    suppords raw keys or keyid's
    The latter will as a first step fetched to get the raw key
    """
    if 'keyid' in ent and 'key' not in ent:
        keyserver = "keyserver.ubuntu.com"
        if 'keyserver' in ent:
            keyserver = ent['keyserver']
        try:
            ent['key'] = getkeybyid(ent['keyid'], keyserver)
        except:
            raise Exception('failed to get key from %s' % keyserver)

    if 'key' in ent:
        add_key_raw(ent['key'])


def add_sources(srcdict, template_params=None, aa_repo_match=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srcdict'.  When rendering template, also
    include the values in dictionary searchList
    """
    if template_params is None:
        template_params = {}

    if aa_repo_match is None:
        raise Exception('did not get a valid repo matcher')

    errorlist = []
    if not isinstance(srcdict, dict):
        raise Exception('unknown apt_sources format: %s' % (srcdict))

    for filename in srcdict:
        ent = srcdict[filename]
        if 'filename' not in ent:
            ent['filename'] = filename

        # keys can be added without specifying a source
        try:
            add_key(ent)
        except Exception as detail:
            errorlist.append([ent, detail])

        if 'source' not in ent:
            errorlist.append(["", "missing source"])
            continue
        source = ent['source']
        source = render_string(source, template_params)

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
            util.write_file(ent['filename'], contents, omode="ab")
        except Exception as detail:
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

    mirror_info = None
    mirror = cfg.get("apt_mirror", None)
    if mirror is not None:
        mirror_info = {'primary': mirror,
                       'security': mirror}
    else:
        pmirror = cfg.get("apt_primary_mirror", None)
        smirror = cfg.get("apt_security_mirror", pmirror)
        if pmirror is not None:
            mirror_info = {'primary': pmirror,
                           'security': smirror}

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
        Entry point for curtin apt_source
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
    if apt_source_cfg is None:
        raise ValueError("apt_source needs a custom config to be defined")

    try:
        handle_apt_source(apt_source_cfg)
    except Exception as error:
        sys.stderr.write("Failed to configure apt_source:\n%s\nExeption: %s" %
                         (apt_source_cfg, error))
        sys.exit(1)
    sys.exit(0)


CMD_ARGUMENTS = (
    ('mode', {'help': 'meta-mode to use',
              'choices': [CUSTOM]}),
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, apt_source)

# vi: ts=4 expandtab syntax=python
