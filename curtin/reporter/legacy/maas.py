from curtin import url_helper

from . import (BaseReporter, LoadReporterException)

import mimetypes
import os.path
import random
import string
import sys


class MAASReporter(BaseReporter):

    def __init__(self, config):
        """Load config dictionary and initialize object."""
        self.url = config['url']
        self.urlhelper = url_helper.OauthUrlHelper(
            consumer_key=config.get('consumer_key'),
            token_key=config.get('token_key'),
            token_secret=config.get('token_secret'),
            consumer_secret='',
            skew_data_file="/run/oauth_skew.json")
        self.files = []
        self.retries = config.get('retries', [1, 1, 2, 4, 8, 16, 32])

    def report_success(self):
        """Report installation success."""
        status = "OK"
        message = "Installation succeeded."
        self.report(status, message, files=self.files)

    def report_failure(self, message):
        """Report installation failure."""
        status = "FAILED"
        self.report(status, message, files=self.files)

    def encode_multipart_data(self, data, files):
        """Create a MIME multipart payload from L{data} and L{files}.

        @param data: A mapping of names (ASCII strings) to data (byte string).
        @param files: A mapping of names (ASCII strings) to file objects ready
            to be read.
        @return: A 2-tuple of C{(body, headers)}, where C{body} is a a byte
            string and C{headers} is a dict of headers to add to the enclosing
            request in which this payload will travel.
        """
        boundary = self._random_string(30)

        lines = []
        for name in data:
            lines.extend(self._encode_field(name, data[name], boundary))
        for name in files:
            lines.extend(self._encode_file(name, files[name], boundary))
        lines.extend(('--%s--' % boundary, ''))
        body = '\r\n'.join(lines)

        headers = {
            'content-type': 'multipart/form-data; boundary=' + boundary,
            'content-length': "%d" % len(body),
        }
        return body, headers

    def report(self, status, message=None, files=None):
        """Send the report."""

        params = {}
        params['status'] = status
        if message is not None:
            params['error'] = message

        if files is None:
            files = []
        install_files = {}
        for fpath in files:
            install_files[os.path.basename(fpath)] = open(fpath, "r")

        data, headers = self.encode_multipart_data(params, install_files)

        exc = None
        msg = ""

        if not isinstance(data, bytes):
            data = data.encode()

        try:
            payload = self.urlhelper.geturl(
                self.url, data=data, headers=headers,
                retries=self.retries)
            if payload != b'OK':
                raise TypeError("Unexpected result from call: %s" % payload)
            else:
                msg = "Success"
        except url_helper.UrlError as exc:
            msg = str(exc)
        except Exception as exc:
            raise exc
            msg = "unexpected error [%s]" % exc

        sys.stderr.write("%s\n" % msg)

    def _encode_field(self, field_name, data, boundary):
        return (
            '--' + boundary,
            'Content-Disposition: form-data; name="%s"' % field_name,
            '', str(data),
            )

    def _encode_file(self, name, fileObj, boundary):
        return (
            '--' + boundary,
            'Content-Disposition: form-data; name="%s"; filename="%s"'
            % (name, name),
            'Content-Type: %s' % self._get_content_type(name),
            '',
            fileObj.read(),
            )

    def _random_string(self, length):
        return ''.join(random.choice(string.ascii_letters)
                       for ii in range(length + 1))

    def _get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def load_factory(options):
    try:
        return MAASReporter(options)
    except Exception:
        raise LoadReporterException
