# This file is part of curtin. See LICENSE file for copyright and license info.

from pathlib import Path

from .helpers import CiTestCase
from curtin.commands import collect_logs


class TestRedactSensitiveInformation(CiTestCase):

    def setUp(self):
        super().setUp()
        self.tmpd = Path(self.tmp_dir())

    def _write_file(self, name, content):
        fpath = self.tmpd / name
        fpath.write_text(content)
        return fpath

    def test_redact_simple_value(self):
        secret = "my-secret-token"
        fpath = self._write_file("log.txt", f"token: {secret}")
        collect_logs._redact_sensitive_information(str(self.tmpd), [secret])
        self.assertEqual("token: <REDACTED>", fpath.read_text())

    def test_redact_dot_treated_as_literal(self):
        secret = "my.secret"
        fpath = self._write_file(
            "log.txt",
            "my.secret: 1\nmyXsecret: 2",
        )
        collect_logs._redact_sensitive_information(str(self.tmpd), [secret])
        self.assertEqual(
            "<REDACTED>: 1\nmyXsecret: 2",
            fpath.read_text(),
        )

    def test_redact_invalid_regex_does_not_raise(self):
        secret = "foo[bar"
        fpath = self._write_file("log.txt", "value: foo[bar")
        collect_logs._redact_sensitive_information(str(self.tmpd), [secret])
        self.assertEqual("value: <REDACTED>", fpath.read_text())

    def test_redact_multiple_values(self):
        secrets = ["token-1", "token-2"]
        fpath = self._write_file(
            "log.txt",
            "first: token-1\nsecond: token-2",
        )
        collect_logs._redact_sensitive_information(str(self.tmpd), secrets)
        self.assertEqual(
            "first: <REDACTED>\nsecond: <REDACTED>",
            fpath.read_text(),
        )

    def test_redact_value_not_present(self):
        secret = "missing-token"
        content = "nothing to see here"
        fpath = self._write_file("log.txt", content)
        collect_logs._redact_sensitive_information(str(self.tmpd), [secret])
        self.assertEqual(content, fpath.read_text())
