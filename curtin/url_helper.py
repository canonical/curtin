from email.utils import parsedate
import json
import os
import socket
import time
import uuid
from functools import partial

try:
    from urllib import request as urllib_request
    from urllib import error as urllib_error
    from urllib.parse import urlparse
except ImportError:
    # python2
    import urllib2 as urllib_request
    import urllib2 as urllib_error
    from urlparse import urlparse

from .log import LOG

error = urllib_error


class _ReRaisedException(Exception):
    """this exists only as an exception type that was re-raised by
    an exception_cb, so code can know to handle it specially"""
    def __init__(self, exc):
        self.exc = exc


def _geturl(url, headers=None, headers_cb=None, exception_cb=None, data=None):
    def_headers = {'User-Agent': 'Curtin/0.1'}

    if headers is not None:
        def_headers.update(headers)

    headers = def_headers

    if headers_cb:
        headers.update(headers_cb(url))

    if data and isinstance(data, dict):
        data = json.dumps(data).encode()

    try:
        req = urllib_request.Request(url=url, data=data, headers=headers)
        r = urllib_request.urlopen(req).read()
        # python2, we want to return bytes, which is what python3 does
        if isinstance(r, str):
            return r.decode()
        return r
    except urllib_error.HTTPError as exc:
        myexc = UrlError(exc, code=exc.code, headers=exc.headers, url=url,
                         reason=exc.reason)
    except Exception as exc:
        myexc = UrlError(exc, code=None, headers=None, url=url,
                         reason="unknown")

    if exception_cb:
        try:
            exception_cb(myexc)
        except Exception as e:
            myexc = _ReRaisedException(e)

    raise myexc


def geturl(url, headers=None, headers_cb=None, exception_cb=None,
           data=None, retries=None, log=LOG.warn):
    """return the content of the url in binary_type. (py3: bytes, py2: str)"""
    if retries is None:
        retries = []

    curexc = None
    for trynum, naptime in enumerate(retries):
        try:
            return _geturl(url=url, headers=headers, headers_cb=headers_cb,
                           exception_cb=exception_cb, data=data)
        except Exception as e:
            curexc = e
            if isinstance(curexc, _ReRaisedException):
                raise curexc.exc
        if log:
            msg = ("try %d of request to %s failed. sleeping %d: %s" %
                   (naptime, url, naptime, curexc))
            log(msg)
        time.sleep(naptime)
    try:
        return _geturl(url=url, headers=headers, headers_cb=headers_cb,
                       exception_cb=exception_cb, data=data)
    except _ReRaisedException as e:
        raise e.exc


class UrlError(IOError):
    def __init__(self, cause, code=None, headers=None, url=None, reason=None):
        IOError.__init__(self, str(cause))
        self.cause = cause
        self.code = code
        self.headers = headers
        if self.headers is None:
            self.headers = {}
        self.url = url
        self.reason = reason

    def __str__(self):
        if isinstance(self.cause, urllib_error.HTTPError):
            msg = "http error: %s" % self.cause.code
        elif isinstance(self.cause, urllib_error.URLError):
            msg = "url error: %s" % self.cause.reason
        elif isinstance(self.cause, socket.timeout):
            msg = "socket timeout: %s" % self.cause
        else:
            msg = "Unknown Exception: %s" % self.cause
        return "[%s] " % self.url + msg


