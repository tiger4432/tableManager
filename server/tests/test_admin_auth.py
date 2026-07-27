# -*- coding: utf-8 -*-
"""Guards for the shared-token gate on /admin/*.

Access control that is wrong is *silently* wrong: the surface looks locked and
is not. The load-bearing test here is
:meth:`TestEveryAdminRouteIsCovered.test_every_admin_route_carries_a_gate`,
which enumerates the routes FastAPI actually registered rather than a list
someone maintains by hand. An admin route added six months from now fails this
suite instead of shipping unprotected.

It asserts a **set**, never a count. A count is satisfied by any change that
swaps one member for another - a doc in this repo claimed a marker set was "14
before and after" while the membership had silently changed underneath. The
assertions below compare sets of ``(method, path)`` so a swap is as loud as a
removal.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import admin_auth
from main import app

TOKEN = "correct-horse-battery-staple"
HEADER = admin_auth.ADMIN_TOKEN_HEADER
ENV = admin_auth.ADMIN_TOKEN_ENV


# --------------------------------------------------------------------------
# Route inventory helpers
# --------------------------------------------------------------------------

#: Admin paths that must stay reachable without a token, with the reason.
#: These serve the admin *page* itself: the browser navigates to them, so it
#: cannot attach a header, and the HTML is what then asks the operator for the
#: token. They carry no data - every byte the page displays arrives through the
#: gated JSON routes below.
#:
#: Registered only when a client2 build is present (main.py guards them with
#: `if os.path.exists(client2_dist_path)`), so this is the set of *permitted*
#: exemptions, not a set that must be fully present.
PUBLIC_ADMIN_PATHS = {"/admin", "/admin.html"}

#: Prefixes whose routes must all be gated. `/internal` is worker->server IPC:
#: POST /internal/events/broadcast relays an arbitrary dict to every connected
#: WebSocket client and injects into audit_cache, so leaving it open while
#: gating read-only admin routes was backwards.
GATED_PREFIXES = ("/admin", "/internal")

#: Routes that reach code execution and are therefore never open: they refuse
#: with 503 when no token is configured, rather than falling back to open.
STRICT_ADMIN_ROUTES = {
    ("POST", "/admin/scripts/code"),          # writes an arbitrary Python file
    ("POST", "/admin/auto-update/run-now"),   # makes the scheduler run it
}


def _dependency_calls(route):
    """Every dependency callable FastAPI resolved for this route.

    Walks the resolved ``Dependant`` tree rather than reading the decorator's
    ``dependencies=`` list, so the gate is detected however a future route
    attaches it - route-level dependency, router-level dependency, or a
    ``Depends()`` default on a parameter.
    """
    found = set()

    def walk(dependant):
        if dependant.call is not None:
            found.add(dependant.call)
        for sub in dependant.dependencies:
            walk(sub)

    walk(route.dependant)
    return found


def admin_routes():
    """(method, path, route) for every registered route under a gated prefix.

    Uses ``app.routes`` - the router's own inventory - so nothing can be
    enumerated here that is not actually served, and nothing served can be
    omitted.

    KNOWN LIMIT, do not read this as more than it is: ``methods`` is ``None`` on
    WebSocket routes and on mounts, so both are skipped here. An ungated
    ``@app.websocket("/admin/live-console")`` would NOT fail this test. The gap
    is tracked separately; until it closes, every claim made about this test
    must say "HTTP routes".
    """
    out = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if not any(path == p or path.startswith(p) for p in GATED_PREFIXES):
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append((method, path, route))
    return out


class TestEveryAdminRouteIsCovered:
    """The durable guard. Everything else in this file is a spot check."""

    def test_every_admin_route_carries_a_gate(self):
        """Red the moment an unprotected /admin route is registered."""
        ungated = set()
        gated = set()
        exempt = set()

        for method, path, route in admin_routes():
            if path in PUBLIC_ADMIN_PATHS:
                exempt.add((method, path))
                continue
            calls = _dependency_calls(route)
            if calls & set(admin_auth.ADMIN_GATES):
                gated.add((method, path))
            else:
                ungated.add((method, path))

        assert not ungated, (
            "these /admin routes are registered with NO authentication "
            f"dependency: {sorted(ungated)}. Add "
            "`dependencies=[Depends(require_admin_token)]` to the route "
            "decorator, or - if the route can execute code - "
            "`require_admin_token_strict`. If the route genuinely must be "
            "public, add it to PUBLIC_ADMIN_PATHS with the reason."
        )
        # A gate on nothing is not a gate. Guards against the failure mode where
        # a refactor drops the routes and leaves this test passing vacuously.
        assert gated, "no gated /admin routes found - did the app fail to load?"

    def test_the_exempt_set_never_grows_silently(self):
        """Anything exempt must be one of the two page routes, by name.

        Membership, not count: swapping /admin.html for /admin/anything-else
        keeps the size identical and must still fail.
        """
        observed_exempt = {p for _m, p, _r in admin_routes()
                           if p in PUBLIC_ADMIN_PATHS}
        assert observed_exempt <= PUBLIC_ADMIN_PATHS
        # And the exemptions really are GET-only page serving, not an API verb
        # that slipped in under the same path.
        for method, path, _route in admin_routes():
            if path in PUBLIC_ADMIN_PATHS:
                assert method == "GET", (
                    f"{method} {path} is exempt from the admin gate but is not "
                    "a page fetch")

    def test_the_code_execution_routes_are_strict(self):
        """These two must use the fail-closed gate, as a set.

        Downgrading either to the ordinary gate would leave an unconfigured
        server offering remote code execution, which is the exact hole this
        work closed.
        """
        strict_observed = set()
        for method, path, route in admin_routes():
            if admin_auth.require_admin_token_strict in _dependency_calls(route):
                strict_observed.add((method, path))

        assert strict_observed == STRICT_ADMIN_ROUTES, (
            "the set of fail-closed admin routes changed. expected "
            f"{sorted(STRICT_ADMIN_ROUTES)}, found {sorted(strict_observed)}"
        )

    def test_health_is_not_swept_up_by_the_gate(self):
        """/health is the monitoring surface; locking it defeats its purpose."""
        for route in app.routes:
            if getattr(route, "path", None) == "/health":
                assert not (_dependency_calls(route) & set(admin_auth.ADMIN_GATES)), \
                    "/health must stay unauthenticated for external monitors"
                return
        pytest.fail("/health route not found")


# --------------------------------------------------------------------------
# Behaviour: token configured
# --------------------------------------------------------------------------

@pytest.fixture
def token_set(monkeypatch):
    monkeypatch.setenv(ENV, TOKEN)
    return TOKEN


@pytest.fixture
def token_unset(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)


class TestConfiguredTokenIsEnforced:

    # A read and a write, so neither verb can be gated while the other is not.
    GATED = [
        ("get", "/admin/outbox/failed"),
        ("get", "/admin/scripts/list"),
        ("get", "/admin/chain/rules"),
        ("post", "/admin/reload-configs"),
    ]

    @pytest.mark.parametrize("verb,path", GATED)
    def test_missing_header_is_rejected(self, client, token_set, verb, path):
        res = getattr(client, verb)(path)
        assert res.status_code == 401, (
            f"{verb.upper()} {path} answered {res.status_code} with no token")

    @pytest.mark.parametrize("verb,path", GATED)
    def test_wrong_header_is_rejected(self, client, token_set, verb, path):
        res = getattr(client, verb)(path, headers={HEADER: TOKEN + "x"})
        assert res.status_code == 403, (
            f"{verb.upper()} {path} answered {res.status_code} with a bad token")

    @pytest.mark.parametrize("verb,path", GATED)
    def test_right_header_is_accepted(self, client, token_set, verb, path):
        """Not just 'not 401/403' - the handler must actually have run.

        Asserting `< 400` would pass on a 500, i.e. on a gate that lets the
        request through into a broken handler; these routes return JSON bodies.
        """
        res = getattr(client, verb)(path, headers={HEADER: TOKEN})
        assert res.status_code == 200, f"{verb.upper()} {path}: {res.text}"

    def test_empty_header_value_is_rejected(self, client, token_set):
        res = client.get("/admin/chain/rules", headers={HEADER: ""})
        assert res.status_code == 401

    def test_a_prefix_of_the_token_is_rejected(self, client, token_set):
        """compare_digest is a full comparison, not a startswith."""
        res = client.get("/admin/chain/rules", headers={HEADER: TOKEN[:-1]})
        assert res.status_code == 403

    def test_non_ascii_header_does_not_500(self, client, token_set):
        """`secrets.compare_digest` raises TypeError on non-ASCII *str* input.

        An unhandled TypeError here would be a leak, not just a 500: the
        traceback renders the operands, so the presented value - and on some
        formatters the expected one - lands in the log.

        The value must be handed over as **bytes**: httpx refuses to encode a
        non-ASCII ``str`` header and the request would die in the client,
        proving nothing about the server. Starlette decodes these bytes as
        latin-1, which is what puts non-ASCII characters into the ``str`` that
        reaches ``_matches``.

        What injection actually showed (do not overstate this):
        ``_matches`` has two independent protections - encoding both operands
        to bytes, and the ``except`` clause. Removing *either one alone* leaves
        this test green, because the survivor still yields a clean 403. Only
        removing **both** turns it red, with
        ``TypeError: comparing strings with non-ASCII characters is not
        supported`` at admin_auth.py. So this test guards the pair, not each
        half; that redundancy is deliberate, and the price is that it cannot
        tell you which belt was cut.
        """
        # A distinctive value, NOT a real word: the Korean rejection message
        # legitimately contains "토큰" (= "token"), so probing with that word
        # would fail on the static message and prove nothing about leakage.
        probe = "pässwörd-9f3a"
        res = client.get("/admin/chain/rules",
                         headers={HEADER: probe.encode("utf-8")})
        assert res.status_code == 403, res.text
        assert "9f3a" not in res.text
        assert "sswörd" not in res.text

    def test_matches_is_total_on_any_header_string(self):
        """Unit-level statement of the same contract, without the transport."""
        assert admin_auth._matches(TOKEN, TOKEN) is True
        assert admin_auth._matches(TOKEN + "x", TOKEN) is False
        assert admin_auth._matches("", TOKEN) is False
        # latin-1 decoded bytes: the shape Starlette actually delivers.
        assert admin_auth._matches("토큰".encode("utf-8").decode("latin-1"),
                                   TOKEN) is False
        assert admin_auth._matches("\udcff", TOKEN) is False  # lone surrogate

    def test_the_token_is_not_accepted_as_a_query_parameter(self, client, token_set):
        """Query strings land in the uvicorn access log; the header does not.

        If this ever starts passing, the secret is being written to disk on
        every admin request.
        """
        res = client.get(f"/admin/chain/rules?token={TOKEN}")
        assert res.status_code == 401
        res = client.get(f"/admin/chain/rules?{HEADER}={TOKEN}")
        assert res.status_code == 401


# --------------------------------------------------------------------------
# Behaviour: token NOT configured (the split)
# --------------------------------------------------------------------------

class TestUnconfiguredServerFailsClosedOnlyWhereItMatters:
    """The operator's first restart must not black out the admin page, but must
    not leave code execution reachable either."""

    STRICT_CALLS = [
        ("post", "/admin/scripts/code",
         {"path": "ingestion_workspace/x/scripts/a.py", "code": "# x\n"}),
        ("post", "/admin/auto-update/run-now",
         {"table_name": "t", "script_name": "s.py"}),
    ]

    @pytest.mark.parametrize("verb,path,body", STRICT_CALLS)
    def test_code_execution_routes_refuse_with_503(
            self, client, token_unset, verb, path, body):
        res = getattr(client, verb)(path, json=body)
        assert res.status_code == 503, (
            f"{verb.upper()} {path} answered {res.status_code} on an "
            "unconfigured server - remote code execution is reachable")
        # The refusal has to tell the operator how to fix it, or they will hunt.
        assert ENV in res.json()["detail"]

    @pytest.mark.parametrize("verb,path,body", STRICT_CALLS)
    def test_a_guessed_header_does_not_open_them(
            self, client, token_unset, verb, path, body):
        """Unset means unset. No header value can satisfy an unset secret."""
        for guess in ("", "x", "None", "null", "true"):
            res = getattr(client, verb)(path, json=body, headers={HEADER: guess})
            assert res.status_code == 503, f"header {guess!r} got past the gate"

    @pytest.mark.parametrize("verb,path", [
        ("get", "/admin/outbox/failed"),
        ("get", "/admin/scripts/list"),
        ("get", "/admin/chain/rules"),
        ("get", "/admin/auto-update/status"),
        ("post", "/admin/reload-configs"),
    ])
    def test_the_remaining_admin_routes_still_serve(
            self, client, token_unset, verb, path):
        """The user's explicit choice: do not lock the operator out on restart."""
        res = getattr(client, verb)(path)
        assert res.status_code == 200, (
            f"{verb.upper()} {path} broke on an unconfigured server: {res.text}")

    def test_whitespace_only_token_counts_as_unset(self, client, monkeypatch):
        """`export ASSY_ADMIN_TOKEN=` must not create a guessable secret."""
        monkeypatch.setenv(ENV, "   ")
        assert admin_auth.configured_token() is None
        res = client.post("/admin/scripts/code",
                          json={"path": "ingestion_workspace/x/s/a.py", "code": ""})
        assert res.status_code == 503
        # ...and the empty string must not be accepted as the token either.
        res = client.post("/admin/scripts/code", headers={HEADER: "   "},
                          json={"path": "ingestion_workspace/x/s/a.py", "code": ""})
        assert res.status_code == 503


