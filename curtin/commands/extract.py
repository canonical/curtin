# This file is part of curtin. See LICENSE file for copyright and license info.

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


def extract_root_fsimage_url(url, target):
    path = _path_from_file_url(url)
    if path != url or os.path.isfile(path):
        return _extract_root_fsimage(path, target)

    wfp = tempfile.NamedTemporaryFile(suffix=".img", delete=False)
    wfp.close()
    try:
        url_helper.download(url, wfp.name, retries=3)
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


def extract_root_layered_fsimage_url(uri, target):
    ''' Build images list to consider from a layered structure

    uri: URI of the layer file
    target: Target file system to provision

    return: None
    '''
    path = _path_from_file_url(uri)

    image_stack = _get_image_stack(path)
    LOG.debug("Considering fsimages: '%s'", ",".join(image_stack))

    tmp_dir = None
    try:
        # Download every remote images if remote url
        if url_helper.urlparse(path).scheme != "":
            tmp_dir = tempfile.mkdtemp()
            image_stack = _download_layered_images(image_stack, tmp_dir)

        # Check that all images exists on disk and are not empty
        for img in image_stack:
            if not os.path.isfile(img) or os.path.getsize(img) <= 0:
                raise ValueError("Failed to use fsimage: '%s' doesn't exist " +
                                 "or is invalid", img)

        return _extract_root_layered_fsimage(image_stack, target)
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)


def _download_layered_images(image_stack, tmp_dir):
    local_image_stack = []
    try:
        for img_url in image_stack:
            dest_path = os.path.join(tmp_dir,
                                     os.path.basename(img_url))
            url_helper.download(img_url, dest_path, retries=3)
            local_image_stack.append(dest_path)
    except url_helper.UrlError as e:
        LOG.error("Failed to download '%s'" % img_url)
        raise e
    return local_image_stack


def _extract_root_layered_fsimage(image_stack, target):
    mp_base = tempfile.mkdtemp()
    mps = []
    try:
        # Create a mount point for each image file and mount the image
        try:
            for img in image_stack:
                mp = os.path.join(mp_base, os.path.basename(img) + ".dir")
                os.mkdir(mp)
                util.subp(['mount', '-o', 'loop,ro', img, mp], capture=True)
                mps.insert(0, mp)
        except util.ProcessExecutionError as e:
            LOG.error("Failed to mount '%s' for extraction: %s", img, e)
            raise e

        # Prepare
        if len(mps) == 1:
            root_dir = mps[0]
        else:
            # Multiple image files, merge them with an overlay and do the copy
            root_dir = os.path.join(mp_base, "root.dir")
            os.mkdir(root_dir)
            try:
                util.subp(['mount', '-t', 'overlay', 'overlay', '-o',
                           'lowerdir=' + ':'.join(mps), root_dir],
                          capture=True)
                mps.append(root_dir)
            except util.ProcessExecutionError as e:
                LOG.error("overlay mount to %s failed: %s", root_dir, e)
                raise e

        copy_to_target(root_dir, target)
    finally:
        umount_err_mps = []
        for mp in reversed(mps):
            try:
                util.subp(['umount', mp], capture=True)
            except util.ProcessExecutionError as e:
                LOG.error("can't unmount %s: %e", mp, e)
                umount_err_mps.append(mp)
        if umount_err_mps:
            raise util.ProcessExecutionError(
                "Failed to umount: %s", ", ".join(umount_err_mps))
        shutil.rmtree(mp_base)


def _get_image_stack(uri):
    '''Find a list of dependent images for given layered fsimage path

    uri: URI of the layer file
    return: tuple of path to dependent images
    '''

    image_stack = []
    root_dir = os.path.dirname(uri)
    img_name = os.path.basename(uri)
    _, img_ext = os.path.splitext(img_name)

    img_parts = img_name.split('.')
    # Last item is the extension
    for i in img_parts[:-1]:
        image_stack.append(
            os.path.join(
                root_dir,
                '.'.join(img_parts[0:img_parts.index(i)+1]) + img_ext))

    return image_stack


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
            elif source['type'] == "fsimage-layered":
                extract_root_layered_fsimage_url(source['uri'], target=target)
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
