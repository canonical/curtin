#   Copyright (C) 2014 Canonical Ltd.
#
#   Author: Newell Jensen <newell.jensen@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

"""MAAS Reporter."""

from curtin.reporter import (
    BaseReporter,
    INSTALL_LOG,
    LoadReporterException,
    )
from email.utils import parsedate
import mimetypes
import oauth.oauth as oauth
import os.path
import random
import socket
import string
import sys
import time
import uuid
import urllib2


class MAASReporter(BaseReporter):

    def __init__(self, config):
        """Load config dictionary and initialize object."""
        self.url = config['url']
        self.consumer_key = config['consumer_key']
        self.consumer_secret = ''
        self.token_key = config['token_key']
        self.token_secret = config['token_secret']

    def report_progress(self, progress, files):
        """Report installation progress."""
        status = "WORKING"
        message = "Installation in progress %s" % progress
        self.report(files, status, message)

    def report_success(self):
        """Report installation success."""
        status = "OK"
        message = "Installation succeeded."
        self.report([INSTALL_LOG], status, message)

    def report_failure(self, message):
        """Report installation failure."""
        status = "FAILED"
        self.report([INSTALL_LOG], status, message)

    def oauth_headers(self, url, consumer_key, token_key, token_secret,
                      consumer_secret, clockskew=0):
        """Build OAuth headers using given credentials."""
        consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
        token = oauth.OAuthToken(token_key, token_secret)

        timestamp = int(time.time()) + clockskew

        params = {
            'oauth_version': "1.0",
            'oauth_nonce': uuid.uuid4().get_hex(),
            'oauth_timestamp': timestamp,
            'oauth_token': token.key,
            'oauth_consumer_key': consumer.key,
        }
        req = oauth.OAuthRequest(http_url=url, parameters=params)
        req.sign_request(
            oauth.OAuthSignatureMethod_PLAINTEXT(), consumer, token)
        return(req.to_header())

    def authenticate_headers(self, url, headers, creds, clockskew):
        """Update and sign a dict of request headers."""
        if creds.get('consumer_key', None) is not None:
            headers.update(self.oauth_headers(
                url,
                consumer_key=creds['consumer_key'],
                token_key=creds['token_key'],
                token_secret=creds['token_secret'],
                consumer_secret=creds['consumer_secret'],
                clockskew=clockskew))

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

    def geturl(self, url, creds, headers=None, data=None):
        """Create MAAS url for sending the report."""
        if headers is None:
            headers = {}
        else:
            headers = dict(headers)

        clockskew = 0

        exc = Exception("Unexpected Error")
        for naptime in (1, 1, 2, 4, 8, 16, 32):
            self.authenticate_headers(url, headers, creds, clockskew)
            try:
                req = urllib2.Request(url=url, data=data, headers=headers)
                return urllib2.urlopen(req).read()
            except urllib2.HTTPError as exc:
                if 'date' not in exc.headers:
                    sys.stderr.write("date field not in %d headers" % exc.code)
                    pass
                elif exc.code in (401, 403):
                    date = exc.headers['date']
                    try:
                        ret_time = time.mktime(parsedate(date))
                        clockskew = int(ret_time - time.time())
                        sys.stderr.write("updated clock skew to %d" %
                                         clockskew)
                    except:
                        sys.stderr.write("failed to convert date '%s'" % date)
            except Exception as exc:
                pass

            sys.stderr.write(
                "request to %s failed. sleeping %d.: %s" % (url, naptime, exc))
            time.sleep(naptime)

        raise exc

    def report(self, files, status, message=None):
        """Send the report."""

        creds = {
            'consumer_key': self.consumer_key,
            'token_key': self.token_key,
            'token_secret': self.token_secret,
            'consumer_secret': self.consumer_secret,
            }

        params = {}
        params['status'] = status
        if message is not None:
            params['error'] = message

        install_files = {}
        for fpath in files:
            install_files[os.path.basename(fpath)] = open(fpath, "r")

        data, headers = self.encode_multipart_data(params, install_files)

        exc = None
        msg = ""

        try:
            payload = self.geturl(self.url, creds=creds, headers=headers,
                                  data=data)
            if payload != "OK":
                raise TypeError("Unexpected result from call: %s" % payload)
            else:
                msg = "Success"
        except urllib2.HTTPError as exc:
            msg = "http error [%s]" % exc.code
        except urllib2.URLError as exc:
            msg = "url error [%s]" % exc.reason
        except socket.timeout as exc:
            msg = "socket timeout [%s]" % exc
        except TypeError as exc:
            msg = exc.message
        except Exception as exc:
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
        return ''.join(random.choice(string.letters)
                       for ii in range(length + 1))

    def _get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def load_factory(options):
    try:
        return MAASReporter(options)
    except Exception:
        raise LoadReporterException