# --------------------------------------------------------------------------
# The token must not leak
# --------------------------------------------------------------------------

class TestTheTokenNeverLeaks:

    def test_the_context_middleware_cannot_pick_it_up(self, client, token_set):
        """`main.py` sets request_user / _transaction_id / _source from headers.

        Those are what land in AuditLog rows. This asserts the admin header is
        not one of the names they read - a rename that collided (say, someone
        renaming X-Admin-Token to X-Source) would write the secret into every
        audit row the request produced.
        """
        import main
        import inspect

        src = inspect.getsource(main.db_context_middleware)
        consumed = ("X-User", "X-Transaction-ID", "X-Source")
        for name in consumed:
            assert name in src, "middleware no longer reads the headers this test tracks"
        assert HEADER not in src, (
            f"{HEADER} is read by the context middleware, so the token would be "
            "written into audit rows / transaction ids")

    @pytest.mark.parametrize("presented,expected_status", [
        (None, 401),
        ("wrong-token-value-9f3a", 403),
    ])
    def test_rejection_bodies_do_not_echo_the_secret(
            self, client, token_set, presented, expected_status):
        headers = {HEADER: presented} if presented is not None else {}
        res = client.get("/admin/chain/rules", headers=headers)
        assert res.status_code == expected_status
        body = res.text
        assert TOKEN not in body, "the configured token appeared in an error body"
        if presented:
            assert presented not in body, "the presented value was echoed back"

    def test_the_503_body_names_the_variable_but_not_a_value(self, client, token_unset):
        res = client.post("/admin/auto-update/run-now",
                          json={"table_name": "t", "script_name": "s"})
        detail = res.json()["detail"]
        assert ENV in detail          # tells the operator what to set
        assert "=" not in detail      # ...without printing a value next to it

    def test_startup_banner_never_prints_the_token(self, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        level, msg = admin_auth.startup_banner()
        assert level == "info"
        assert TOKEN not in msg
        assert ENV in msg

    def test_startup_banner_when_unset_says_what_is_off_and_how_to_fix(
            self, monkeypatch):
        """The operator must not have to discover the requirement by trial."""
        monkeypatch.delenv(ENV, raising=False)
        level, msg = admin_auth.startup_banner()
        assert level == "warning"
        assert ENV in msg                            # which variable
        assert "/admin/scripts/code" in msg          # what stopped working
        assert "/admin/auto-update/run-now" in msg
        assert "DEPLOY_SETUP" in msg                 # where the instructions are


# --------------------------------------------------------------------------
# Suite hygiene
# --------------------------------------------------------------------------

class TestStaticFallbackCannotServeArbitraryFiles:
    """[B1] The SPA catch-all handed out any file the process could read.

    This is the reason the admin GETs are gated at all - `admin_auth` says so in
    its own docstring - so a hole next door made those gates decorative:
    `/../../server/config/table_config.json` and `/../../server/admin_auth.py`
    both returned 200 with no token.

    Driven at the **ASGI layer**. httpx (and therefore TestClient) normalizes
    `..` out of a URL before it is sent, so a TestClient-based test cannot see
    this bug at all - it would have passed against the vulnerable code.
    """

    @staticmethod
    def _raw_get(path):
        import asyncio

        async def go():
            scope = {"type": "http", "asgi": {"version": "3.0"},
                     "http_version": "1.1", "method": "GET", "scheme": "http",
                     "path": path, "raw_path": path.encode(), "query_string": b"",
                     "root_path": "", "headers": [(b"host", b"testserver")],
                     "client": ("192.168.0.77", 5555), "server": ("127.0.0.1", 8080)}
            captured, body = {}, bytearray()

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(msg):
                if msg["type"] == "http.response.start":
                    captured["status"] = msg["status"]
                elif msg["type"] == "http.response.body":
                    body.extend(msg.get("body", b""))

            await app(scope, receive, send)
            return captured.get("status"), bytes(body)

        return asyncio.run(go())

    ESCAPES = [
        "/../../server/config/table_config.json",   # the config the gate protects
        "/../../server/admin_auth.py",              # the gate's own source
        "/../../../../../../Windows/win.ini",       # outside the repo entirely
        "/%2e%2e/%2e%2e/server/admin_auth.py",      # percent-encoded
        "/..%2f..%2fserver/admin_auth.py",          # encoded separator
        "/C:/Windows/win.ini",                      # absolute: join discards base
        "/....//....//server/admin_auth.py",        # doubled-dot filter bypass
    ]

    @pytest.mark.parametrize("path", ESCAPES)
    def test_traversal_never_returns_file_contents(self, path):
        status, body = self._raw_get(path)
        # 404 is the required answer for an escape. A 200 is only acceptable if
        # it is the SPA index fallback, never file bytes from outside dist/.
        if status == 200:
            text = body[:2000].decode("utf-8", "replace")
            assert "<!doctype html" in text.lower(), (
                f"{path} returned {len(body)} bytes of non-HTML content - "
                "the static handler is serving files outside client2/dist")
            for marker in ("business_key", "16-bit app support",
                           "Shared-token gate", "compare_digest"):
                assert marker not in text, (
                    f"{path} leaked file contents (found {marker!r})")
        else:
            assert status == 404, f"{path} answered {status}"

    def test_a_legitimate_asset_is_still_served(self):
        """Guards against 'fixing' the traversal by refusing everything."""
        status, body = self._raw_get("/index.html")
        assert status == 200
        assert b"<!doctype html" in body[:200].lower()


class TestNonAsciiTokenIsRejectedNotSilentlyBroken:
    """[B3] Starlette decodes headers as latin-1; a utf-8 re-encode never matches.

    A Korean-speaking operator following DEPLOY_SETUP ("길고 추측 불가능한
    문자열", no ASCII constraint stated at the time) would set a token, read
    "is set" in the log, and then be told their correct token was wrong on every
    one of the 16 routes.
    """

    def test_non_ascii_token_does_not_count_as_configured(self, monkeypatch):
        monkeypatch.setenv(ENV, "관리자토큰")
        assert admin_auth.configured_token() is None
        assert admin_auth.token_is_unusable() is True

    def test_ascii_token_is_still_accepted(self, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        assert admin_auth.configured_token() == TOKEN
        assert admin_auth.token_is_unusable() is False

    def test_banner_is_an_error_that_names_the_cause_and_the_fix(self, monkeypatch):
        monkeypatch.setenv(ENV, "관리자토큰")
        level, msg = admin_auth.startup_banner()
        assert level == "error", "a non-ASCII token must not log as 'is set'"
        assert "NON-ASCII" in msg
        assert "IGNORED" in msg
        assert ENV in msg
        assert "관리자토큰" not in msg, "the banner leaked the token value"

    def test_it_lands_in_the_unconfigured_state_not_the_locked_out_state(
            self, client, monkeypatch):
        """Code execution refused, everything else open - never all-16-dead."""
        monkeypatch.setenv(ENV, "관리자토큰")
        assert client.get("/admin/chain/rules").status_code == 200
        assert client.post(
            "/admin/auto-update/run-now",
            json={"table_name": "t", "script_name": "s"}).status_code == 503


class TestGateRejectionsAreMachineReadable:
    """[B4] A bare 401/403 is ambiguous; the client must not guess.

    `_resolve_admin_script_path` raises 403 for isolation reasons that have
    nothing to do with the token. The client keyed off the status alone, decided
    the token was bad, and overwrote a correct one.
    """

    def test_gate_401_carries_the_challenge_header(self, client, token_set):
        res = client.get("/admin/chain/rules")
        assert res.status_code == 401
        assert res.headers.get("WWW-Authenticate") == HEADER

    def test_gate_403_carries_the_challenge_header(self, client, token_set):
        res = client.get("/admin/chain/rules", headers={HEADER: "wrong"})
        assert res.status_code == 403
        assert res.headers.get("WWW-Authenticate") == HEADER

    def test_the_isolation_403_does_NOT_carry_it(self, client, token_set,
                                                 monkeypatch, tmp_path):
        """The exact collision that destroyed a valid token."""
        import paths
        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = client.post("/admin/scripts/code",
                          headers={HEADER: TOKEN},
                          json={"path": "mappers/probe.py", "code": "# x\n"})
        assert res.status_code == 403
        assert "isolated data root" in res.json()["detail"]
        assert res.headers.get("WWW-Authenticate") is None, (
            "a non-auth 403 is advertising an auth challenge; the client will "
            "re-prompt and overwrite the operator's working token")

    def test_the_503_is_not_an_auth_challenge(self, client, token_unset):
        """503 means 'configure the server', not 'your token is wrong'."""
        res = client.post("/admin/auto-update/run-now",
                          json={"table_name": "t", "script_name": "s"})
        assert res.status_code == 503
        assert res.headers.get("WWW-Authenticate") is None


class TestInternalEventsAreGated:
    """[B5] Worker->server IPC was the one unauthenticated write surface."""

    CALLS = [
        ("/internal/events/broadcast", {"event": "spoofed", "table_name": "t"}),
        ("/internal/events/batch-refresh", {"table_name": "t", "change_count": 1}),
        ("/internal/events/file-processed", {"table_name": "t", "file_name": "f"}),
        ("/internal/events/ingestion-state",
         {"table_name": "t", "file_name": "f", "state": "QUEUED"}),
    ]

    @pytest.mark.parametrize("path,body", CALLS)
    def test_rejected_without_the_token(self, client, token_set, path, body):
        res = client.post(path, json=body)
        assert res.status_code == 401, (
            f"{path} accepted an unauthenticated write ({res.status_code}); a "
            "forged broadcast reaches every connected grid")

    @pytest.mark.parametrize("path,body", CALLS)
    def test_accepted_with_the_token(self, client, token_set, path, body):
        res = client.post(path, json=body, headers={HEADER: TOKEN})
        assert res.status_code != 401, res.text

    @pytest.mark.parametrize("path,body", CALLS)
    def test_still_open_when_no_token_is_configured(self, client, token_unset,
                                                    path, body):
        """An unconfigured server keeps working exactly as it does today."""
        res = client.post(path, json=body)
        assert res.status_code != 401, res.text

    def test_workers_send_the_header_when_a_token_is_configured(self, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        assert admin_auth.internal_event_headers() == {HEADER: TOKEN}

    def test_workers_send_nothing_when_it_is_not(self, monkeypatch):
        monkeypatch.delenv(ENV, raising=False)
        assert admin_auth.internal_event_headers() == {}

    def test_every_sender_path_attaches_them(self):
        """All THREE daemons post to /internal/events/*, not just one.

        A previous incident in this repo was re-introduced daemon by daemon
        because only one sender was fixed; the memory file records it. Assert
        the call sites textually so a fourth daemon copying an old pattern is
        caught here.
        """
        import inspect
        import run_watcher
        import chain_ingestion_worker
        import graph_sync_worker

        for mod, fn in ((run_watcher, "post_event"),
                        (chain_ingestion_worker, "post_event_async"),
                        (graph_sync_worker, "post_event_async")):
            src = inspect.getsource(getattr(mod, fn))
            assert "internal_event_headers" in src, (
                f"{mod.__name__}.{fn} posts to /internal/events/* without the "
                "admin header; its notifications will 401 on a locked server")


def test_conftest_pins_the_variable_away_from_the_ambient_shell():
    """The suite's behaviour must not depend on whose machine it runs on.

    An operator who has exported ASSY_ADMIN_TOKEN (production setup tells them
    to) would otherwise run the whole suite with the gate enforcing, turning
    every pre-existing /admin test red for a reason unrelated to its subject.
    """
    assert os.environ.get(ENV) is None, (
        "conftest.py must pop ASSY_ADMIN_TOKEN; something re-set it")
