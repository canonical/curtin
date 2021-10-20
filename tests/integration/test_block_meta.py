# This file is part of curtin. See LICENSE file for copyright and license info.

from collections import namedtuple
import contextlib
import sys
import yaml

from curtin import block, udev, util

from tests.unittests.helpers import CiTestCase


class IntegrationTestCase(CiTestCase):
    allowed_subp = True


@contextlib.contextmanager
def loop_dev(image):
    dev = util.subp(
        ['losetup', '--show', '--find', '--partscan', image],
        capture=True, decode='ignore')[0].strip()
    try:
        udev.udevadm_trigger([dev])
        yield dev
    finally:
        util.subp(['losetup', '--detach', dev])


PartData = namedtuple("PartData", ('number', 'offset', 'size'))


def summarize_partitions(dev):
    # We don't care about the kname
    return sorted(
        [PartData(*d[1:]) for d in block.sysfs_partition_data(dev)])


class StorageConfigBuilder:

    def __init__(self):
        self.config = []
        self.cur_image = None

    def render(self):
        return {
            'storage': {
                'config': self.config,
                },
            }

    def add_image(self, *, path, size, **kw):
        action = {
            'type': 'image',
            'id': 'id' + str(len(self.config)),
            'path': path,
            'size': size,
            }
        action.update(**kw)
        self.cur_image = action['id']
        self.config.append(action)

    def add_part(self, *, size, **kw):
        if self.cur_image is None:
            raise Exception("no current image")
        action = {
            'type': 'partition',
            'id': 'id' + str(len(self.config)),
            'device': self.cur_image,
            'size': size,
            }
        action.update(**kw)
        self.config.append(action)


class TestBlockMeta(IntegrationTestCase):

    def run_bm(self, config):
        config_path = self.tmp_path('config.yaml')
        with open(config_path, 'w') as fp:
            yaml.dump(config, fp)
        cmd = [
            sys.executable, '-m', 'curtin', '--showtrace', '-vv',
            '-c', config_path, 'block-meta', '--testmode', 'custom',
            ]
        util.subp(cmd)

    def _test_default_offsets(self, ptable):
        psize = 40 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder()
        config.add_image(path=img, size='100M', ptable=ptable)
        config.add_part(size=psize, number=1)
        config.add_part(size=psize, number=2)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(
                        number=1, offset=1 << 20, size=psize),
                    PartData(
                        number=2, offset=(1 << 20) + psize, size=psize),
                ])

    def test_default_offsets_gpt(self):
        self._test_default_offsets('gpt')

    def test_default_offsets_msdos(self):
        self._test_default_offsets('msdos')

    def _test_non_default_numbering(self, ptable):
        psize = 40 << 20
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder()
        config.add_image(path=img, size='100M', ptable=ptable)
        config.add_part(size=psize, number=1)
        config.add_part(size=psize, number=4)
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    PartData(
                        number=1, offset=1 << 20, size=psize),
                    PartData(
                        number=4, offset=(1 << 20) + psize, size=psize),
                ])

    def test_non_default_numbering_gpt(self):
        self._test_non_default_numbering('gpt')

    def BROKEN_test_non_default_numbering_msdos(self):
        self._test_non_default_numbering('msdos')

    def test_logical(self):
        img = self.tmp_path('image.img')
        config = StorageConfigBuilder()
        config.add_image(path=img, size='100M', ptable='msdos')
        config.add_part(size='50M', number=1, flag='extended')
        config.add_part(size='10M', number=5, flag='logical')
        config.add_part(size='10M', number=6, flag='logical')
        self.run_bm(config.render())

        with loop_dev(img) as dev:
            self.assertEqual(
                summarize_partitions(dev), [
                    # extended partitions get a strange size in sysfs
                    PartData(number=1, offset=1 << 20, size=1 << 10),
                    PartData(number=5, offset=2 << 20, size=10 << 20),
                    # part 5 takes us to 12 MiB offset, curtin leaves a 1 MiB
                    # gap.
                    PartData(number=6, offset=13 << 20, size=10 << 20),
                ])

            p1kname = block.partition_kname(block.path_to_kname(dev), 1)
            self.assertTrue(block.is_extended_partition('/dev/' + p1kname))
