#!/usr/bin/python3
# This file is part of curtin. See LICENSE file for copyright and license info.

import socket
try:
    # python2
    import SimpleHTTPServer as http_server
    import SocketServer as socketserver
except ImportError:
    import http.server as http_server
    import socketserver

import json
import os
import sys
import threading

EXAMPLE_CONFIG = """\
# example config
reporting:
  mypost:
    type: webhook
    endpoint: %(endpoint)s
install:
  log_file: /tmp/foo
  post_files: [/tmp/foo]

# example python:
from curtin.reporter import events, update_configuration
cfg = {'mypost': {'type': 'webhook', 'endpoint': '%(endpoint)s'}}
update_configuration(cfg)
with events.ReportEventStack(name="myname", description="mydesc",
                             reporting_enabled=True):
    print("do something")
"""

CURTIN_EVENTS = []
DEFAULT_PORT = 8000
addr = ""


def render_event_string(event_str):
    return json.dumps(json.loads(event_str), indent=1)


def write_event_string(target, event_str):
    data = []
    if os.path.exists(target):
        with open(target, 'r') as fp:
            data = json.load(fp)
    data.append(json.loads(event_str))
    with open(target, 'w') as fp:
        json.dump(data, fp)


class HTTPServerV6(socketserver.TCPServer):
    address_family = socket.AF_INET6


class ServerHandler(http_server.SimpleHTTPRequestHandler):
    address_family = socket.AF_INET6
    result_log_file = None

    def log_request(self, code, size=None):
        if self.result_log_file:
            return
        lines = [
            "== %s %s ==" % (self.command, self.path),
            str(self.headers).replace('\r', '')]
        if self._message:
            lines.append(self._message)
        sys.stdout.write('\n'.join(lines) + '\n')
        sys.stdout.flush()

    def do_GET(self):
        self._message = None
        self.send_response(200)
        self.end_headers()
        self.wfile.write("content of %s\n" % self.path)

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(length).decode('utf-8')
        try:
            if self.result_log_file:
                write_event_string(self.result_log_file, post_data)
            self._message = render_event_string(post_data)
        except Exception as e:
            self._message = '\n'.join(
                ["failed printing event: %s" % e, post_data])

        msg = "received post to %s" % self.path
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))


def GenServerHandlerWithResultFile(file_path):
    class ExtendedServerHandler(ServerHandler):
        result_log_file = file_path
    return ExtendedServerHandler


def get_httpd(port=None, result_file=None):
    # avoid 'Address already in use' after ctrl-c
    socketserver.TCPServer.allow_reuse_address = True

    # get first available port if none specified
    if port is None:
        port = 0

    if result_file:
        Handler = GenServerHandlerWithResultFile(result_file)
    else:
        Handler = ServerHandler
    httpd = HTTPServerV6(("::", port), Handler)
    httpd.allow_reuse_address = True

    return httpd


def run_server(port=DEFAULT_PORT, log_data=True):
    """Run the server and capture output, redirecting output to /dev/null if
       log_data = False"""
    httpd = get_httpd(port=port)

    _stdout = sys.stdout
    with open(os.devnull, 'w') as fp:
        try:
            if not log_data:
                sys.stdout = fp
            httpd.serve_forever()
        except KeyboardInterrupt:
            sys.stdout.flush()
            pass
        finally:
            sys.stdout = _stdout
            httpd.server_close()

    return CURTIN_EVENTS


class CaptureReporting:

    def __init__(self, result_file):
        self.result_file = result_file
        self.httpd = get_httpd(result_file=self.result_file,
                               port=None)
        self.httpd.server_activate()
        # socket.AF_INET6 returns
        # (host, port, flowinfo, scopeid)
        (self.bind_addr, self.port, _, _) = self.httpd.server_address

    def __enter__(self):
        if os.path.exists(self.result_file):
            os.remove(self.result_file)
        self.worker = threading.Thread(target=self.httpd.serve_forever)
        self.worker.start()
        return self

    def __exit__(self, etype, value, trace):
        self.httpd.shutdown()


def mainloop():
    addr = port = None
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
        addr = sys.argv[1]
    elif len(sys.argv) > 1:
        port = int(sys.argv[1])
        addr = ""
    else:
        port = DEFAULT_PORT
    info = {
        'interface': addr or "::",
        'port': port,
        'endpoint': "http://" + (addr or "[::1]") + ":%s" % port
    }
    print("Serving at: %(endpoint)s" % info)
    print("Post to this with:\n%s\n" % (EXAMPLE_CONFIG % info))
    run_server(port=port, log_data=True)
    sys.exit(0)


if __name__ == "__main__":
    mainloop()

# vi: ts=4 expandtab syntax=python
