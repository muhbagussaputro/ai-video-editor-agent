#!/usr/bin/env python3
"""Minimal local CONNECT proxy for the clipper's YouTube requests.

It is bound only to the Docker bridge gateway. The proxy container uses host
networking, so outbound requests inherit the host's already-active WARP route.
This avoids changing host default routes or Tailscale policy routing.
"""
from __future__ import annotations

import selectors
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BIND_HOST = "172.26.0.1"
BIND_PORT = 18888
BUFFER_SIZE = 64 * 1024


def _connect(host: str, port: int) -> socket.socket:
    errors: list[OSError] = []
    for family, socktype, proto, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        upstream = socket.socket(family, socktype, proto)
        upstream.settimeout(20)
        try:
            upstream.connect(address)
            upstream.settimeout(None)
            return upstream
        except OSError as exc:
            errors.append(exc)
            upstream.close()
    raise errors[-1] if errors else OSError("unable to resolve upstream")


def _relay(left: socket.socket, right: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    try:
        while True:
            for key, _ in selector.select(timeout=60):
                source: socket.socket = key.fileobj
                target: socket.socket = key.data
                data = source.recv(BUFFER_SIZE)
                if not data:
                    return
                target.sendall(data)
    finally:
        selector.close()


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.client_address[0]} {format % args}", flush=True)

    def do_CONNECT(self) -> None:
        host, separator, port_raw = self.path.rpartition(":")
        if not separator or not port_raw.isdigit():
            self.send_error(400, "CONNECT target must be host:port")
            return
        try:
            upstream = _connect(host, int(port_raw))
        except OSError as exc:
            self.send_error(502, f"upstream connect failed: {exc}")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        try:
            _relay(self.connection, upstream)
        finally:
            upstream.close()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if not parsed.scheme or not parsed.hostname:
            self.send_error(400, "absolute proxy URL required")
            return
        try:
            upstream = _connect(parsed.hostname, parsed.port or 80)
            path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
            upstream.sendall(f"{self.command} {path} {self.request_version}\r\n".encode())
            for name, value in self.headers.items():
                if name.lower() not in {"proxy-connection", "connection", "host"}:
                    upstream.sendall(f"{name}: {value}\r\n".encode())
            upstream.sendall(f"Host: {parsed.netloc}\r\nConnection: close\r\n\r\n".encode())
            _relay(upstream, self.connection)
        except OSError as exc:
            self.send_error(502, f"upstream request failed: {exc}")
        finally:
            try:
                upstream.close()
            except UnboundLocalError:
                pass


if __name__ == "__main__":
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), ProxyHandler)
    print(f"WARP proxy listening on http://{BIND_HOST}:{BIND_PORT}", flush=True)
    server.serve_forever()
