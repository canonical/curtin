#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
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

import os
import re
import sys

from curtin import config
from curtin import futil
from curtin.log import LOG
from curtin import util

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-t', '--target'),
      {'help': 'operate on target. default is env[TARGET_MOUNT_POINT]',
       'action': 'store', 'metavar': 'TARGET', 'default': None}),
     (('-c', '--config'),
      {'help': 'operate on config. default is env[CONFIG]',
       'action': 'store', 'metavar': 'CONFIG', 'default': None}),
     )
)


def write_files(cfg, target):
    # this takes 'write_files' entry in config and writes files in the target
    # config entry example:
    # f1:
    #  path: /file1
    #  content: !!binary |
    #    f0VMRgIBAQAAAAAAAAAAAAIAPgABAAAAwARAAAAAAABAAAAAAAAAAJAVAAAAAAA
    # f2: {path: /file2, content: "foobar", permissions: '0666'}
    if 'write_files' not in cfg:
        return

    for (key, info) in cfg.get('write_files').items():
        if not info.get('path'):
            LOG.warn("Warning, write_files[%s] had no 'path' entry", key)

        futil.write_finfo(path=target + os.path.sep + info['path'],
                          content=info.get('content', ''),
                          owner=info.get('owner', "-1:-1"),
                          perms=info.get('perms', "0644"))


def apt_config(cfg, target):
    # cfg['apt_proxy']

    proxy_cfg_path = os.path.sep.join([target,
        '/etc/apt/apt.conf.d/90curtin-aptproxy'])
    if cfg.get('apt_proxy'):
        util.write_file(proxy_cfg_path,
            content='Acquire::HTTP::Proxy "%s";\n' % cfg['apt_proxy'])
    else:
        if os.path.isfile(proxy_cfg_path):
            os.path.unlink(proxy_cfg_path)

    # cfg['apt_mirrors']
    # apt_mirrors:
    #  ubuntu_archive: http://local.archive/ubuntu
    #  ubuntu_security: http://local.archive/ubuntu
    sources_list = os.path.sep.join([target, '/etc/apt/sources.list'])
    if (isinstance(cfg.get('apt_mirrors'), dict) and
        os.path.isfile(sources_list)):
        repls = [
            ('ubuntu_archive', r'http://\S*[.]*archive.ubuntu.com/\S*'),
            ('ubuntu_security', r'http://security.ubuntu.com/\S*'),
        ]
        content = None
        for name, regex in repls:
            mirror = cfg['apt_mirrors'].get(name)
            if not mirror:
                continue

            if content is None:
                with open(sources_list) as fp:
                    content = fp.read()
                util.write_file(sources_list + ".dist", content)

            content = re.sub(regex, mirror + " ", content)

        if content is not None:
            util.write_file(sources_list, content)


def curthooks(args):
    state = util.load_command_environment()

    if args.target is not None:
        target = args.target
    else:
        target = state['target']

    if args.config is not None:
        cfg_file = args.config
    else:
        cfg_file = state['target']

    if target is None:
        sys.stderr.write("Unable to find target.  "
                         "Use --target or set TARGET_MOUNT_POINT\n")
        sys.exit(2)

    if not cfg_file:
        LOG.debug("config file was none!")
        cfg = {}
    else:
        cfg = config.load_config(cfg_file)

    write_files(cfg, target)
    apt_config(cfg, target)
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, curthooks)

# vi: ts=4 expandtab syntax=python
