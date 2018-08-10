# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import textwrap


class TestJournaldReporter(VMBaseClass):
    # Test that curtin with no config does the right thing
    conf_file = "examples/tests/journald_reporter.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = VMBaseClass.collect_scripts + [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["root/journalctl.curtin_events.log",
                                 "root/journalctl.curtin_events.json"])

    def test_journal_reporter_events(self):
        events = json.loads(
            self.load_collect_file("root/journalctl.curtin_events.json"))
        self.assertGreater(len(events), 0)
        e1 = events[0]
        for key in ['CURTIN_EVENT_TYPE', 'CURTIN_MESSAGE', 'CURTIN_NAME',
                    'PRIORITY', 'SYSLOG_IDENTIFIER']:
            self.assertIn(key, e1)


class XenialTestJournaldReporter(relbase.xenial, TestJournaldReporter):
    __test__ = True


class BionicTestJournaldReporter(relbase.bionic, TestJournaldReporter):
    __test__ = True


class CosmicTestJournaldReporter(relbase.cosmic, TestJournaldReporter):
    __test__ = True

# vi: ts=4 expandtab syntax=python
