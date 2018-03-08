# This file is part of curtin. See LICENSE file for copyright and license info.

from email.utils import parsedate
import json
import os
import socket
import sys
import time
import uuid
from functools import partial

from curtin import version

try:
    from urllib import request as _u_re  # pylint: disable=no-name-in-module
    from urllib import error as _u_e     # pylint: disable=no-name-in-module
    from urllib.parse import urlparse    # pylint: disable=no-name-in-module
    urllib_request = _u_re
    urllib_error = _u_e
except ImportError:
    # python2
    import urllib2 as urllib_request
    import urllib2 as urllib_error
    from urlparse import urlparse  # pylint: disable=import-error

from .log import LOG

error = urllib_error

DEFAULT_HEADERS = {'User-Agent': 'Curtin/' + version.version_string()}


class _ReRaisedException(Exception):
    exc = None
    """this exists only as an exception type that was re-raised by
    an exception_cb, so code can know to handle it specially"""
    def __init__(self, exc):
        self.exc = exc


class UrlReader(object):
    fp = None

    def __init__(self, url, headers=None, data=None):
        headers = _get_headers(headers)
        self.url = url
        try:
            req = urllib_request.Request(url=url, data=data, headers=headers)
            self.fp = urllib_request.urlopen(req)
        except urllib_error.HTTPError as exc:
            raise UrlError(exc, code=exc.code, headers=exc.headers, url=url,
                           reason=exc.reason)
        except Exception as exc:
            raise UrlError(exc, code=None, headers=None, url=url,
                           reason="unknown")

        self.info = self.fp.info()
        self.size = self.info.get('content-length', -1)

    def read(self, buflen):
        try:
            return self.fp.read(buflen)
        except urllib_error.HTTPError as exc:
            raise UrlError(exc, code=exc.code, headers=exc.headers,
                           url=self.url, reason=exc.reason)
        except Exception as exc:
            raise UrlError(exc, code=None, headers=None, url=self.url,
                           reason="unknown")

    def close(self):
        if not self.fp:
            return
        try:
            self.fp.close()
        finally:
            self.fp = None

    def __enter__(self):
        return self

    def __exit__(self, etype, value, trace):
        self.close()


def download(url, path, reporthook=None, data=None):
    """Download url to path.

    reporthook is compatible with py3 urllib.request.urlretrieve.
    urlretrieve does not exist in py2."""

    buflen = 8192
    wfp = open(path, "wb")

    try:
        buf = None
        blocknum = 0
        fsize = 0
        start = time.time()
        with UrlReader(url) as rfp:
            if reporthook:
                reporthook(blocknum, buflen, rfp.size)

            while True:
                buf = rfp.read(buflen)
                if not buf:
                    break
                blocknum += 1
                if reporthook:
                    reporthook(blocknum, buflen, rfp.size)
                wfp.write(buf)
                fsize += len(buf)
        timedelta = time.time() - start
        LOG.debug("Downloaded %d bytes from %s to %s in %.2fs (%.2fMbps)",
                  fsize, url, path, timedelta, fsize / timedelta / 1024 / 1024)
        return path, rfp.info
    finally:
        wfp.close()


