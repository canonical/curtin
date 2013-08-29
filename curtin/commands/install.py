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
import json
import os
import shutil
import tempfile

from curtin import config
from curtin.log import LOG
from curtin import util

from . import populate_one_subcmd

CONFIG_BUILTIN = {
    'sources': {},
    'stages': ['early', 'partitioning', 'network', 'extract', 'hook', 'final'],
    'extract_commands': {'builtin': ['curtin', 'extract']},
    'hook_commands': {'builtin': ['curtin', 'hook']}
}


class MyAppend(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])
        getattr(namespace, self.dest).append((option_string, values,))


class WorkingDir(object):
    def __init__(self, config):
        top_d = tempfile.mkdtemp()
        state_d = os.path.join(top_d, 'state')
        target_d = os.path.join(top_d, 'target')
        scratch_d = os.path.join(top_d, 'scratch')
        for p in (state_d, target_d, scratch_d):
            os.mkdir(p)

        interfaces_f = os.path.join(state_d, 'interfaces')
        config_f = os.path.join(state_d, 'config')
        fstab_f = os.path.join(state_d, 'fstab')

        with open(config_f, "w") as fp:
            json.dump(config, fp)

        # just touch these files to make sure they exist
        for f in (interfaces_f, config_f, fstab_f):
            with open(f, "ab") as fp:
                pass

        self.scratch = scratch_d
        self.target = target_d
        self.top = top_d
        self.interfaces = interfaces_f
        self.fstab = fstab_f
        self.config = config
        self.config_file = config_f

    def env(self):
        return ({'WORKING_DIR': self.scratch, 'OUTPUT_FSTAB': self.fstab,
                 'OUTPUT_INTERFACES': self.interfaces,
                 'TARGET_MOUNT_POINT': self.target,
                 'CONFIG': self.config_file})


class Stage(object):
    def __init__(self, name, commands, env):
        self.name = name
        self.commands = commands
        self.env = env

    def run(self):
        for cmdname in sorted(self.commands.keys()):
            cmd = self.commands[cmdname]
            shell = not isinstance(cmd, list)
            with util.LogTimer(LOG.debug, cmdname):
                try:
                    util.subp(cmd, shell=shell, env=self.env)
                except util.ProcessExecutionError:
                    LOG.warn("%s command failed", cmdname)
                    raise


def cmd_install(args):
    cfg = CONFIG_BUILTIN

    for (flag, val) in args.cfgopts:
        if flag in ('-c', '--config'):
            config.merge_config_fp(cfg, val)
        elif flag in ('--set'):
            config.merge_cmdarg(cfg, val)

    for source in args.source:
        cfg['sources']["%02d_cmdline" % len(cfg['sources'])] = source

    LOG.debug("merged config: %s" % cfg)
    if not len(cfg.get('sources', [])):
        raise util.BadUsage("no sources provided to install")

    try:
        workingd = WorkingDir(cfg)
        LOG.debug(workingd.env())

        env = os.environ.copy()
        env.update(workingd.env())

        for name in cfg.get('stages'):
            commands_name = '%s_commands' % name
            with util.LogTimer(LOG.debug, 'stage_%s' % name):
                stage = Stage(name, cfg.get(commands_name, {}), env)
                stage.run()

    finally:
        for d in ('sys', 'dev', 'proc'):
            util.do_umount(os.path.join(workingd.target, d))
        util.do_umount(workingd.target)
        shutil.rmtree(workingd.top)


CMD_ARGUMENTS = (
    ((('-c', '--config'),
      {'help': 'read configuration from cfg', 'action': MyAppend,
       'metavar': 'FILE', 'type': argparse.FileType("rb"),
       'dest': 'cfgopts', 'default': []}),
     ('--set', {'help': 'define a config variable', 'action': MyAppend,
                'metavar': 'key=val', 'dest': 'cfgopts'}),
     ('source', {'help': 'what to install', 'nargs': '*'}),
     )
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, cmd_install)

# vi: ts=4 expandtab syntax=python
