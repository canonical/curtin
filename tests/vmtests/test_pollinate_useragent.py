# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass
from .releases import base_vm_classes as relbase

import re
import textwrap
from unittest import SkipTest


class TestPollinateUserAgent(VMBaseClass):
    # Test configuring pollinate useragent
    conf_file = "examples/tests/pollinate-useragent.yaml"
    test_type = 'config'
    extra_disks = []
    extra_nics = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cp -a /etc/pollinate etc_pollinate
        pollinate --print-user-agent > pollinate_print_user_agent

        exit 0
        """)]

    def test_pollinate_user_agent(self):
        self.output_files_exist(["pollinate_print_user_agent"])
        agent_values = self.load_collect_file("pollinate_print_user_agent")
        if len(agent_values) == 0:
            pollver = re.search(r'pollinate\s(?P<version>\S+)',
                                self.load_collect_file("debian-packages.txt"))
            msg = ("pollinate client '%s' does not support "
                   "--print-user-agent'" % pollver.groupdict()['version'])
            raise SkipTest(msg)

        # curtin version is always present
        curtin_ua = "curtin/%s #from curtin" % self.get_curtin_version()
        ua_values = self.load_collect_file("etc_pollinate/add-user-agent")
        for line in ua_values.splitlines() + [curtin_ua]:
            """Each line is:
               key/value # comment goes here

               or

               key/value

               So we break at the first space
            """
            ua_val = line.split()[0]
            # escape + and . that are likely in maas/curtin version strings
            regex = '%s' % ua_val.replace('+', r'\+').replace('.', r'\.')
            hit = re.search(regex, agent_values)
            self.assertIsNotNone(hit)
            self.assertEqual(ua_val, hit.group())


class XenialTestPollinateUserAgent(relbase.xenial, TestPollinateUserAgent):
    __test__ = True


class BionicTestPollinateUserAgent(relbase.bionic, TestPollinateUserAgent):
    __test__ = True


class DiscoTestPollinateUserAgent(relbase.disco, TestPollinateUserAgent):
    __test__ = True


class EoanTestPollinateUserAgent(relbase.eoan, TestPollinateUserAgent):
    __test__ = True


class FocalTestPollinateUserAgent(relbase.focal, TestPollinateUserAgent):
    __test__ = True


# vi: ts=4 expandtab syntax=python
