"""MergeJudge egress proxy - the agent's only way out of the sandbox.

The sandbox profile denies all network except 127.0.0.1:<port>, where this
proxy listens. It tunnels HTTPS CONNECT requests to allowlisted hosts only
(the model API) and refuses everything else, recording what it refused.
Plain-HTTP proxy requests are always refused.

Standalone, for probing the sandbox by hand:
  python3 src/egress_proxy.py        # prints the port, serves until Ctrl-C
"""

import select
import socket
import socketserver
import threading

ALLOWED = {("api.anthropic.com", 443)}


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            head += chunk
        method, target = (head.split(b"\r\n", 1)[0].decode("latin-1")
                          .split(" ") + ["", ""])[:2]
        host, _, port = target.rpartition(":")
        if method != "CONNECT" or (host, int(port or 0)) not in ALLOWED:
            self.server.refused.append(f"{method} {target}")
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return
        try:
            upstream = socket.create_connection((host, int(port)), timeout=30)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        with upstream:
            socks = [self.request, upstream]
            while True:
                readable, _, _ = select.select(socks, [], [], 300)
                if not readable:
                    return
                for s in readable:
                    data = s.recv(65536)
                    if not data:
                        return
                    (upstream if s is self.request else self.request).sendall(data)


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start():
    """Start the proxy on an ephemeral localhost port; return the server.

    server.server_address[1] is the port; server.refused lists refused
    requests; call server.shutdown() when the run is over.
    """
    server = _Server(("127.0.0.1", 0), _Handler)
    server.refused = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = start()
    print(srv.server_address[1], flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("refused:", srv.refused)
