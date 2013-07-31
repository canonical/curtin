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

import argparse

from curtin.log import LOG
from curtin import config


class MyAppend(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).append((option_string, values,))


def cmd_install(args):
    cfg = {'urls': {}}

    for (flag, val) in args.cfgopts:
        if flag in ('-c', '--config'):
            config.merge_config_fp(cfg, val)
        elif flag in ('--set'):
            config.merge_cmdarg(cfg, val)

    for url in args.url:
        cfg['urls']["%02d_cmdline" % len(cfg['urls'])] = url

    LOG.debug("merged config: %s" % cfg)


CMD_ARGUMENTS = (
    ((('-c', '--config'),
      {'help': 'read configuration from cfg', 'action': MyAppend,
       'metavar': 'FILE', 'type': argparse.FileType("rb"),
       'dest': 'cfgopts'}),
     ('--set', {'help': 'define a config variable', 'action': MyAppend,
                'metavar': 'key=val', 'dest': 'cfgopts'}),
     ('url', {'help': 'what to install', 'nargs': '*'}),
     )
)
CMD_HANDLER = cmd_install

# vi: ts=4 expandtab syntax=python
