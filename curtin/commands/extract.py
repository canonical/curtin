# This file is part of curtin. See LICENSE file for copyright and license info.

import os
import sys
import tempfile

import curtin.config
from curtin.log import LOG
from curtin import util
from curtin.futil import write_files
from curtin.reporter import events
from curtin import url_helper

from . import populate_one_subcmd

CMD_ARGUMENTS = (
    ((('-t', '--target'),
      {'help': ('target directory to extract to (root) '
                '[default TARGET_MOUNT_POINT]'),
       'action': 'store', 'default': os.environ.get('TARGET_MOUNT_POINT')}),
     (('sources',),
      {'help': 'the sources to install [default read from CONFIG]',
       'nargs': '*'}),
     )
)


def tar_xattr_opts(cmd=None):
    # if tar cmd supports xattrs, return the required flags to extract them.
    if cmd is None:
        cmd = ['tar']

    if isinstance(cmd, str):
        cmd = [cmd]

    (out, _err) = util.subp(cmd + ['--help'], capture=True)

    if "xattr" in out:
        return ['--xattrs', '--xattrs-include=*']
    return []


def extract_root_tgz_url(url, target):
    # extract a -root.tar.gz url in the 'target' directory
    path = _path_from_file_url(url)
    if path != url or os.path.isfile(path):
        util.subp(args=['tar', '-C', target] + tar_xattr_opts() +
                  ['-Sxpzf', path, '--numeric-owner'])
        return

    # Uses smtar to avoid specifying the compression type
    util.subp(args=['sh', '-cf',
                    ('wget "$1" --progress=dot:mega -O - |'
                     'smtar -C "$2" ' + ' '.join(tar_xattr_opts()) +
                     ' ' + '-Sxpf - --numeric-owner'),
                    '--', url, target])


def extract_root_fsimage_url(url, target):
    path = _path_from_file_url(url)
    if path != url or os.path.isfile(path):
        return _extract_root_fsimage(path, target)

    wfp = tempfile.NamedTemporaryFile(suffix=".img", delete=False)
    wfp.close()
    try:
        url_helper.download(url, wfp.name)
        return _extract_root_fsimage(wfp.name, target)
    finally:
        os.unlink(wfp.name)


def _extract_root_fsimage(path, target):
    mp = tempfile.mkdtemp()
    try:
        util.subp(['mount', '-o', 'loop,ro', path, mp], capture=True)
    except util.ProcessExecutionError as e:
        LOG.error("Failed to mount '%s' for extraction: %s", path, e)
        os.rmdir(mp)
        raise e
    try:
        return copy_to_target(mp, target)
    finally:
        util.subp(['umount', mp])
        os.rmdir(mp)


def copy_to_target(source, target):
    if source.startswith("cp://"):
        source = source[5:]
    source = os.path.abspath(source)

    util.subp(args=['sh', '-c',
                    ('mkdir -p "$2" && cd "$2" && '
                     'rsync -aXHAS --one-file-system "$1/" .'),
                    '--', source, target])


def _path_from_file_url(url):
    return url[7:] if url.startswith("file://") else url


def extract(args):
    if not args.target:
        raise ValueError("Target must be defined or set in environment")

    state = util.load_command_environment()
    cfg = curtin.config.load_command_config(args, state)

    sources = args.sources
    target = args.target
    if not sources:
        if not cfg.get('sources'):
            raise ValueError("'sources' must be on cmdline or in config")
        sources = cfg.get('sources')

    if isinstance(sources, dict):
        sources = [sources[k] for k in sorted(sources.keys())]

    sources = [util.sanitize_source(s) for s in sources]

    LOG.debug("Installing sources: %s to target at %s" % (sources, target))
    stack_prefix = state.get('report_stack_prefix', '')

    for source in sources:
        with events.ReportEventStack(
                name=stack_prefix, reporting_enabled=True, level="INFO",
                description="acquiring and extracting image from %s" %
                source['uri']):
            if source['type'].startswith('dd-'):
                continue
            if source['uri'].startswith("cp://"):
                copy_to_target(source['uri'], target)
            elif source['type'] == "fsimage":
                extract_root_fsimage_url(source['uri'], target=target)
            else:
                extract_root_tgz_url(source['uri'], target=target)

    if cfg.get('write_files'):
        LOG.info("Applying write_files from config.")
        write_files(cfg['write_files'], target)
    else:
        LOG.info("No write_files in config.")
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, extract)

# vi: ts=4 expandtab syntax=python
