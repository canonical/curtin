#!/usr/bin/python3
# This file is part of curtin. See LICENSE file for copyright and license info.

from simplestreams import util as sutil
from simplestreams import contentsource
from simplestreams import objectstores
from simplestreams import log
from simplestreams.log import LOG
from simplestreams import mirrors
from simplestreams import filters

import argparse
import errno
import hashlib
import os
import signal
import sys

try:
    from json.decoder import JSONDecodeError
except ImportError:
    # python3.4 (trusty) does not have a JSONDecodeError
    # and raises simple ValueError on decode fail.
    JSONDecodeError = ValueError

from curtin import util


def environ_get(key, default):
    """Try CURTIN_VMTEST_<key> envvar then <key> envvar, else use default"""
    long_key = 'CURTIN_VMTEST_' + key
    return os.environ.get(long_key, os.environ.get(key, default))


IMAGE_SRC_URL = environ_get(
    'IMAGE_SRC_URL',
    "http://maas.ubuntu.com/images/ephemeral-v3/daily/streams/v1/index.sjson")
IMAGE_DIR = environ_get("IMAGE_DIR", "/srv/images")

KEYRING = environ_get(
    'IMAGE_SRC_KEYRING',
    '/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg')
ITEM_NAME_FILTERS = \
    ['ftype~(boot-initrd|boot-kernel|root-tgz|squashfs)']
FORMAT_JSON = 'JSON'
STREAM_BASE = 'com.ubuntu.maas:daily'
VMTEST_CONTENT_ID_PATH_MAP = {
    STREAM_BASE + ":v3:download": "streams/v1/vmtest.json",
    STREAM_BASE + ":centos-bases-download": "streams/v1/vmtest-centos.json",
}

DEFAULT_OUTPUT_FORMAT = ("%(release)-7s %(arch)s/%(subarch)s/%(kflavor)s "
                         "%(version_name)-10s %(item_name)s")

DEFAULT_ARCHES = {
    'i386': ['i386'],
    'i586': ['i386'],
    'i686': ['i386'],
    'x86_64': ['amd64'],
    'ppc64le': ['ppc64el'],
    'armhf': ['armhf'],
    'aarch64': ['arm64'],
    's390x': ['s390x'],
}


def get_file_info(path, sums=None):
    # return dictionary with size and checksums of existing file
    LOG.info("getting info for %s" % path)
    buflen = 1024*1024

    if sums is None:
        sums = ['sha256']
    sumers = {k: hashlib.new(k) for k in sums}

    ret = {'size': os.path.getsize(path)}
    with open(path, "rb") as fp:
        while True:
            buf = fp.read(buflen)
            for sumer in sumers.values():
                sumer.update(buf)
            if len(buf) != buflen:
                break

    ret.update({k: sumers[k].hexdigest() for k in sumers})
    LOG.info("done getting ifo for %s: %s" % (path, ret))
    return ret


def remove_empty_dir(dirpath):
    if os.path.exists(dirpath):
        # normpath never returns trailing / (unless '/')
        # so that dirname will always get our parent.
        dirpath = os.path.normpath(dirpath)
        try:
            os.rmdir(dirpath)
            LOG.info("removed empty directory '%s'", dirpath)
            remove_empty_dir(os.path.dirname(dirpath))
        except OSError as e:
            if e.errno == errno.ENOTEMPTY:
                pass


class FakeContentSource(contentsource.ContentSource):
    def __init__(self, path):
        self.url = path

    def open(self):
        raise ValueError(
            "'%s' content source never expected to be read" % self.url)


def products_version_get(tree, pedigree):
    tprod = tree.get('products', {}).get(pedigree[0], {})
    return tprod.get('versions', {}).get(pedigree[1], {})


