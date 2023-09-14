# This file is part of curtin. See LICENSE file for copyright and license info.

try:
    from abc import ABC
except ImportError:
    ABC = object
import abc
import os
import shutil
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
        util.subp(args=['smtar', '-C', target] + tar_xattr_opts() +
                  ['-Sxpf', path, '--numeric-owner'])
        return

    # Uses smtar to avoid specifying the compression type
    util.subp(args=['sh', '-cf',
                    ('wget "$1" --progress=dot:mega -O - |'
                     'smtar -C "$2" ' + ' '.join(tar_xattr_opts()) +
                     ' ' + '-Sxpf - --numeric-owner'),
                    '--', url, target])


def mount(device, mountpoint, options=None, type=None):
    opts = []
    if options is not None:
        opts.extend(['-o', options])
    if type is not None:
        opts.extend(['-t', type])
    util.subp(['mount'] + opts + [device, mountpoint], capture=True)


def unmount(mountpoint):
    util.subp(['umount', mountpoint], capture=True)


class AbstractSourceHandler(ABC):
    """Encapsulate setting up an installation source for copy_to_target.

    A source hander sets up a curtin installation source (see
    https://curtin.readthedocs.io/en/latest/topics/config.html#sources)
    for copying to the target with copy_to_target.
    """

    @abc.abstractmethod
    def setup(self):
        """Set up the source for copying and return the path to it."""
        pass

    @abc.abstractmethod
    def cleanup(self):
        """Perform any necessary clean up of actions performed by setup."""
        pass


class LayeredSourceHandler(AbstractSourceHandler):

    def __init__(self, image_stack):
        self.image_stack = image_stack
        self._tmpdir = None
        self._mounts = []

    def _download(self):
        new_image_stack = []
        for path in self.image_stack:
            if url_helper.urlparse(path).scheme not in ["", "file"]:
                new_path = os.path.join(self._tmpdir, os.path.basename(path))
                url_helper.download(path, new_path, retries=3)
            else:
                new_path = _path_from_file_url(path)
            new_image_stack.append(new_path)
        self.image_stack = new_image_stack

    def setup(self):
        self._tmpdir = tempfile.mkdtemp()
        LOG.debug(f"Setting up Layered Source for stack {self.image_stack}")
        try:
            self._download()
            # Check that all images exists on disk and are not empty
            for img in self.image_stack:
                if not os.path.isfile(img) or os.path.getsize(img) <= 0:
                    raise ValueError(
                        ("Failed to use fsimage: '%s' doesn't exist " +
                         "or is invalid") % (img,))
            for img in self.image_stack:
                mp = os.path.join(
                    self._tmpdir, os.path.basename(img) + ".dir")
                os.mkdir(mp)
                mount(img, mp, options='loop,ro')
                self._mounts.append(mp)
            if len(self._mounts) == 1:
                root_dir = self._mounts[0]
            else:
                # Multiple image files, merge them with an overlay.
                root_dir = os.path.join(self._tmpdir, "root.dir")
                os.mkdir(root_dir)
                mount(
                    'overlay', root_dir, type='overlay',
                    options='lowerdir=' + ':'.join(reversed(self._mounts)))
                self._mounts.append(root_dir)
            return root_dir
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        for mount in reversed(self._mounts):
            unmount(mount)
        self._mounts = []
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir)
        self._tmpdir = None


class TrivialSourceHandler(AbstractSourceHandler):

    def __init__(self, path):
        self.path = path

    def setup(self):
        LOG.debug(f"Setting up Trivial Source for stack {self.path}")
        return self.path

    def cleanup(self):
        pass


def _get_image_stack(uri):
    '''Find a list of dependent images for given layered fsimage path

    uri: URI of the layer file
    return: tuple of path to dependent images
    '''

    image_stack = []
    img_name = os.path.basename(uri)
    root_dir = uri[:-len(img_name)]
    img_base, img_ext = os.path.splitext(img_name)

    if not img_base:
        return []

    img_parts = img_base.split('.')
    for i in range(len(img_parts)):
        image_stack.append(
            root_dir + '.'.join(img_parts[0:i+1]) + img_ext)

    return image_stack


def get_handler_for_source(source):
    """Return an AbstractSourceHandler for setting up `source`."""
    if source['uri'].startswith("cp://"):
        return TrivialSourceHandler(source['uri'][5:])
    elif source['type'] == "fsimage":
        return LayeredSourceHandler([source['uri']])
    elif source['type'] == "fsimage-layered":
        return LayeredSourceHandler(_get_image_stack(source['uri']))
    else:
        return None


def extract_source(source, target, *, extra_rsync_args=None):
    handler = get_handler_for_source(source)
    if handler is not None:
        root_dir = handler.setup()
        try:
            copy_to_target(root_dir, target, extra_rsync_args=extra_rsync_args)
        finally:
            handler.cleanup()
    else:
        extract_root_tgz_url(source['uri'], target=target)


def copy_to_target(source, target, *, extra_rsync_args=None):
    if extra_rsync_args is None:
        extra_rsync_args = []
    if source.startswith("cp://"):
        source = source[5:]
    source = os.path.abspath(source)

    os.makedirs(target, exist_ok=True)

    util.subp(
        ['rsync', '-aXHAS', '--one-file-system'] +
        extra_rsync_args +
        [source + '/', '.'],
        cwd=target)


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
            extra_rsync_args = cfg.get(
                'install', {}).get('extra_rsync_args', [])
            extract_source(source, target, extra_rsync_args=extra_rsync_args)

    if cfg.get('write_files'):
        LOG.info("Applying write_files from config.")
        write_files(cfg['write_files'], target)
    else:
        LOG.info("No write_files in config.")
    sys.exit(0)


def POPULATE_SUBCMD(parser):
    populate_one_subcmd(parser, CMD_ARGUMENTS, extract)

# vi: ts=4 expandtab syntax=python
