import mock
import random

from curtin.config import merge_config
from curtin.block import dasd
from curtin.util import ProcessExecutionError
from .helpers import CiTestCase

def random_bus_id():
    return "%x.%x.%04x" % (random.randint(0, 16),
                           random.randint(0, 16),
                           random.randint(1024, 4096))

class TestLsdasd(CiTestCase):

    def setUp(self):
        super(TestLsdasd, self).setUp()
        self.add_patch('curtin.block.dasd.util.subp', 'm_subp')

        # defaults
        self.m_subp.return_value = (None, None)

    def test_noargs(self):
        """lsdasd invoked with --long --offline with no params"""

        dasd.lsdasd()
        self.assertEqual(
                [mock.call(['lsdasd', '--long', '--offline'], capture=True)],
                self.m_subp.call_args_list)

    def test_with_bus_id(self):
        """lsdasd appends bus_id param when passed"""

        bus_id = random_bus_id()
        dasd.lsdasd(bus_id=bus_id)
        self.assertEqual(
                [mock.call(
                    ['lsdasd', '--long', '--offline', bus_id], capture=True)],
                self.m_subp.call_args_list)

    def test_with_offline_false(self):
        """lsdasd does not have --offline if param is false"""

        dasd.lsdasd(offline=False)
        self.assertEqual([mock.call(['lsdasd', '--long'], capture=True)],
                         self.m_subp.call_args_list)

    def test_returns_stdout(self):
        """lsdasd returns stdout from command output"""

        stdout = self.random_string()
        self.m_subp.return_value = (stdout, None)
        output = dasd.lsdasd()
        self.assertEqual(stdout, output)
        self.assertEqual(self.m_subp.call_count, 1)

    def test_ignores_stderr(self):
        """lsdasd does not include stderr in return value"""

        stderr = self.random_string()
        self.m_subp.return_value = (None, stderr)
        output = dasd.lsdasd()
        self.assertNotEqual(stderr, output)
        self.assertEqual(self.m_subp.call_count, 1)
