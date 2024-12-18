# This file is part of curtin. See LICENSE file for copyright and license info.

import copy
import json
import textwrap
import typing

import attr

from curtin import config
from .helpers import CiTestCase


class TestMerge(CiTestCase):
    def test_merge_cfg_string(self):
        d1 = {'str1': 'str_one'}
        d2 = {'dict1': {'d1.e1': 'd1-e1'}}

        expected = {'str1': 'str_one', 'dict1': {'d1.e1': 'd1-e1'}}
        config.merge_config(d1, d2)
        self.assertEqual(d1, expected)


class TestCmdArg2Cfg(CiTestCase):
    def test_cmdarg_flat(self):
        self.assertEqual(config.cmdarg2cfg("foo=bar"), {'foo': 'bar'})

    def test_dict_dict(self):
        self.assertEqual(config.cmdarg2cfg("foo/v1/v2=bar"),
                         {'foo': {'v1': {'v2': 'bar'}}})

    def test_no_equal_raises_value_error(self):
        self.assertRaises(ValueError, config.cmdarg2cfg, "foo/v1/v2"),

    def test_json(self):
        self.assertEqual(
            config.cmdarg2cfg('json:foo/bar=["a", "b", "c"]', delim="/"),
            {'foo': {'bar': ['a', 'b', 'c']}})

    def test_cmdarg_multiple_equal(self):
        self.assertEqual(
            config.cmdarg2cfg("key=mykey=value"),
            {"key": "mykey=value"})

    def test_with_merge_cmdarg(self):
        cfg1 = {'foo': {'key1': 'val1', 'mylist': [1, 2]}, 'f': 'fval'}
        cfg2 = {'foo': {'key2': 'val2', 'mylist2': ['a', 'b']}, 'g': 'gval'}

        via_merge = copy.deepcopy(cfg1)
        config.merge_config(via_merge, cfg2)

        via_merge_cmdarg = copy.deepcopy(cfg1)
        config.merge_cmdarg(via_merge_cmdarg, 'json:=' + json.dumps(cfg2))

        self.assertEqual(via_merge, via_merge_cmdarg)


class TestConfigArchive(CiTestCase):
    def test_archive_dict(self):
        myarchive = _replace_consts(textwrap.dedent("""
            _ARCH_HEAD_
            - type: _CONF_TYPE_
              content: |
                key1: val1
                key2: val2
            - content: |
               _CONF_HEAD_
               key1: override_val1
        """))
        ret = config.load_config_archive(myarchive)
        self.assertEqual(ret, {'key1': 'override_val1', 'key2': 'val2'})

    def test_archive_string(self):
        myarchive = _replace_consts(textwrap.dedent("""
            _ARCH_HEAD_
            - |
              _CONF_HEAD_
              key1: val1
              key2: val2
            - |
              _CONF_HEAD_
              key1: override_val1
        """))
        ret = config.load_config_archive(myarchive)
        self.assertEqual(ret, {'key1': 'override_val1', 'key2': 'val2'})

    def test_archive_mixed_dict_string(self):
        myarchive = _replace_consts(textwrap.dedent("""
            _ARCH_HEAD_
            - type: _CONF_TYPE_
              content: |
                key1: val1
                key2: val2
            - |
              _CONF_HEAD_
              key1: override_val1
        """))
        ret = config.load_config_archive(myarchive)
        self.assertEqual(ret, {'key1': 'override_val1', 'key2': 'val2'})

    def test_recursive_string(self):
        myarchive = _replace_consts(textwrap.dedent("""
            _ARCH_HEAD_
            - |
              _ARCH_HEAD_
              - |
                _CONF_HEAD_
                key1: val1
                key2: val2
            - |
              _ARCH_HEAD_
               - |
                 _CONF_HEAD_
                 key1: override_val1
        """))
        ret = config.load_config_archive(myarchive)
        self.assertEqual(ret, {'key1': 'override_val1', 'key2': 'val2'})

    def test_recursive_dict(self):
        myarchive = _replace_consts(textwrap.dedent("""
            _ARCH_HEAD_
            - type: _CONF_TYPE_
              content: |
                key1: val1
                key2: val2
            - content: |
                _ARCH_HEAD_
                 - |
                   _CONF_HEAD_
                   key1: override_val1
        """))
        ret = config.load_config_archive(myarchive)
        self.assertEqual(ret, {'key1': 'override_val1', 'key2': 'val2'})


