from . import VMBaseClass
from .releases import base_vm_classes as relbase

import json
import textwrap


class TestJournaldReporter(VMBaseClass):
    # Test that curtin with no config does the right thing
    conf_file = "examples/tests/journald_reporter.yaml"
    extra_disks = []
    extra_nics = []
    collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        sfdisk --list > sfdisk_list
        for d in /dev/[sv]d[a-z] /dev/xvd?; do
            [ -b "$d" ] || continue
            echo == $d ==
            sgdisk --print $d
        done > sgdisk_list
        blkid > blkid
        cat /proc/partitions > proc_partitions
        cp /etc/network/interfaces interfaces
        if [ -f /var/log/cloud-init-output.log ]; then
           cp /var/log/cloud-init-output.log .
        fi
        cp /var/log/cloud-init.log .
        find /etc/network/interfaces.d > find_interfacesd
        """)]

    def test_output_files_exist(self):
        self.output_files_exist(["sfdisk_list", "blkid",
                                 "proc_partitions", "interfaces",
                                 "root/journalctl.curtin_events.log",
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


class ArtfulTestJournaldReporter(relbase.artful, TestJournaldReporter):
    __test__ = True
