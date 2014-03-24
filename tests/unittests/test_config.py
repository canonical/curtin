from unittest import TestCase
import textwrap

from curtin import config


class TestMerge(TestCase):
    def test_merge_cfg_string(self):
        d1 = {'str1': 'str_one'}
        d2 = {'dict1': {'d1.e1': 'd1-e1'}}

        expected = {'str1': 'str_one', 'dict1': {'d1.e1': 'd1-e1'}}
        config.merge_config(d1, d2)
        self.assertEqual(d1, expected)


class TestCmdArg2Cfg(TestCase):
    def test_cmdarg_flat(self):
        self.assertEqual(config.cmdarg2cfg("foo=bar"), {'foo': 'bar'})

    def test_dict_dict(self):
        self.assertEqual(config.cmdarg2cfg("foo/v1/v2=bar"),
                         {'foo': {'v1': {'v2': 'bar'}}})

    def test_no_equal_raises_value_error(self):
        self.assertRaises(ValueError, config.cmdarg2cfg, "foo/v1/v2"),


class TestConfigArchive(TestCase):
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

# vi: ts=4 expandtab syntax=python