def _replace_consts(cfgstr):
    repls = {'_ARCH_HEAD_': config.ARCHIVE_HEADER,
             '_ARCH_TYPE_': config.ARCHIVE_TYPE,
             '_CONF_HEAD_': config.CONFIG_HEADER,
             '_CONF_TYPE_': config.CONFIG_TYPE}
    for k, v in repls.items():
        cfgstr = cfgstr.replace(k, v)
    return cfgstr


class TestDeserializer(CiTestCase):

    def test_scalar(self):
        deserializer = config.Deserializer()
        self.assertEqual(1, deserializer.deserialize(int, 1))
        self.assertEqual("a", deserializer.deserialize(str, "a"))

    def test_attr(self):
        deserializer = config.Deserializer()

        @attr.s(auto_attribs=True)
        class Point:
            x: int
            y: int

        self.assertEqual(
            Point(x=1, y=2),
            deserializer.deserialize(Point, {'x': 1, 'y': 2}))

    def test_list(self):
        deserializer = config.Deserializer()
        self.assertEqual(
            [1, 2, 3],
            deserializer.deserialize(typing.List[int], [1, 2, 3]))

    def test_optional(self):
        deserializer = config.Deserializer()
        self.assertEqual(
            1,
            deserializer.deserialize(typing.Optional[int], 1))
        self.assertEqual(
            None,
            deserializer.deserialize(typing.Optional[int], None))

    def test_converter(self):
        deserializer = config.Deserializer()

        @attr.s(auto_attribs=True)
        class WithoutConverter:
            val: bool

        with self.assertRaises(config.SerializationError):
            deserializer.deserialize(WithoutConverter, {"val": "on"})

        @attr.s(auto_attribs=True)
        class WithConverter:
            val: bool = attr.ib(converter=config.value_as_boolean)

        self.assertEqual(
            WithConverter(val=True),
            deserializer.deserialize(WithConverter, {"val": "on"}))

    def test_dash_to_underscore(self):
        deserializer = config.Deserializer()

        @attr.s(auto_attribs=True)
        class DashToUnderscore:
            a_b: bool = False

        self.assertEqual(
            DashToUnderscore(a_b=True),
            deserializer.deserialize(DashToUnderscore, {"a-b": True}))

    def test_union_str_list(self):
        deserializer = config.Deserializer()

        @attr.s(auto_attribs=True)
        class UnionClass:
            val: typing.Union[str | list | None]

        self.assertEqual(
            UnionClass(val="a"),
            deserializer.deserialize(UnionClass, {"val": "a"}))

        self.assertEqual(
            UnionClass(val=["b"]),
            deserializer.deserialize(UnionClass, {"val": ["b"]}))

        self.assertEqual(
            UnionClass(val=None),
            deserializer.deserialize(UnionClass, {"val": None}))


class TestBootCfg(CiTestCase):
    def test_empty(self):
        with self.assertRaises(TypeError) as exc:
            config.BootCfg()
        self.assertIn("missing 1 required positional argument: 'bootloaders'",
                      str(exc.exception))

    def test_not_list(self):
        with self.assertRaises(ValueError) as exc:
            config.BootCfg('invalid')
        self.assertIn("bootloaders must be a list: invalid",
                      str(exc.exception))

    def test_empty_list(self):
        with self.assertRaises(ValueError) as exc:
            config.BootCfg([])
        self.assertIn("Empty bootloaders list:", str(exc.exception))

    def test_duplicate(self):
        with self.assertRaises(ValueError) as exc:
            config.BootCfg(['grub', 'grub'])
        self.assertIn("bootloaders list contains duplicates: ['grub', 'grub']",
                      str(exc.exception))

    def test_invalid(self):
        with self.assertRaises(ValueError) as exc:
            config.BootCfg(['fred'])
        self.assertIn("Unknown bootloader fred: ['fred']", str(exc.exception))

    def test_valid(self):
        config.BootCfg(['grub'])


# vi: ts=4 expandtab syntax=python
