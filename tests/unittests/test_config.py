from unittest import TestCase

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

# vi: ts=4 expandtab syntax=python
