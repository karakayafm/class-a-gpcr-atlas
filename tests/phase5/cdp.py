"""Minimal Chrome DevTools Protocol client: stdlib only.

Implements just enough of RFC 6455 to send and receive text frames over the DevTools socket —
handshake, masked client frames, unmasked server frames, close. No third-party dependency.
"""
from __future__ import annotations
import base64, json, os, socket, struct, urllib.request

class WS:
    def __init__(self, url: str, timeout: float = 30.0):
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
               f"Sec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = self.sock.recv(4096)
            if not c: raise RuntimeError("handshake closed")
            buf += c
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("handshake failed: " + buf.split(b"\r\n",1)[0].decode())
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def _recv_exact(self, n):
        while len(self.buf) < n:
            c = self.sock.recv(65536)
            if not c: raise RuntimeError("socket closed")
            self.buf += c
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text: str):
        payload = text.encode()
        mask = os.urandom(4)
        n = len(payload)
        hdr = b"\x81"
        if n < 126: hdr += bytes([0x80 | n])
        elif n < 65536: hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else: hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(hdr + mask + masked)

    def recv(self) -> str:
        while True:
            b0, b1 = self._recv_exact(2)
            op = b0 & 0x0F
            n = b1 & 0x7F
            if n == 126: n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._recv_exact(8))[0]
            if b1 & 0x80: mask = self._recv_exact(4)
            else: mask = None
            data = self._recv_exact(n)
            if mask: data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8: raise RuntimeError("closed by peer")
            if op == 9:  # ping -> pong
                self.sock.sendall(b"\x8a" + bytes([0x80 | len(data)]) + os.urandom(4) + data)
                continue
            if op in (1, 2): return data.decode("utf-8", "replace")

    def close(self):
        try: self.sock.sendall(b"\x88\x80" + os.urandom(4))
        except Exception: pass
        try: self.sock.close()
        except Exception: pass


class Chrome:
    def __init__(self, port: int):
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=20).read())
        page = next(t for t in tabs if t.get("type") == "page")
        self.ws = WS(page["webSocketDebuggerUrl"])
        self.id = 0
        self.logs = []

    def call(self, method, params=None, timeout_msgs=400):
        self.id += 1
        mid = self.id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        for _ in range(timeout_msgs):
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.consoleAPICalled":
                self.logs.append(msg["params"])
                continue
            if msg.get("method") == "Runtime.exceptionThrown":
                self.logs.append({"type": "exception", "params": msg["params"]})
                continue
            if msg.get("id") == mid:
                if "error" in msg: raise RuntimeError(method + ": " + json.dumps(msg["error"]))
                return msg.get("result", {})
        raise RuntimeError("no reply for " + method)

    def eval(self, expr, await_promise=True):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": await_promise})
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:400])
        return res.get("value")

    def goto(self, url):
        self.call("Page.navigate", {"url": url})

    def close(self): self.ws.close()