class CurtinVmTestMirror(mirrors.ObjectFilterMirror):
    # This class works as a 'target' mirror.
    # it creates the vmtest files as it needs them and
    # writes the maas image files and maas json files intact.
    # but adds a streams/v1/vmtest.json file the created data.
    def __init__(self, config, out_d, verbosity=0):

        self.config = config
        self.filters = self.config.get('filters', [])
        self.out_d = os.path.abspath(out_d)
        self.objectstore = objectstores.FileStore(
            out_d, complete_callback=self.callback)
        self.file_info = {}
        self.data_path = ".vmtest-data"
        super(CurtinVmTestMirror, self).__init__(config=config,
                                                 objectstore=self.objectstore)

        self.verbosity = verbosity
        self.dlstatus = {'columns': 80, 'total': 0, 'curpath': None}

    def callback(self, path, cur_bytes, tot_bytes):
        # progress written to screen
        if self.verbosity == 0:
            return

        # this is taken logically from simplstreams DotProgress
        if self.dlstatus['curpath'] != path:
            self.dlstatus['printed'] = 0
            self.dlstatus['curpath'] = path
            sys.stderr.write('=> %s [%s]\n' % (path, tot_bytes))

        if cur_bytes == tot_bytes:
            self.dlstatus['total'] += tot_bytes
            sys.stderr.write("\n")
            return

        columns = self.dlstatus['columns']
        printed = self.dlstatus['printed']
        toprint = int(cur_bytes * columns / tot_bytes) - printed
        if toprint <= 0:
            return
        sys.stderr.write('.' * toprint)
        sys.stderr.flush()
        self.dlstatus['printed'] += toprint

    def fpath(self, path):
        # return the full path to a local file in the mirror
        return os.path.join(self.out_d, path)

    def products_data_path(self, content_id):
        # our data path is .vmtest-data rather than .data
        return self.data_path + os.path.sep + content_id

    def _reference_count_data_path(self):
        # overridden from ObjectStoreMirrorWriter
        return self.data_path + os.path.sep + "references.json"

    def load_products(self, path=None, content_id=None, remove=True):
        # overridden from ObjectStoreMirrorWriter
        # the reason is that we have copied here from trunk
        # is bug 1511364 which is not fixed in all ubuntu versions
        if content_id:
            try:
                dpath = self.products_data_path(content_id)
                return sutil.load_content(self.source(dpath).read())
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
            except JSONDecodeError:
                jsonfile = os.path.join(self.out_d, dpath)
                sys.stderr.write("Decode error in:\n  "
                                 "content_id=%s\n  "
                                 "JSON filepath=%s\n" % (content_id,
                                                         jsonfile))
                if remove is True:
                    sys.stderr.write("Removing offending file: %s\n" %
                                     jsonfile)
                    util.del_file(jsonfile)
                    sys.stderr.write("Trying to load products again...\n")
                    sys.stderr.flush()
                    return self.load_products(path=path, content_id=content_id,
                                              remove=False)
                raise

        if path:
            return {}

        raise TypeError("unable to load_products with no path")

    def get_file_info(self, path):
        # check and see if we might know checksum and size
        if path in self.file_info:
            return self.file_info[path]
        found = get_file_info(path)
        self.file_info[path] = found
        return found

    def remove_item(self, data, src, target, pedigree):
        super(CurtinVmTestMirror, self).remove_item(data, src, target,
                                                    pedigree)
        if 'path' in data:
            remove_empty_dir(self.fpath(os.path.dirname(data['path'])))

    def insert_products(self, path, target, content):
        # The super classes' insert_products will
        # we override this because default  mirror inserts content
        # where as we want to insert the rendered 'target' tree
        # the difference is that 'content' is the original (with gpg sign)
        # so our content will no longer have that signature.

        dpath = self.products_data_path(target['content_id'])
        self.store.insert_content(dpath, util.json_dumps(target))
        if not path:
            return
        # this will end up writing the content exactly as it
        # was in the source, leaving the signed data in-tact
        self.store.insert_content(path, content)

        # for our vmtest content id, we want to write
        # a json file in streams/v1/<distro>.json that can be queried
        # even though it will not appear in index
        vmtest_json = VMTEST_CONTENT_ID_PATH_MAP.get(target['content_id'])
        if vmtest_json:
            self.store.insert_content(vmtest_json, util.json_dumps(target))

    def insert_index_entry(self, data, src, pedigree, contentsource):
        # this is overridden, because the default implementation
        # when syncing an index.json will call insert_products
        # and also insert_index_entry. And both actually end up
        # writing the .[s]json file that they should write. Since
        # insert_products will do that, we just no-op this.
        return


def set_logging(verbose, log_file):
    vlevel = min(verbose, 2)
    level = (log.ERROR, log.INFO, log.DEBUG)[vlevel]
    log.basicConfig(stream=log_file, level=level)
    return vlevel


def main_mirror(args):
    if len(args.arches) == 0:
        try:
            karch = os.uname()[4]
            arches = DEFAULT_ARCHES[karch]
        except KeyError:
            msg = "No default arch list for kernel arch '%s'. Try '--arches'."
            sys.stderr.write(msg % karch + "\n")
            return False
    else:
        arches = []
        for f in args.arches:
            arches.extend(f.split(","))

    arch_filter = "arch~(" + "|".join(arches) + ")"

    mirror_filters = [arch_filter] + ITEM_NAME_FILTERS + args.filters

    vlevel = set_logging(args.verbose, args.log_file)

    sys.stderr.write(
        "summary: \n " + '\n '.join([
            "source: %s" % args.source,
            "output: %s" % args.output_d,
            "arches: %s" % arches,
            "filters: %s" % mirror_filters,
        ]) + '\n')

    mirror(output_d=args.output_d, source=args.source,
           mirror_filters=mirror_filters, max_items=args.max_items,
           keyring=args.keyring, verbosity=vlevel)


