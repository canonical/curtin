# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Reporter Abstract Base Class."""

## TODO - make python3 compliant
# str = None 

from abc import (
    ABCMeta,
    abstractmethod,
    abstractproperty,
    )
from curtin.util import (
    import_module,
    try_import_module,
    )
from email.utils import parsedate
import json
import mimetypes
import oauth.oauth as oauth
import os.path
import random
import socket
import string
import sys
import time
import urllib2
import uuid
import yaml


class BaseReporter:
    """Skeleton for a report."""

    __metaclass__ = ABCMeta

    @abstractmethod
    def report_progress(self, progress):
        """Report installation progress."""

    @abstractmethod
    def report_success(self):
        """Report installation success."""

    @abstractmethod
    def report_failure(self, failure):
        """Report installation failure."""


class EmptyReporter(BaseReporter):

    def report_progress(self, progress):
        """Empty."""

    def report_success(self, progress):
        """Empty."""

    def report_failure(self, progress):
        """Empty."""


def warn(msg):
    sys.stderr.write(msg + "\n")


def fail(msg):
    sys.stderr.write("FAIL: %s" % msg)


def oauth_headers(url, consumer_key, token_key, token_secret, consumer_secret,
                  clockskew=0):
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


def authenticate_headers(url, headers, creds, clockskew):
    """Update and sign a dict of request headers."""
    if creds.get('consumer_key', None) is not None:
        headers.update(oauth_headers(
            url,
            consumer_key=creds['consumer_key'],
            token_key=creds['token_key'],
            token_secret=creds['token_secret'],
            consumer_secret=creds['consumer_secret'],
            clockskew=clockskew))


def geturl(url, creds, headers=None, data=None):
    # Takes a dict of creds to be passed through to oauth_headers,
    #   so it should have consumer_key, token_key, ...
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)

    clockskew = 0

    exc = Exception("Unexpected Error")
    for naptime in (1, 1, 2, 4, 8, 16, 32):
        authenticate_headers(url, headers, creds, clockskew)
        try:
            req = urllib2.Request(url=url, data=data, headers=headers)
            return urllib2.urlopen(req).read()
        except urllib2.HTTPError as exc:
            if 'date' not in exc.headers:
                warn("date field not in %d headers" % exc.code)
                pass
            elif exc.code in (401, 403):
                date = exc.headers['date']
                try:
                    ret_time = time.mktime(parsedate(date))
                    clockskew = int(ret_time - time.time())
                    warn("updated clock skew to %d" % clockskew)
                except:
                    warn("failed to convert date '%s'" % date)
        except Exception as exc:
            pass

        warn("request to %s failed. sleeping %d.: %s" % (url, naptime, exc))
        time.sleep(naptime)

    raise exc


def _encode_field(field_name, data, boundary):
    return (
        '--' + boundary,
        'Content-Disposition: form-data; name="%s"' % field_name,
        '', str(data),
        )


def _encode_file(name, fileObj, boundary):
    return (
        '--' + boundary,
        'Content-Disposition: form-data; name="%s"; filename="%s"'
        % (name, name),
        'Content-Type: %s' % _get_content_type(name),
        '',
        fileObj.read(),
        )


def _random_string(length):
    return ''.join(random.choice(string.letters) for ii in range(length + 1))


def _get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def encode_multipart_data(data, files):
    """Create a MIME multipart payload from L{data} and L{files}.

    @param data: A mapping of names (ASCII strings) to data (byte string).
    @param files: A mapping of names (ASCII strings) to file objects ready to
        be read.
    @return: A 2-tuple of C{(body, headers)}, where C{body} is a a byte string
        and C{headers} is a dict of headers to add to the enclosing request in
        which this payload will travel.
    """
    boundary = _random_string(30)

    lines = []
    for name in data:
        lines.extend(_encode_field(name, data[name], boundary))
    for name in files:
        lines.extend(_encode_file(name, files[name], boundary))
    lines.extend(('--%s--' % boundary, ''))
    body = '\r\n'.join(lines)

    headers = {
        'content-type': 'multipart/form-data; boundary=' + boundary,
        'content-length': "%d" % len(body),
    }

    return body, headers


def load_reporter(config):
    """Loads and returns reporter intance stored in config file."""
    
    reporter = config.get('reporter')
    if reporter is None:
        return EmptyReporter()
    name, options = reporter.popitem()
    module = try_import_module('curtin.reporter.%s' % name)
    if module is None:
        return EmptyReporter()
    try:
        return module.load_factory(options)
    except Exception as e:
        return EmptyReporter()


def report(url, consumer_key, consumer_secret, token_key, token_secret,
           files, status, message=None):
    """Send the report."""

    creds = {
        'consumer_key': consumer_key,
        'token_key': token_key,
        'token_secret': token_secret,
        'consumer_secret': consumer_secret,
        }

    params = {}
    params['status'] = status
    if message is not None:
        params['error'] = message

    install_files = {}
    for fpath in files:
        install_files[os.path.basename(fpath)] = open(fpath, "r")

    data, headers = encode_multipart_data(params, install_files)

    exc = None
    msg = ""

    try:
        payload = geturl(url, creds=creds, headers=headers, data=data)
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
