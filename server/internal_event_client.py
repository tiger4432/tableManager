"""The one way a process on this box talks to the web server on this box.

Why this module exists
----------------------
On 2026-07-30 the production chain worker took repeated **403** on
``POST /internal/events/broadcast``. The gate cannot produce that answer to a
request with no header - it answers 401 - and ``/health``, which has no gate at
all, was refusing too. Nothing of ours was answering.

``requests`` defaults ``trust_env=True``, so a bare ``requests.Session()`` reads
``HTTP_PROXY`` / ``http_proxy`` and, on Windows, the WinINET proxy registry. The
trap that makes that reach a loopback address: the ``ProxyOverride`` value's
``<local>`` token exempts only hostnames **with no dot**, so ``localhost`` is
bypassed and **``127.0.0.1`` is not**. A notification addressed to this same
machine therefore left the box for the corporate proxy, which refused to relay to
a private address. ``curl.exe --noproxy "*"`` against the same URL returned 200
the whole time.

Everything about the incident follows from that: 403 instead of 401, every path
including ungated ones, immune to restarts, and invisible on a development
machine that has no corporate proxy.

The rule this module enforces
-----------------------------
**An internal call between two processes on one machine must never consult proxy
configuration.** That is not a preference; a proxy in the path of worker-to-server
IPC can only break it.

The rule is enforced by construction rather than by comment:
:func:`internal_event_session` is the only supported way to obtain an HTTP client
for these calls, and ``server/tests/test_admin_auth.py`` asserts that no sender
builds its own. The same defect has now been fixed sender-by-sender three times on
this one endpoint (the agent lesson file records the previous two), so a rule that
a fourth sender has to remember is not good enough.
"""
import os
import threading

#: The web server's address, in ONE place. Three modules previously repeated this
#: literal, so a deployment that moved the port had three edits to find and
#: nothing derived it from whatever actually chose the port.
DEFAULT_API_BASE_URL = "http://127.0.0.1:8080"

#: Hosts that are this machine. Used only to decide how loudly to talk about an
#: internal call that is about to leave the box.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0")

_http_local = threading.local()


def api_base_url():
    """Where ``/internal/events/*`` lives, from the environment or the default.

    Read at call time, not captured at import, so a test or an isolated stack can
    redirect it without reimporting the senders.
    """
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)


def internal_event_session():
    """A ``requests.Session`` for worker-to-web-server calls, per calling thread.

    Two properties, and both are load-bearing:

    ``trust_env = False``
        No proxy environment variables, no Windows proxy registry. This is the
        fix for the 2026-07-30 incident described above. Chosen over a per-request
        ``proxies={'http': None, 'https': None}`` for two reasons: it also covers
        the Windows registry path that a request-level override reaches only by
        way of a ``setdefault`` implementation detail, and it is a property of the
        object, so a new call site inherits it instead of having to remember it.
        The other things ``trust_env`` governs are all inapplicable here - there
        is no TLS on a loopback call, so ``REQUESTS_CA_BUNDLE`` is moot, and
        authentication is an explicit ``X-Admin-Token`` header, not ``.netrc``.

    thread-local
        ``requests.Session`` is not thread-safe (its cookie jar and connection
        pool mutate), and ``run_watcher`` calls in from both the observer thread
        and the retry poller. One session per thread keeps the keep-alive win -
        the reason the chain worker grew a session in the first place - without
        sharing mutable state across threads.
    """
    sess = getattr(_http_local, "session", None)
    if sess is None:
        import requests
        sess = requests.Session()
        # See the docstring. Do not "simplify" this away: without it, an
        # internal notification to 127.0.0.1 can be relayed to a corporate
        # proxy, which answers 403 and looks exactly like an auth failure.
        sess.trust_env = False
        _http_local.session = sess
    return sess


def _redact_proxy(url):
    """A proxy URL with any ``user:password@`` removed.

    Proxy environment variables routinely carry credentials, and this string goes
    into a log file. The host is the diagnostic value; the credentials are
    somebody's password.
    """
    text = str(url)
    if "@" not in text:
        return text
    scheme, sep, rest = text.partition("://")
    if not sep:
        scheme, rest = "", text
    host = rest.split("@", 1)[1]
    return f"{scheme}{sep}<redacted>@{host}" if sep else f"<redacted>@{host}"


def proxy_environment_summary():
    """What proxy configuration this process can see, as a short log-safe string.

    No network call. This is the fact that made the incident invisible: nothing in
    any log said a proxy existed, so nobody thought to suspect one. Now every
    daemon says it at startup, whether or not anything is wrong.
    """
    try:
        import urllib.request
        proxies = urllib.request.getproxies() or {}
    except Exception as e:  # pragma: no cover - defensive
        return f"unknown ({e})"
    if not proxies:
        return "none"
    parts = [f"{scheme}={_redact_proxy(url)}" for scheme, url in sorted(proxies.items())
             if scheme.lower() in ("http", "https", "all")]
    if not parts:
        return "none"
    return "; ".join(parts)


