"""The notice page while the server is off (owner 11-14 «이런거 업데이트중이면 안내 페이지를 띄워야겠음», 안 1).

`maintenance.bat` runs this after the launcher is stopped; it is closed before the launcher starts again. On the API's
own host and port (`process_supervisor.api_bind`, the launcher's one reading), every path answers 503 with Retry-After
and one page - /health too, so anything polling it reads «down». Standard library only: no database, no app.
usage: python server/runtime/maintenance_page.py [operator note ...]
"""
import html
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # server/, run as a file
from runtime import process_supervisor  # noqa: E402

STATUS = 503
#: seconds a client is told to wait before asking again
RETRY_AFTER = "300"
BUSY = "Port %s is in use (%s) - stop the launcher first, then run maintenance.bat again"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Updating</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f6f8;color:#1f2430;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
main{padding:24px 16px;text-align:center}
h1{margin:0 0 8px;font-size:32px;font-weight:600}
p{margin:4px 0;font-size:18px}
.note{color:#4a5263}
@media (prefers-color-scheme:dark){body{background:#16181d;color:#e6e8ee}.note{color:#a9b0bf}}
</style></head>
<body><main><h1>Updating</h1><p>Back soon</p>%s</main></body></html>
"""


def page(note: str = "") -> bytes:
    """The one page; an operator's note, escaped, under «Back soon»."""
    return (PAGE % ('<p class="note">%s</p>' % html.escape(note) if note else "")).encode("utf-8")


def handler_for(body: bytes):
    class Notice(BaseHTTPRequestHandler):
        def _answer(self, with_body=True):
            self.send_response(STATUS)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Retry-After", RETRY_AFTER)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if with_body:
                self.wfile.write(body)

        def do_HEAD(self):
            self._answer(with_body=False)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _answer

        def log_message(self, *_args):
            pass

    return Notice


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False                             # a held port fails the bind - it is never shared

    def __init__(self, family, address, handler):
        self.address_family = family
        super().__init__(address, handler)

    def server_bind(self):
        if self.address_family == socket.AF_INET6:          # one socket per family, as the API opens them
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def _say(line):
    print(line, flush=True)                                 # the window may be a pipe; a kill must not lose it


def serve(note: str = "", say=_say) -> int:
    """Serve the page until stopped. -> 1 when the port is held (nothing served)."""
    host, port = process_supervisor.api_bind()
    taken = process_supervisor.preflight_port_check([int(port)], host=host)
    if taken:
        say(BUSY % (port, taken[0][1]))
        return 1
    handler = handler_for(page(note))
    servers = []
    try:
        for family, address in process_supervisor.bind_targets(host):
            servers.append(_Server(family, (address, int(port)), handler))
    except OSError as e:
        for server in servers:
            server.server_close()
        say(BUSY % (port, e))
        return 1
    say("Notice page on port %s - close this window before starting the launcher" % port)
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(serve(" ".join(sys.argv[1:]).strip()))
