# This file is part of curtin. See LICENSE file for copyright and license info.

import threading
import socketserver
from http.server import SimpleHTTPRequestHandler
from tests.vmtests.image_sync import IMAGE_DIR


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


class ImageHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=IMAGE_DIR, **kwargs)


class ImageServer:
    def __init__(self, host="localhost", port=0):
        self.bind_host = host
        self.bind_port = port
        self.server = None
        self._running = False

    def start(self, *args, **kwds):
        if self._running:
            return

        self.server = ThreadedTCPServer(
            (self.bind_host, self.bind_port), ImageHTTPRequestHandler
        )

        server_thread = threading.Thread(target=self.server.serve_forever)

        # exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()
        self._running = True

    def stop(self):
        if not self._running:
            return
        if self.server:
            self.server.shutdown()
        self._running = False

    @property
    def base_url(self):
        (ip, port) = (self.bind_host, self.bind_port)
        if self.server is not None:
            ip, port = self.server.server_address

        return f"http://{ip}:{port}"
