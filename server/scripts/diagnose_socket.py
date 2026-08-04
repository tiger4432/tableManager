"""Read-only socket/startup diagnosis. Starts nothing, stops nothing, writes nothing.

WHY THIS EXISTS. "The socket does not work" has at least five distinct causes in this
stack and they need opposite repairs: a second launcher holding the ports, a backend that
is up while the WS route is not, a corporate proxy refusing the HTTP Upgrade, a client
bundle whose assets 404, and a browser that is simply waiting out its own reconnect
backoff. Asking an operator to run five commands and read five outputs mid-incident is how
the wrong one gets fixed.

EVERY CHECK USES A RAW SOCKET, DELIBERATELY. This environment has a corporate proxy that
`127.0.0.1` does not bypass, and the one-line "fix" for that (setting NO_PROXY) has already
caused an incident here by making urllib ignore the proxy registry wholesale. Raw sockets
never consult proxy settings at all, so this script cannot be fooled by them and cannot
change them.

Run:  python server/scripts/diagnose_socket.py
"""
import json
import os
import re
import socket
import subprocess
import sys

API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8080"))
GRAPH_PORT = int(os.environ.get("GRAPH_SYNC_PORT", "8090"))
TIMEOUT = 5.0

# A healthy stack is 6 python processes (measured 2026-08-04).
HEALTHY_PYTHON_COUNT = 6

findings = []          # (severity, message) - severity in {"BAD", "WARN", "OK"}


def say(sev, msg):
    findings.append((sev, msg))
    print(f"  [{sev}] {msg}")


def http(method, path, extra_headers="", close=True):
    """One request over a raw socket. Returns (status_line, headers, body_prefix).

    `close=False` for the upgrade probe. Sending `Connection: close` alongside
    `Connection: Upgrade` is not a harmless extra header -- the server reads the
    connection token, decides this is not an upgrade, and routes the request to a
    plain-HTTP handler that has no /ws route. It answers 404, and the probe then
    reports "there is no WS route" about a server whose WS route is fine. Caught by
    running this script against a stack already known to upgrade correctly.
    """
    with socket.create_connection((API_HOST, API_PORT), TIMEOUT) as s:
        s.settimeout(TIMEOUT)
        req = (f"{method} {path} HTTP/1.1\r\nHost: {API_HOST}:{API_PORT}\r\n"
               f"{extra_headers}"
               f"{'Connection: close' + chr(13) + chr(10) if close else ''}\r\n")
        s.sendall(req.encode())
        buf = b""
        try:
            while len(buf) < 65536:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass            # an upgraded connection stays open; what we have is enough
    head, _, body = buf.partition(b"\r\n\r\n")
    lines = head.decode("latin-1", "replace").split("\r\n")
    return (lines[0] if lines else ""), lines[1:], body[:4000]


def port_holders(port):
    """PIDs listening on `port`, via netstat. Empty list means nothing is listening."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             timeout=20).stdout
    except Exception as e:
        say("WARN", f"netstat could not be run ({e}); port ownership is UNKNOWN, not clear")
        return None
    pids = set()
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    return sorted(pids)


def python_processes():
    """[(pid, commandline)] for every python process. None if it could not be read."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\""
          " | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if not out:
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [(d.get("ProcessId"), d.get("CommandLine") or "") for d in data]
    except Exception as e:
        say("WARN", f"process list unavailable ({e}); launcher count is UNKNOWN")
        return None


print("=" * 72)
print("SOCKET DIAGNOSIS (read-only)")
print("=" * 72)

# 1. Who holds the ports -----------------------------------------------------
print(f"\n1. PORTS {API_PORT} / {GRAPH_PORT}")
for port in (API_PORT, GRAPH_PORT):
    pids = port_holders(port)
    if pids is None:
        continue
    if not pids:
        say("BAD", f"port {port}: NOBODY is listening - the backend is not up on this port")
    elif len(pids) == 1:
        say("OK", f"port {port}: held by PID {pids[0]}")
    else:
        say("BAD", f"port {port}: {len(pids)} listeners {pids} - more than one stack")

