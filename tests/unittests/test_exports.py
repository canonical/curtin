from unittest import TestCase

import curtin


class TestImport(TestCase):
    def test_exported_kernel_cmdline_copy_to_install(self):
        self.assertTrue(getattr(curtin, 'KERNEL_CMDLINE_COPY_TO_INSTALL_SEP'))
