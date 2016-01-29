#!/usr/bin/python3

from simplestreams import util as sutil
from simplestreams import contentsource
from simplestreams import objectstores
from simplestreams import log
from simplestreams.log import LOG
from simplestreams import mirrors
from simplestreams import filters

import argparse
import copy
import errno
import hashlib
import json
import os
import shutil
import sys
import tempfile

from curtin import util

IMAGE_SRC_URL = os.environ.get(
    'IMAGE_SRC_URL',
    "http://maas.ubuntu.com/images/ephemeral-v2/daily/streams/v1/index.sjson")

KEYRING = '/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg'
ITEM_NAME_FILTERS = ['ftype~(root-image.gz|boot-initrd|boot-kernel)']
FORMAT_JSON = 'JSON'

DEFAULT_ARCHES = {
    'i386': ['i386'],
    'i586': ['i386'],
    'i686': ['i386'],
    'x86_64': ['amd64'],
    'ppc64le': ['ppc64el'],
    'armhf': ['armhf'],
    'aarch64': ['arm64'],
}

def get_file_info(path, sums=None):
    # return dictionary with size and checksums of existing file
    LOG.info("getting ifo for %s" % path)
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


class MyObjectStore(object):
    paths = {}
        
    def __init__(self, out_d):
        print("new: %s" % out_d)
        self.out_d = out_d
        
    def insert(self, path, reader, checksums=None, mutable=True, size=None):
        # store content from reader.read() into path, expecting result checksum
        print("insert: path=%s reader=%s checksums=%s mutable=%s size=%s" %
              (path, reader, checksums, mutable, size))
        if path and path.startswith(".vmtest-data"):
            self.paths[path] = reader.read()
        elif path:
            self.paths[path] = str(path) + " " + str(reader)
        else:
            raise ValueError("FOO bad path")
            
    def insert_content(self, path, content, checksums=None, mutable=True):
        if not isinstance(content, bytes):
            content = content.encode('utf-8')
        self.insert(path=path, reader=contentsource.MemoryContentSource(content=content),
                    checksums=checksums, mutable=mutable)
                
    def remove(self, path):
        # remove path from store
        print("remove: path=%s" % path)
        del self.paths[path]
        
    def source(self, path):
        try:
            return contentsource.MemoryContentSource(content=self.paths[path])
        except KeyError:
            raise IOError(errno.ENOENT, '%s not found' % path)

    def exists_with_checksum(self, path, checksums=None):
        return (path in self.paths)


def generate_root_derived(path_gz, base_d="/"):
    fpath_gz = os.path.join(base_d, path_gz)
    ri_name = 'vmtest.root-image'
    rtgz_name = 'vmtest.root-tgz'
    ri_path = os.path.dirname(path_gz) + "/" + ri_name
    rtgz_path = os.path.dirname(path_gz) + "/" + rtgz_name
    ri_fpath = os.path.join(base_d, ri_path)
    rtgz_fpath = os.path.join(base_d, rtgz_path)
    new_items = {ri_name: {'ftype': ri_name, 'path': ri_path},
                 rtgz_name: {'ftype': rtgz_name, 'path': rtgz_path}}
    
    tmpd = None
    try:
        # create tmpdir under output dir
        tmpd = tempfile.mkdtemp(dir=os.path.dirname(fpath_gz))
        tmp_img = ri_fpath
        tmp_rtgz = rtgz_fpath
        if not os.path.exists(ri_fpath):
            # uncompress path_gz to tmpdir/root-image
            tmp_img = os.path.join(tmpd, ri_name)
            LOG.info("uncompressing %s to %s" % (fpath_gz, tmp_img))
            util.subp(['sh', '-c', 'exec gunzip -c "$0" > "$1"',
                      fpath_gz, tmp_img])
        if not os.path.exists(rtgz_fpath):
            tmp_rtgz = os.path.join(tmpd, rtgz_name)
            m2r = ['tools/maas2roottar', tmp_img, tmp_rtgz]
            LOG.info("creating root-tgz from %s" % tmp_img)
            util.subp(m2r)

        if tmp_img != ri_fpath:
            os.rename(tmp_img, ri_fpath)
        if tmp_rtgz != rtgz_fpath:
            os.rename(tmp_rtgz, rtgz_fpath)

    finally:
        if tmpd:
            shutil.rmtree(tmpd)

    new_items[ri_name].update(get_file_info(ri_fpath))
    new_items[rtgz_name].update(get_file_info(rtgz_fpath))

    return new_items


def remove_empty_dir(dirpath):
    if os.path.exists(dirpath):
        try:
            os.rmdir(dirpath)
        except OSError as e:
            if e.errno == errno.ENOTEMPTY:
                pass


class FakeContentSource(contentsource.ContentSource):
    def __init__(self, path):
        self.url = path

    def open(self):
        raise ValueError("'%s' content source never expected to be read" %
                         self.path)


def products_version_get(tree, pedigree):
    tprod = tree.get('products', {}).get(pedigree[0], {})
    return tprod.get('versions', {}).get(pedigree[1], {})