class OauthUrlHelper(object):
    def __init__(self, consumer_key=None, token_key=None,
                 token_secret=None, consumer_secret=None,
                 skew_data_file="/run/oauth_skew.json"):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret or ""
        self.token_key = token_key
        self.token_secret = token_secret
        self.skew_data_file = skew_data_file
        self._do_oauth = True
        self.skew_change_limit = 5
        required = (self.token_key, self.token_secret, self.consumer_key)
        if not any(required):
            self._do_oauth = False
        elif not all(required):
            raise ValueError("all or none of token_key, token_secret, or "
                             "consumer_key can be set")

        old = self.read_skew_file()
        self.skew_data = old or {}

    def __str__(self):
        fields = ['consumer_key', 'consumer_secret',
                  'token_key', 'token_secret']
        masked = fields

        def r(name):
            if not hasattr(self, name):
                rval = "_unset"
            else:
                val = getattr(self, name)
                if val is None:
                    rval = "None"
                elif name in masked:
                    rval = '"%s"' % ("*" * len(val))
                else:
                    rval = '"%s"' % val
            return '%s=%s' % (name, rval)

        return ("OauthUrlHelper(" + ','.join([r(f) for f in fields]) + ")")

    def read_skew_file(self):
        if self.skew_data_file and os.path.isfile(self.skew_data_file):
            with open(self.skew_data_file, mode="r") as fp:
                return json.load(fp.read())
        return None

    def update_skew_file(self, host, value):
        # this is not atomic
        if not self.skew_data_file:
            return
        cur = self.read_skew_file()
        cur[host] = value
        with open(self.skew_data_file, mode="w") as fp:
            fp.write(json.dumps(cur))

    def exception_cb(self, exception):
        if not (isinstance(exception, UrlError) and
                (exception.code == 403 or exception.code == 401)):
            return

        if 'date' not in exception.headers:
            LOG.warn("Missing header 'date' in %s response", exception.code)
            return

        date = exception.headers['date']
        try:
            remote_time = time.mktime(parsedate(date))
        except Exception as e:
            LOG.warn("Failed to convert datetime '%s': %s", date, e)
            return

        skew = int(remote_time - time.time())
        host = urlparse(exception.url).netloc
        old_skew = self.skew_data.get(host, 0)
        if abs(old_skew - skew) > self.skew_change_limit:
            self.update_skew_file(host, skew)
            LOG.warn("Setting oauth clockskew for %s to %d", host, skew)
        self.skew_data[host] = skew

        return

    def headers_cb(self, url):
        if not self._do_oauth:
            return {}

        host = urlparse(url).netloc
        clockskew = None
        if self.skew_data and host in self.skew_data:
            clockskew = self.skew_data[host]

        return oauth_headers(
            url=url, consumer_key=self.consumer_key,
            token_key=self.token_key, token_secret=self.token_secret,
            consumer_secret=self.consumer_secret, clockskew=clockskew)

    def _wrapped(self, wrapped_func, args, kwargs):
        kwargs['headers_cb'] = partial(
            self._headers_cb, kwargs.get('headers_cb'))
        kwargs['exception_cb'] = partial(
            self._exception_cb, kwargs.get('exception_cb'))
        return wrapped_func(*args, **kwargs)

    def geturl(self, *args, **kwargs):
        return self._wrapped(geturl, args, kwargs)

    def _exception_cb(self, extra_exception_cb, exception):
        ret = None
        try:
            if extra_exception_cb:
                ret = extra_exception_cb(exception)
        finally:
                self.exception_cb(exception)
        return ret

    def _headers_cb(self, extra_headers_cb, url):
        headers = {}
        if extra_headers_cb:
            headers = extra_headers_cb(url)
        headers.update(self.headers_cb(url))
        return headers


try:
    import oauth.oauth as oauth

    def oauth_headers(url, consumer_key, token_key, token_secret,
                      consumer_secret, clockskew=0):
        """Build OAuth headers using given credentials."""
        consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
        token = oauth.OAuthToken(token_key, token_secret)

        if clockskew is None:
            clockskew = 0
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

except ImportError:
    import oauthlib.oauth1 as oauth1

    def oauth_headers(url, consumer_key, token_key, token_secret,
                      consumer_secret, clockskew=0):
        """Build OAuth headers using given credentials."""
        if clockskew is None:
            clockskew = 0
        timestamp = int(time.time()) + clockskew
        client = oauth1.Client(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=token_key,
            resource_owner_secret=token_secret,
            signature_method=oauth1.SIGNATURE_PLAINTEXT,
            timestamp=str(timestamp))
        uri, signed_headers, body = client.sign(url)
        return signed_headers


# vi: ts=4 expandtab syntax=python