# 2. How many launchers ------------------------------------------------------
print("\n2. PROCESSES")
procs = python_processes()
if procs is not None:
    launchers = [(p, c) for p, c in procs if "run_decoupled_app" in c]
    print(f"  python processes: {len(procs)} (healthy stack is {HEALTHY_PYTHON_COUNT})")
    if len(launchers) > 1:
        say("BAD", f"{len(launchers)} launchers are running - this is the duplicate-launcher "
                   f"failure: the second cannot bind and retries every 60s forever")
        for p, c in launchers:
            print(f"      PID {p}: {c[:150]}")
    elif len(launchers) == 1:
        say("OK", f"one launcher, PID {launchers[0][0]}")
        print(f"      {launchers[0][1][:150]}")
    else:
        say("WARN", "no launcher process found - the stack may have been started another way")

# 3. Is the API answering ----------------------------------------------------
print("\n3. HTTP")
try:
    status, _, body = http("GET", "/health")
    print(f"  GET /health -> {status}")
    is_ours = b'"checks"' in body and b'"status"' in body
    if status.startswith("HTTP/1.1 200") and is_ours:
        say("OK", "the API is up and the body is OUR health payload")
    elif is_ours:
        say("WARN", f"our app answered but not with 200 ({status.strip()}) - it is up and unhealthy")
    else:
        say("BAD", "something answered that is NOT this app (no status+checks body) - "
                   "a proxy or another server is in front of this port")
        print(f"      body starts: {body[:200]!r}")
except Exception as e:
    say("BAD", f"no HTTP answer on {API_HOST}:{API_PORT} ({e}) - the backend is not reachable")

# 4. Does the WS route actually upgrade --------------------------------------
print("\n4. WEBSOCKET")
try:
    status, headers, _ = http(
        "GET", "/ws",
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n",
        close=False)
    print(f"  GET /ws (upgrade) -> {status}")
    if "101" in status:
        say("OK", "the server DOES upgrade to WebSocket - the server side is not the problem")
    elif "403" in status or "502" in status or "407" in status:
        say("BAD", "the upgrade was REFUSED - characteristic of a proxy blocking WebSocket "
                   "while plain HTTP still works")
    elif "404" in status:
        say("BAD", "no /ws route on this server - the process answering is not the app you think")
    else:
        say("BAD", f"the upgrade did not complete: {status.strip()}")
        for h in headers[:6]:
            print(f"      {h}")
except Exception as e:
    say("BAD", f"the WS handshake could not be attempted ({e})")

# 5. Is the served bundle self-consistent ------------------------------------
print("\n5. CLIENT BUNDLE")
for page in ("/index.html", "/map_editor.html"):
    try:
        status, _, body = http("GET", page)
        if not status.startswith("HTTP/1.1 200"):
            say("WARN", f"{page} -> {status.strip()}")
            continue
        refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', body.decode("utf-8", "replace"))
        missing = []
        for ref in refs:
            st, _, _ = http("GET", ref)
            if not st.startswith("HTTP/1.1 200"):
                missing.append((ref, st.strip()))
        if missing:
            say("BAD", f"{page}: {len(missing)} of {len(refs)} assets do not load - the page's "
                       f"JS never runs, so it never opens a socket")
            for ref, st in missing:
                print(f"      {ref} -> {st}")
        else:
            say("OK", f"{page}: all {len(refs)} assets load")
    except Exception as e:
        say("WARN", f"{page} could not be checked ({e})")

# Verdict --------------------------------------------------------------------
print("\n" + "=" * 72)
bad = [m for s, m in findings if s == "BAD"]
if bad:
    print(f"VERDICT: {len(bad)} problem(s) found. Fix the FIRST one and re-run - they cascade.\n")
    for i, m in enumerate(bad, 1):
        print(f"  {i}. {m}")
else:
    print("VERDICT: server, WS route and bundle all check out from THIS machine.\n")
    print("  So the failure is between the browser and here. Most likely, in order:")
    print("   - the browser is waiting out its own reconnect backoff (up to 30s after the")
    print("     server returns). A hard reload (Ctrl+Shift+R) settles this immediately.")
    print("   - a proxy on the BROWSER's path, not this one. This script bypasses proxies by")
    print("     using raw sockets, so it cannot see that. Check the browser's Network tab")
    print("     for the /ws request and read its status code.")
    print("   - the browser holds a cached page referencing assets a newer build deleted.")
print("=" * 72)
sys.exit(1 if bad else 0)
