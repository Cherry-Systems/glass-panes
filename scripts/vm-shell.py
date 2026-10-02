#!/usr/bin/env python3
"""Run shell commands inside a test VM's desktop session, over QEMU's user network.

  vm-shell.py serve                 start the host side (port 18765)
  vm-shell.py run 'CMD' [TIMEOUT]   run CMD in the VM and print its output

Inside the VM, type once into a terminal (scripts/qmp.py type ...):
  curl -s 10.0.2.2:18765/agent | bash &
The VM can also download any file of this repository from http://10.0.2.2:18765/files/PATH.
"""
import http.server
import os
import queue
import sys
import threading
import urllib.request

PORT = 18765
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

AGENT = """while :; do
  c=$(curl -s -m 25 http://10.0.2.2:%d/cmd) || { sleep 2; continue; }
  [ -n "$c" ] || continue
  bash -c "$c" 2>&1 | head -c 400000 | curl -s --data-binary @- http://10.0.2.2:%d/out
done
""" % (PORT, PORT)

commands: "queue.Queue[str]" = queue.Queue()
results: "queue.Queue[bytes]" = queue.Queue()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body: bytes, code=200):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        if self.path == "/agent":
            self.reply(AGENT.encode())
        elif self.path == "/cmd":
            try:
                self.reply(commands.get(timeout=20).encode())
            except queue.Empty:
                self.reply(b"")
        elif self.path.startswith("/files/"):
            path = os.path.realpath(os.path.join(ROOT, self.path[len("/files/"):]))
            if not path.startswith(ROOT + os.sep) or not os.path.isfile(path):
                self.reply(b"not found\n", 404)
            else:
                with open(path, "rb") as f:
                    self.reply(f.read())
        else:
            self.reply(b"", 404)

    def do_POST(self):
        if self.path == "/out":
            results.put(self.body())
            self.reply(b"")
        elif self.path.startswith("/run"):
            while not results.empty():
                results.get_nowait()
            commands.put(self.body().decode())
            timeout = float(self.headers.get("X-Timeout", 60))
            try:
                self.reply(results.get(timeout=timeout))
            except queue.Empty:
                self.reply(b"(timed out waiting for the VM)\n", 504)
        else:
            self.reply(b"", 404)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "serve":
        # QEMU's user network forwards the guest's 10.0.2.2 to the host's loopback.
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        server.serve_forever()
    elif sys.argv[1] == "run":
        timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 60
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/run", data=sys.argv[2].encode(),
                                     headers={"X-Timeout": str(timeout)})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as r:
                sys.stdout.buffer.write(r.read())
        except urllib.error.HTTPError as e:
            sys.stdout.buffer.write(e.read())
            sys.exit(1)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    threading.current_thread().name = "vm-shell"
    main()
