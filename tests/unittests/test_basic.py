from unittest import TestCase


class TestImport(TestCase):
    def test_import(self):
        import curtin
        self.assertFalse(getattr(curtin, 'BOGUS_ENTRY', None))


# vi: ts=4 expandtab syntax=python