class CurtinVmTestMirror(mirrors.ObjectFilterMirror):
    def __init__(self, config, out_d, verbosity=0):

        self.config = config
        self.filters = self.config.get('filters', [])
        self.out_d = os.path.abspath(out_d)
        self.objectstore = objectstores.FileStore(
            out_d, complete_callback=self.callback)
        super(CurtinVmTestMirror, self).__init__(config=config,
                                                 objectstore=self.objectstore)

    def source(self, path):
        return self.objectstore.source(path)

    def fpath(self, path):
        return os.path.join(self.out_d, path)

    def read_json(self, path):
        with self.source(path) as source:
            raw = source.read().decode('utf-8')
        return raw, self.policy(content=raw, path=path)

    def callback(self, path, cur_bytes, tot_bytes):
        pass

    def products_data_path(self, content_id):
        return ".vmtest-data/%s" % content_id

    def _reference_count_data_path(self):
	# less than ideal to override this. but want to leave .data alone
        return ".vmtest-data/references.json"

    def load_products(self, path=None, content_id=None):
        if content_id:
            try:
                dpath = self.products_data_path(content_id)
                return sutil.load_content(self.source(dpath).read())
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise

        if path:
            return {}

        raise TypeError("unable to load_products with no path")

    def insert_version(self, data, src, target, pedigree):
        # this is called for any version that had items inserted
        # data target['products'][pedigree[0]]['versions'][pedigree[1]]
        # a dictionary with possibly some tags and 'items': {'boot_initrd}...
        items = data.get('items', {})
        ri_name = 'vmtest.root-image'
        rtgz_name = 'vmtest.root-tgz'
        tver_data = products_version_get(target, pedigree)
        titems = tver_data.get('items')

        if ('root-image.gz' in titems and
                not (ri_name in titems and rtgz_name in titems)):
            # generate the root-image and root-tgz
            derived_items = generate_root_derived(
                titems['root-image.gz']['path'], base_d=self.out_d)
            for fname, item in derived_items.items():
                self.insert_item(item, src, target, pedigree + (fname,),
                                 FakeContentSource(item['path']))

    def remove_version(self, data, src, target, pedigree):
        # called for versions that were removed.
        print("removing %s" % ','.join(pedigree))
        for item in data.get('items', {}).values():
            if 'path' in item:
                remove_empty_dir(os.path.join(self.out_d,
                                              os.path.dirname(item['path'])))


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

    filter_list = filters.get_filters([arch_filter] + ITEM_NAME_FILTERS + args.filters)

    (source_url, initial_path) = sutil.path_from_mirror_url(args.source, None)

    def policy(content, path):  # pylint: disable=W0613
        if initial_path.endswith('sjson'):
            return sutil.read_signed(content, keyring=args.keyring)
        else:
            return content

    mirror_config = {'max_items': args.max_items, 'filters': filter_list}

    vlevel = set_logging(args.verbose, args.log_file)

    smirror = mirrors.UrlMirrorReader(source_url, policy=policy)

    LOG.info(
        "summary: \n " + '\n '.join([
            "source: %s" % args.source,
            "output: %s" % args.output_d,
            "arches: %s" % arches,
            "filters: %s" % filter_list,
        ]) + '\n')

    tmirror = CurtinVmTestMirror(config=mirror_config, out_d=args.output_d,
                                 verbosity=vlevel)

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
                flat = sutil.products_exdata(ptree, (prodname, vername, itemname))
                if not ifilters:
                    if not filters.filter_dict(ifilters, flat):
                        continue
                if path2url and 'path' in flat:
                    flat['item_url'] = path2url(flat['path'])
                results.append(flat)
    return results


def jdump(thing):
    return json.dumps(thing, indent=2, sort_keys=True, separators=(',', ': '))


def main_query(args):
    vlevel = set_logging(args.verbose, args.log_file)
    filter_list = filters.get_filters(args.filters)

    smirror = CurtinVmTestMirror(config={}, out_d=args.mirror_url, verbosity=vlevel)
    stree = smirror.load_products(content_id='com.ubuntu.maas:daily:v2:download')
    results = query_ptree(stree, max_num=args.max_items, ifilters=filter_list,
                          path2url=smirror.fpath)

    try:
        print(jdump(results))
    except IOError as e:
        if e.errno == errno.EPIPE:
            sys.exit(0x80 | signal.SIGPIPE)
        raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--log-file', default=sys.stderr,
                        type=argparse.FileType('w'))
    parser.add_argument('--verbose', '-v', action='count', default=0)

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
                           dest='output_format', default=None,
                           help="specify output format per python str.format")
    fmt_group.add_argument('--json', action='store_const',
                           const=FORMAT_JSON, dest='output_format',
                           help="output in JSON as a list of dicts.")
    query_p.add_argument('--verbose', '-v', action='count', default=0)

    query_p.add_argument('mirror_url')
    query_p.add_argument('filters', nargs='*', default=[])

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    #ret = generate_root_derived(sys.argv[1], sys.argv[2])
    #print(ret)
    #sys.exit(0)
    main()

# vi: ts=4 expandtab syntax=python