def mirror(output_d, source=IMAGE_SRC_URL, mirror_filters=None, max_items=1,
           keyring=KEYRING, verbosity=0):
    if mirror_filters is None:
        mirror_filters = [f for f in ITEM_NAME_FILTERS]

    filter_list = filters.get_filters(mirror_filters)

    (source_url, initial_path) = sutil.path_from_mirror_url(source, None)

    def policy(content, path):  # pylint: disable=W0613
        if initial_path.endswith('sjson'):
            return sutil.read_signed(content, keyring=keyring)
        else:
            return content

    smirror = mirrors.UrlMirrorReader(source_url, policy=policy)

    LOG.debug(
        "summary: \n " + '\n '.join([
            "source: %s" % source_url,
            "path: %s" % initial_path,
            "output: %s" % output_d,
            "filters: %s" % filter_list,
        ]) + '\n')

    mirror_config = {'max_items': max_items, 'filters': filter_list}
    tmirror = CurtinVmTestMirror(config=mirror_config, out_d=output_d,
                                 verbosity=verbosity)

    tmirror.sync(smirror, initial_path)


def query_ptree(ptree, max_num=None, ifilters=None, path2url=None):
    results = []
    pkey = 'products'
    verkey = 'versions'
    for prodname, proddata in sorted(ptree.get(pkey, {}).items()):
        if verkey not in proddata:
            continue
        cur = 0
        for vername in sorted(proddata[verkey].keys(), reverse=True):
            if max_num is not None and cur >= max_num:
                break
            verdata = proddata[verkey][vername]
            cur += 1
            for itemname, itemdata in sorted(verdata.get('items', {}).items()):
                flat = sutil.products_exdata(ptree,
                                             (prodname, vername, itemname))
                if ifilters is not None and len(ifilters) > 0:
                    if not filters.filter_dict(ifilters, flat):
                        continue
                if path2url and 'path' in flat:
                    flat['item_url'] = path2url(flat['path'])
                results.append(flat)
    return results


def query(mirror, max_items=1, filter_list=None, verbosity=0):
    if filter_list is None:
        filter_list = []
    ifilters = filters.get_filters(filter_list)

    def fpath(path):
        return os.path.join(mirror, path)

    return next((q for q in (
        query_ptree(sutil.load_content(util.load_file(fpath(path))),
                    max_num=max_items, ifilters=ifilters, path2url=fpath)
        for path in VMTEST_CONTENT_ID_PATH_MAP.values() if os.path.exists(
            fpath(path))) if q), [])


def main_query(args):
    vlevel = set_logging(args.verbose, args.log_file)

    results = query(args.mirror_url, args.max_items, args.filters,
                    verbosity=vlevel)
    try:
        if args.output_format == FORMAT_JSON:
            print(util.json_dumps(results).decode())
        else:
            output = []
            for item in results:
                try:
                    output.append(args.output_format % item)
                except KeyError as e:
                    sys.stderr.write("output format failed (%s) for: %s\n" %
                                     (e, item))
                    sys.exit(1)
            for line in sorted(output):
                print(line)
    except IOError as e:
        if e.errno == errno.EPIPE:
            sys.exit(0x80 | signal.SIGPIPE)
        raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--log-file', default=sys.stderr,
                        type=argparse.FileType('w'))
    parser.add_argument('--verbose', '-v', action='count', default=0)

    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers(help='subcommand help')
    mirror_p = subparsers.add_parser(
        'mirror', help='like sstream-mirror but for vmtest images')
    mirror_p.set_defaults(func=main_mirror)
    mirror_p.add_argument('--max', type=int, default=1, dest='max_items',
                          help='store at most MAX items in the target')
    mirror_p.add_argument('--verbose', '-v', action='count', default=0)
    mirror_p.add_argument('--dry-run', action='store_true', default=False,
                          help='only report what would be done')
    mirror_p.add_argument('--arches', action='append',
                          default=[], help='which arches to mirror.')
    mirror_p.add_argument('--source', default=IMAGE_SRC_URL,
                          help='maas images mirror')
    mirror_p.add_argument('--keyring', action='store', default=KEYRING,
                          help='keyring to be specified to gpg via --keyring')
    mirror_p.add_argument('output_d')
    mirror_p.add_argument('filters', nargs='*', default=[])

    query_p = subparsers.add_parser(
        'query', help='like sstream-query but for vmtest mirror')
    query_p.set_defaults(func=main_query)
    query_p.add_argument('--max', type=int, default=None, dest='max_items',
                         help='store at most MAX items in the target')
    query_p.add_argument('--path', default=None,
                         help='sync from index or products file in mirror')

    fmt_group = query_p.add_mutually_exclusive_group()
    fmt_group.add_argument('--output-format', '-o', action='store',
                           dest='output_format', default=DEFAULT_OUTPUT_FORMAT,
                           help="specify output format per python str.format")
    fmt_group.add_argument('--json', action='store_const',
                           const=FORMAT_JSON, dest='output_format',
                           help="output in JSON as a list of dicts.")
    query_p.add_argument('--verbose', '-v', action='count', default=0)

    query_p.add_argument('mirror_url')
    query_p.add_argument('filters', nargs='*', default=[])

    args = parser.parse_args()

    if args.func is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
    sys.exit(0)

# vi: ts=4 expandtab syntax=python