def is_loopback(url):
    """True when this URL addresses the machine we are running on."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(str(url)).hostname or "").lower()
    except Exception:
        return False
    return host in _LOOPBACK_HOSTS


def check_api_reachable(base_url=None, timeout=3.0):
    """Probe ``GET /health`` once, and say what the answer means.

    Returns ``(level, message)`` for the caller to log. Never raises: this runs on
    a daemon's startup path and a diagnostic that can kill a worker is worse than
    no diagnostic.

    ``/health`` is deliberately the probe target because it carries **no admin
    gate**. That makes the three outcomes mean three different things, which is
    exactly the discrimination that took three hours of investigation to make by
    hand:

    * **200** - the web server is up and answering us directly.
    * **connection refused / timeout** - nothing is listening yet. Expected during
      boot; the launcher starts the API and this worker within seconds of each
      other and uvicorn takes longer to bind than a worker takes to reach here.
      Logged at INFO for that reason - a warning on every normal startup is a
      warning nobody reads.
    * **any HTTP status** - something answered, and since ``/health`` is ungated it
      was **not this application**. That is the incident: a proxy or filtering
      layer in the path of a loopback call. Logged at ERROR with the remedy.
    """
    base = base_url or api_base_url()
    url = f"{base.rstrip('/')}/health"
    proxy_env = proxy_environment_summary()
    try:
        res = internal_event_session().get(url, timeout=timeout)
    except Exception as e:
        return "info", (
            f"[internal-events] {url} not reachable yet ({type(e).__name__}) - "
            "normal during startup, the launcher brings the API up alongside this "
            f"process. proxy-env={proxy_env}"
        )

    if res.status_code == 200:
        return "info", (
            f"[internal-events] {url} -> 200, direct (proxy bypassed). "
            f"proxy-env={proxy_env}"
        )

    server_header = ""
    try:
        seen = res.headers.get("Server") or res.headers.get("Via")
        if seen:
            server_header = f" answered by '{seen}';"
    except Exception:
        pass
    return "error", (
        f"[internal-events] {url} -> {res.status_code}.{server_header} /health "
        "carries NO admin gate, so a status like this cannot come from this "
        "application - something in front of it answered. Internal notifications "
        f"will fail the same way. proxy-env={proxy_env}. 이 세션은 이미 "
        "trust_env=False 라 프록시 환경변수를 보지 않습니다. 따라서 이것은 "
        "환경변수 문제가 아니라 포트 앞단(리버스 프록시/필터)의 문제입니다. "
        "확인: 그 포트를 소유한 프로세스, 그리고 위 'answered by' 값. "
        "[금지] NO_PROXY 를 설정하지 마세요 - 프로세스 전역이라 인제션 스크립트까지 "
        "물려받고, no_proxy 하나만 있어도 urllib 이 프록시 레지스트리를 통째로 "
        "무시합니다(2026-07-30 실제로 오토업데이트가 이렇게 멈췄습니다)."
    )
    # NOTE: keep every character in this module's log lines encodable in cp949.
    # The production console is a Korean Windows console (run_app.bat sets no
    # PYTHONIOENCODING), and an em dash - U+2014, which cp949 does NOT have,
    # unlike the visually identical U+2015 - makes the logging handler raise and
    # DROP the line. Losing this particular line means losing the one sentence
    # that names the proxy during a proxy incident. Guarded by
    # test_admin_auth.py::TestOperatorFacingLinesSurviveTheProductionConsole.


def startup_lines(process_label, base_url=None):
    """Every line a daemon should log about its internal-event path, in order.

    Returns a list of ``(level, message)``. Bundled into one function so the three
    daemons cannot drift into logging different subsets of the same diagnosis.
    """
    import admin_auth

    base = base_url or api_base_url()
    lines = [admin_auth.worker_token_banner(f"{process_label} -> {base}")]

    if not is_loopback(base):
        # Not a refusal. A notification that fails costs a delayed grid refresh
        # (the undelivered-broadcast sweep recovers it); a worker that refuses to
        # start costs ingestion, which is the thing this system exists to do. The
        # admin gate makes the same trade in the same direction - fail closed only
        # where the harm is code execution - so this warns and serves.
        lines.append(("warning", (
            f"[internal-events] API_BASE_URL={base} is not this machine. Internal "
            "events are sent with proxy configuration disabled by design, so an "
            "off-box address must be directly routable. Confirm this is intended."
        )))

    lines.append(check_api_reachable(base))
    return lines