def get_maas_version(endpoint):
    """ Attempt to return the MAAS version via api calls to the specified
        endpoint.

        MAAS endpoint url looks like this:

        http://10.245.168.2/MAAS/metadata/status/node-f0462064-20f6-11e5-990a-d4bed9a84493

        We need the MAAS_URL, which is http://10.245.168.2

        Returns a maas version dictionary:
        {'subversion': '16.04.1',
         'capabilities': ['networks-management', 'static-ipaddresses',
                          'ipv6-deployment-ubuntu', 'devices-management',
                          'storage-deployment-ubuntu',
                          'network-deployment-ubuntu',
                          'bridging-interface-ubuntu',
                          'bridging-automatic-ubuntu'],
         'version': '2.1.5+bzr5596-0ubuntu1'
        }
    """
    # https://docs.ubuntu.com/maas/devel/en/api indicates that
    # we leave 1.0 in here for maas 1.9 endpoints
    MAAS_API_SUPPORTED_VERSIONS = ["1.0", "2.0"]

    try:
        parsed = urlparse(endpoint)
    except AttributeError as e:
        LOG.warn('Failed to parse endpoint URL: %s', e)
        return None

    maas_host = "%s://%s" % (parsed.scheme, parsed.netloc)
    maas_api_version_url = "%s/MAAS/api/version/" % (maas_host)

    try:
        result = geturl(maas_api_version_url)
    except UrlError as e:
        LOG.warn('Failed to query MAAS API version URL: %s', e)
        return None

    api_version = result.decode('utf-8')
    if api_version not in MAAS_API_SUPPORTED_VERSIONS:
        LOG.warn('Endpoint "%s" API version "%s" not in MAAS supported'
                 'versions: "%s"', endpoint, api_version,
                 MAAS_API_SUPPORTED_VERSIONS)
        return None

    maas_version_url = "%s/MAAS/api/%s/version/" % (maas_host, api_version)
    maas_version = None
    try:
        result = geturl(maas_version_url)
        maas_version = json.loads(result.decode('utf-8'))
    except UrlError as e:
        LOG.warn('Failed to query MAAS version via URL: %s', e)
    except (ValueError, TypeError):
        LOG.warn('Failed to load MAAS version result: %s', result)

    return maas_version


def _get_headers(headers=None):
    allheaders = DEFAULT_HEADERS.copy()
    if headers is not None:
        allheaders.update(headers)
    return allheaders


def _geturl(url, headers=None, headers_cb=None, exception_cb=None, data=None):

    headers = _get_headers(headers)
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
        except _ReRaisedException as e:
            raise curexc.exc
        except Exception as e:
            curexc = e
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
                return json.load(fp)
        return None

    def update_skew_file(self, host, value):
        # this is not atomic
        if not self.skew_data_file:
            return
        cur = self.read_skew_file()
        if cur is None:
            cur = {}
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


def _oauth_headers_none(url, consumer_key, token_key, token_secret,
                        consumer_secret, clockskew=0):
    """oauth_headers implementation when no oauth is available"""
    if not any([token_key, token_secret, consumer_key]):
        return {}
    pkg = "'python3-oauthlib'"
    if sys.version_info[0] == 2:
        pkg = "'python-oauthlib' or 'python-oauth'"
    raise ValueError(
        "Oauth was necessary but no oauth library is available. "
        "Please install package " + pkg + ".")


def _oauth_headers_oauth(url, consumer_key, token_key, token_secret,
                         consumer_secret, clockskew=0):
    """Build OAuth headers with oauth using given credentials."""
    consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
    token = oauth.OAuthToken(token_key, token_secret)

    if clockskew is None:
        clockskew = 0
    timestamp = int(time.time()) + clockskew

    params = {
        'oauth_version': "1.0",
        'oauth_nonce': uuid.uuid4().hex,
        'oauth_timestamp': timestamp,
        'oauth_token': token.key,
        'oauth_consumer_key': consumer.key,
    }
    req = oauth.OAuthRequest(http_url=url, parameters=params)
    req.sign_request(
        oauth.OAuthSignatureMethod_PLAINTEXT(), consumer, token)
    return(req.to_header())


def _oauth_headers_oauthlib(url, consumer_key, token_key, token_secret,
                            consumer_secret, clockskew=0):
    """Build OAuth headers with oauthlib using given credentials."""
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


oauth_headers = _oauth_headers_none
try:
    # prefer to use oauthlib. (python-oauthlib)
    import oauthlib.oauth1 as oauth1
    oauth_headers = _oauth_headers_oauthlib
except ImportError:
    # no oauthlib was present, try using oauth (python-oauth)
    try:
        import oauth.oauth as oauth
        oauth_headers = _oauth_headers_oauth
    except ImportError:
        # we have no oauth libraries available, use oauth_headers_none
        pass

# vi: ts=4 expandtab syntax=python
