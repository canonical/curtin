#   Copyright (C) 2017 Canonical Ltd.
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

from datetime import datetime
import json
import os
import re
import shutil
import sys
import tempfile


from .. import util
from .. import version
from ..config import load_config, merge_config
from . import populate_one_subcmd
from .install import CONFIG_BUILTIN, SAVE_INSTALL_CONFIG


CURTIN_PACK_CONFIG_DIR = '/curtin/configs'


def collect_logs_main(args):
    """Collect all configured curtin logs and into a tarfile."""
    if os.path.exists(SAVE_INSTALL_CONFIG):
        cfg = load_config(SAVE_INSTALL_CONFIG)
    elif os.path.isdir(CURTIN_PACK_CONFIG_DIR):
        cfg = CONFIG_BUILTIN.copy()
        for _file in sorted(os.listdir(CURTIN_PACK_CONFIG_DIR)):
            merge_config(
                cfg, load_config(os.path.join(CURTIN_PACK_CONFIG_DIR, _file)))
    else:
        sys.stderr.write(
            'Warning: no configuration file found in %s or %s.\n'
            'Using builtin configuration.' % (
                SAVE_INSTALL_CONFIG, CURTIN_PACK_CONFIG_DIR))
        cfg = CONFIG_BUILTIN.copy()
    create_log_tarfile(args.output, cfg)


def create_log_tarfile(tarfile, config):
    """Create curtin logs tarfile within a temporary directory.

    A subdirectory curtin-<DATE> is created in the tar containing the specified
    logs. Duplicates are skipped, paths which don't exist are skipped.

    @param tarfile: Path of the tarfile we want to create.
    @param config: Dictionary of curtin's configuration.
    """
    if not (isinstance(tarfile, util.string_types) and tarfile):
        raise ValueError("Invalid value '%s' for tarfile" % tarfile)
    target_dir = os.path.dirname(tarfile)
    if target_dir and not os.path.exists(target_dir):
        util.ensure_dir(target_dir)

    instcfg = config.get('install', {})
    logfile = instcfg.get('log_file')
    alllogs = instcfg.get('post_files', [])
    if logfile:
        alllogs.append(logfile)
    # Prune duplicates and files which do not exist
    stderr = sys.stderr
    valid_logs = []
    for logfile in set(alllogs):
        if os.path.exists(logfile):
            valid_logs.append(logfile)
        else:
            stderr.write(
                'Skipping logfile %s: file does not exist\n' % logfile)

    maascfg = instcfg.get('maas', {})
    redact_values = []
    for key in ('consumer_key', 'token_key', 'token_secret'):
        redact_value = maascfg.get(key)
        if redact_value:
            redact_values.append(redact_value)

    date = datetime.utcnow().strftime('%Y-%m-%d-%H-%M')
    tmp_dir = tempfile.mkdtemp()
    # The tar will contain a dated subdirectory containing all logs
    tar_dir = 'curtin-logs-{date}'.format(date=date)
    cmd = ['tar', '-cvf', os.path.join(os.getcwd(), tarfile), tar_dir]
    try:
        with util.chdir(tmp_dir):
            os.mkdir(tar_dir)
            _collect_system_info(tar_dir, config)
            for logfile in valid_logs:
                shutil.copy(logfile, tar_dir)
            _redact_sensitive_information(tar_dir, redact_values)
            util.subp(cmd, capture=True)
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
    sys.stderr.write('Wrote: %s\n' % tarfile)
    sys.exit(0)


def _collect_system_info(target_dir, config):
    """Copy and create system information files in the provided target_dir."""
    util.write_file(
        os.path.join(target_dir, 'version'), version.version_string())
    if os.path.isdir(CURTIN_PACK_CONFIG_DIR):
        shutil.copytree(
            CURTIN_PACK_CONFIG_DIR, os.path.join(target_dir, 'configs'))
    util.write_file(
        os.path.join(target_dir, 'curtin-config'),
        json.dumps(config, indent=1, sort_keys=True, separators=(',', ': ')))
    for fpath in ('/etc/os-release', '/proc/cmdline', '/proc/partitions'):
        shutil.copy(fpath, target_dir)
        os.chmod(os.path.join(target_dir, os.path.basename(fpath)), 0o644)
    _out, _ = util.subp(['uname', '-a'], capture=True)
    util.write_file(os.path.join(target_dir, 'uname'), _out)
    lshw_out, _ = util.subp(['sudo', 'lshw'], capture=True)
    util.write_file(os.path.join(target_dir, 'lshw'), lshw_out)
    network_cmds = [
        ['ip', '--oneline', 'address', 'list'],
        ['ip', '--oneline', '-6', 'address', 'list'],
        ['ip', '--oneline', 'route', 'list'],
        ['ip', '--oneline', '-6', 'route', 'list'],
    ]
    content = []
    for cmd in network_cmds:
        content.append('=== {cmd} ==='.format(cmd=' '.join(cmd)))
        out, err = util.subp(cmd, combine_capture=True)
        content.append(out)
    util.write_file(os.path.join(target_dir, 'network'), '\n'.join(content))


def _redact_sensitive_information(target_dir, redact_values):
    """Redact sensitive information from any files found in target_dir.

    Perform inline replacement of any matching redact_values with <REDACTED> in
    all files found in target_dir.

    @param target_dir: The directory in which to redact file content.
    @param redact_values: List of strings which need redacting from all files
        in target_dir.
    """
    for root, _, files in os.walk(target_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            with open(fpath) as stream:
                content = stream.read()
            for redact_value in redact_values:
                content = re.sub(redact_value, '<REDACTED>', content)
            util.write_file(fpath, content, mode=0o666)


CMD_ARGUMENTS = (
    ((('-o', '--output'),
      {'help': 'The output tarfile created from logs.', 'action': 'store',
       'default': "curtin-logs.tar"}),)
)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, collect_logs_main)

# vi: ts=4 expandtab syntax=python
