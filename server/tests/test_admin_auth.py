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

#: Routes that reach code execution or a bulk write, and are therefore never open:
#: they refuse with 503 when no token is configured, rather than falling back to
#: open.
STRICT_ADMIN_ROUTES = {
    ("POST", "/admin/scripts/code"),          # writes an arbitrary Python file
    ("POST", "/admin/auto-update/run-now"),   # makes the scheduler run it
    # Queues a retroactive run: rewrites a whole table through a chain rule,
    # withdraws a source's claim on every cell it holds, or deletes graph nodes.
    # Not code execution, but the same class of harm from an unauthenticated
    # caller, and it reaches the same scheduler process by the same outbox.
    ("POST", "/admin/retroactive/{op}/run"),
    # Writes an operator config file that every process reads (ruling
    # R-2026-08-15-M): the source declarations the ledger translators run on, and
    # the ontology layer of the closed vocabulary. Not code execution, but the
    # same class of harm - a caller who can edit these can point a translator at
    # a different table or register a word the gate will then accept. The files
    # are gitignored by design, so an unauthenticated edit has no history to be
    # recovered from either; the route's own timestamped backup is the only undo.
    ("POST", "/admin/ledger/save"),
    # Same file, same reach: retirement changes what the gate will emit.
    ("POST", "/admin/ledger/vocabulary/retire"),
    # Ledger V2 ontology drafts write durable review state, and activation can
    # atomically replace the manifest-owned live declaration. Keep the whole
    # lifecycle strict so an open-token deployment remains read-only.
    ("POST", "/admin/ontology-explorer/drafts"),
    ("PUT", "/admin/ontology-explorer/drafts/{draft_id}"),
    ("POST", "/admin/ontology-explorer/drafts/{draft_id}/review"),
    ("POST", "/admin/ontology-explorer/drafts/{draft_id}/activate"),
    ("DELETE", "/admin/ontology-explorer/drafts/{draft_id}"),
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
        """These must use the fail-closed gate, as a set.

        Downgrading any of them to the ordinary gate would leave an unconfigured
        server offering remote code execution (the exact hole this work closed)
        or an unauthenticated bulk rewrite of a table.
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
        ("post", "/admin/retroactive/graph_orphans/run", {"params": {}}),
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
        """All daemons that post to /internal/events/* attach the header.

        A previous incident in this repo was re-introduced daemon by daemon
        because only one sender was fixed; the memory file records it. Assert
        the call sites textually so a fourth daemon copying an old pattern is
        caught here.
        """
        import inspect
        import run_watcher
        import chain_ingestion_worker

        for mod, fn in ((run_watcher, "post_event"),
                        (chain_ingestion_worker, "post_event_async")):
            src = inspect.getsource(getattr(mod, fn))
            assert "internal_event_headers" in src, (
                f"{mod.__name__}.{fn} posts to /internal/events/* without the "
                "admin header; its notifications will 401 on a locked server")


# --------------------------------------------------------------------------
# [F8] The fingerprint, and the gate signal the senders used to throw away
# --------------------------------------------------------------------------

OTHER_TOKEN = "a-different-but-equally-correct-horse"
NON_ASCII_TOKEN = "관리자토큰"
HEX = set("0123456789abcdef")

#: What the gate attaches to its own rejections, and therefore the only proof a
#: 4xx came from us rather than from a proxy in front of the app.
OUR_CHALLENGE = {admin_auth.GATE_CHALLENGE_HEADER: HEADER}


def _fingerprint_for(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)
    return admin_auth.token_fingerprint()


class TestTokenFingerprint:
    """Eight hex characters that answer "is it the same token?" without leaking it."""

    def test_it_matches_the_command_the_docstring_tells_operators_to_run(
            self, monkeypatch):
        """The oracle is deliberately the operator's own one-liner.

        `token_fingerprint` promises an operator can reproduce it from the value
        in their password manager with a plain sha256. If this drifts (a salt, a
        different digest, a different truncation) that promise breaks silently and
        the operator concludes the two sides differ when they do not.
        """
        import hashlib
        expected = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()[
            :admin_auth.TOKEN_FINGERPRINT_CHARS]
        assert _fingerprint_for(monkeypatch, TOKEN) == expected

    def test_it_is_short_lowercase_hex(self, monkeypatch):
        fp = _fingerprint_for(monkeypatch, TOKEN)
        assert len(fp) == admin_auth.TOKEN_FINGERPRINT_CHARS == 8
        assert set(fp) <= HEX, f"not comparable-by-eye hex: {fp!r}"

    def test_two_different_tokens_do_not_share_a_fingerprint(self, monkeypatch):
        """The whole diagnostic value: different environments must LOOK different."""
        assert (_fingerprint_for(monkeypatch, TOKEN)
                != _fingerprint_for(monkeypatch, OTHER_TOKEN))

    def test_the_same_token_fingerprints_identically_every_time(self, monkeypatch):
        """It is compared across two processes, so it cannot carry per-call state."""
        first = _fingerprint_for(monkeypatch, TOKEN)
        assert _fingerprint_for(monkeypatch, TOKEN) == first

    def test_surrounding_whitespace_does_not_change_it(self, monkeypatch):
        """`configured_token` strips; the fingerprint must strip identically.

        Otherwise cmd.exe's trailing space produces a different fingerprint from
        the same token, and an operator chases a divergence that does not exist.
        """
        assert (_fingerprint_for(monkeypatch, "  " + TOKEN + "  ")
                == _fingerprint_for(monkeypatch, TOKEN))

    def test_unset_and_unusable_are_distinct_and_not_mistakable_for_hex(
            self, monkeypatch):
        """An operator comparing two logs must never see one side print nothing.

        And the two states need different names because they need different
        remedies: unset means ADD the variable, unusable means REPLACE it.
        """
        none_fp = _fingerprint_for(monkeypatch, None)
        unusable_fp = _fingerprint_for(monkeypatch, NON_ASCII_TOKEN)
        assert none_fp == admin_auth.FINGERPRINT_NONE
        assert unusable_fp == admin_auth.FINGERPRINT_UNUSABLE
        assert none_fp != unusable_fp
        for marker in (none_fp, unusable_fp):
            assert marker, "a state with no digest still has to print something"
            assert not set(marker) <= HEX, (
                f"{marker!r} could be read as a real fingerprint")

    def test_a_whitespace_only_value_reads_as_unset_not_as_a_token(self, monkeypatch):
        """It resolves to None in `configured_token`; the fingerprint must agree."""
        assert _fingerprint_for(monkeypatch, "   ") == admin_auth.FINGERPRINT_NONE


class TestNoOutputCarriesTheRawToken:
    """The hard constraint: nothing but the truncated digest ever gets out.

    Asserted over every text-producing entry point in `admin_auth`, in all three
    token states, rather than over the two functions that happened to exist when
    this was written.
    """

    #: Public `admin_auth` callables that are NOT operator-facing text, each with
    #: the reason it is exempt. Two of them return the secret itself - that is
    #: their job; the leak rule is about what reaches a log or a response body.
    NOT_TEXT_PRODUCERS = {
        "configured_token",       # returns the secret, by design
        "internal_event_headers", # puts the secret in a request header, by design
        "token_is_unusable",      # bool
        "require_admin_token",    # raises HTTPException; bodies covered above
        "require_admin_token_strict",
    }

    @staticmethod
    def _emitted_text(label="Some Worker"):
        """Every operator-facing string `admin_auth` can produce right now."""
        out = [admin_auth.token_fingerprint(),
               admin_auth.startup_banner()[1],
               admin_auth.worker_token_banner(label)[1]]
        for status in (401, 403, 407, 500):
            for headers in (None, {}, dict(OUR_CHALLENGE),
                            {admin_auth.GATE_CHALLENGE_HEADER: "Basic realm=x",
                             "Server": "nginx/1.24.0", "Via": "1.1 proxy"}):
                note = admin_auth.internal_event_failure_note(status, headers)
                if note is not None:
                    out.append(note)
        return out

    #: The three states, plus a token whose digest is what gets printed.
    @pytest.mark.parametrize("env_value", [None, "   ", TOKEN, OTHER_TOKEN,
                                           NON_ASCII_TOKEN])
    def test_no_emitted_line_contains_the_configured_token(
            self, monkeypatch, env_value):
        if env_value is None:
            monkeypatch.delenv(ENV, raising=False)
        else:
            monkeypatch.setenv(ENV, env_value)
        for text in self._emitted_text():
            assert isinstance(text, str)
            if env_value and env_value.strip():
                assert env_value.strip() not in text, (
                    f"the raw token reached operator-facing output: {text!r}")
                assert env_value not in text

    def test_every_text_producer_is_covered_by_the_leak_check(self):
        """A new banner must not be addable without a leak check.

        Compares SETS, per this module's own docstring: a producer swapped for
        another would satisfy any count-based assertion.
        """
        import inspect

        public = {name for name, fn in inspect.getmembers(admin_auth, inspect.isfunction)
                  if not name.startswith("_") and fn.__module__ == "admin_auth"}
        covered = {"token_fingerprint", "startup_banner", "worker_token_banner",
                   "internal_event_failure_note"}
        unaccounted = public - covered - self.NOT_TEXT_PRODUCERS
        assert not unaccounted, (
            f"admin_auth gained public function(s) {sorted(unaccounted)} that "
            "neither _emitted_text() checks for leaks nor NOT_TEXT_PRODUCERS "
            "exempts with a reason")
        assert not (covered & self.NOT_TEXT_PRODUCERS)

    def test_the_leak_check_would_actually_catch_a_leak(self, monkeypatch):
        """Proves the assertion above has teeth rather than passing vacuously.

        A test that never sees a failing case proves nothing about the case it
        claims to guard, so a leaking producer is injected here and the same
        comparison the real test makes is asserted to reject it.
        """
        monkeypatch.setenv(ENV, TOKEN)
        monkeypatch.setattr(
            admin_auth, "startup_banner",
            lambda: ("info", f"[admin-auth] token is {admin_auth.configured_token()}"))
        leaked = [t for t in self._emitted_text() if TOKEN in t]
        assert leaked, "the injected leak was not visible to _emitted_text()"


class TestOperatorFacingLinesSurviveTheProductionConsole:
    """Every emitted line must encode in **cp949**.

    The production console is a Korean Windows console and `run_app.bat` sets no
    `PYTHONIOENCODING`, so a character outside cp949 makes the logging handler
    raise and **drop the line**. This is not theoretical: the first draft of the
    proxy diagnosis used an em dash (U+2014, absent from cp949 - unlike the
    visually identical U+2015), which would have silently deleted the one
    sentence that names a proxy during a proxy incident.
    """

    @staticmethod
    def _all_operator_lines(monkeypatch):
        import internal_event_client

        class _Refused:
            status_code = 403
            headers = {"Server": "squid/5.7", "Via": "1.1 corp"}

        monkeypatch.setattr(internal_event_client, "internal_event_session",
                            lambda: type("S", (), {
                                "get": staticmethod(lambda url, **kw: _Refused())})())
        monkeypatch.setattr("urllib.request.getproxies",
                            lambda: {"http": "http://proxy.corp:8080"})

        lines = list(TestNoOutputCarriesTheRawToken._emitted_text())
        lines.append(internal_event_client.check_api_reachable("http://127.0.0.1:8080")[1])
        lines.append(internal_event_client.proxy_environment_summary())
        lines.extend(m for _, m in internal_event_client.startup_lines(
            "W", "http://elsewhere:8080"))
        return lines

    @pytest.mark.parametrize("env_value", [None, TOKEN, NON_ASCII_TOKEN])
    def test_every_emitted_line_encodes_in_cp949(self, monkeypatch, env_value):
        if env_value is None:
            monkeypatch.delenv(ENV, raising=False)
        else:
            monkeypatch.setenv(ENV, env_value)
        for line in self._all_operator_lines(monkeypatch):
            try:
                line.encode("cp949")
            except UnicodeEncodeError as e:
                pytest.fail(
                    f"character {e.object[e.start:e.end]!r} (U+{ord(e.object[e.start]):04X}) "
                    f"cannot be printed on the production console, so this line is "
                    f"DROPPED there: {line[:120]!r}")


class TestGateStatusSemanticsAreUnchanged:
    """401 = no header, 403 = mismatch, 503 = unset on a code-execution route.

    Pinned as one block because an operator runbook and an incident diagnosis
    both read this mapping backwards from the status code alone. In particular a
    missing header must NEVER answer 403: that is what made a production 403
    provably not ours, and re-mapping it would erase the distinction.
    """

    def test_the_three_way_mapping(self, client, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        assert client.get("/admin/chain/rules").status_code == 401
        assert client.get("/admin/chain/rules",
                          headers={HEADER: "not-the-token"}).status_code == 403
        monkeypatch.delenv(ENV, raising=False)
        assert client.post("/admin/auto-update/run-now",
                           json={"table_name": "t", "script_name": "s"}
                           ).status_code == 503

    def test_an_absent_header_is_401_on_the_internal_events_too(
            self, client, token_set):
        """The endpoint the incident was reported on, asserted directly."""
        res = client.post("/internal/events/broadcast",
                          json={"event": "x", "table_name": "t"})
        assert res.status_code == 401, (
            "a no-header internal event must answer 401; if this is ever 403 the "
            "diagnosis 'a 403 with no header cannot be us' stops being true")
        assert res.headers.get(admin_auth.GATE_CHALLENGE_HEADER) == HEADER


class TestTheFailureNoteNamesWhoRefusedAndWhatToDo:
    """[F8-b] The single most useful line in the incident, and it was discarded."""

    def test_our_gate_403_says_the_tokens_differ_and_names_the_remedy(
            self, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(403, dict(OUR_CHALLENGE))
        assert "admin-gate=yes" in note
        assert admin_auth.token_fingerprint() in note   # comparable with the server
        assert "DIFFERENT" in note
        assert "WHOLE launcher tree" in note, "the remedy must be stated, not implied"

    def test_a_403_without_our_challenge_says_it_is_not_us(self, monkeypatch):
        """The production case: a no-token probe answered 403, which we cannot do."""
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(
            403, {"Server": "nginx/1.24.0", "Via": "1.1 corp-proxy"})
        assert "admin-gate=no" in note
        assert "NOT AN ADMIN-TOKEN FAILURE" in note
        assert "nginx/1.24.0" in note, "whoever answered must be named if it says so"
        assert "1.1 corp-proxy" in note
        assert "proxy" in note.lower()
        assert admin_auth.token_fingerprint() not in note, (
            "an upstream refusal must not invite a token comparison; that is the "
            "hour of restarts this note exists to prevent")

    def test_a_foreign_www_authenticate_does_not_count_as_ours(self, monkeypatch):
        """A proxy's own Basic challenge must not be read as the admin gate."""
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(
            403, {admin_auth.GATE_CHALLENGE_HEADER: 'Basic realm="corp"'})
        assert "admin-gate=no" in note
        assert "Basic" in note

    def test_it_reads_the_challenge_case_insensitively_like_requests_does(
            self, monkeypatch):
        """Real responses arrive in a CaseInsensitiveDict with arbitrary casing.

        Our own gate would otherwise be misattributed to a proxy purely because
        the header came back lowercased - inverting the conclusion.
        """
        from requests.structures import CaseInsensitiveDict
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(
            403, CaseInsensitiveDict({"www-authenticate": "x-admin-token"}))
        assert "admin-gate=yes" in note

    def test_401_with_no_token_here_tells_the_operator_to_set_it(self, monkeypatch):
        monkeypatch.delenv(ENV, raising=False)
        note = admin_auth.internal_event_failure_note(401, dict(OUR_CHALLENGE))
        assert admin_auth.FINGERPRINT_NONE in note
        assert ENV in note
        assert "run_decoupled_app.py" in note

    def test_401_with_a_non_ascii_token_says_replace_not_add(self, monkeypatch):
        """Reporting this as "unset" sends the operator to add what is already there."""
        monkeypatch.setenv(ENV, NON_ASCII_TOKEN)
        note = admin_auth.internal_event_failure_note(401, dict(OUR_CHALLENGE))
        assert admin_auth.FINGERPRINT_UNUSABLE in note
        assert "ASCII" in note
        assert "do not just add it" in note

    def test_401_while_holding_a_usable_token_means_the_header_was_stripped(
            self, monkeypatch):
        """The gate saw nothing although we sent something - a third remedy."""
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(401, dict(OUR_CHALLENGE))
        assert "stripped in transit" in note

    @pytest.mark.parametrize("status", [200, 404, 422, 500, 502, 503])
    def test_non_auth_statuses_get_no_auth_paragraph(self, monkeypatch, status):
        monkeypatch.setenv(ENV, TOKEN)
        assert admin_auth.internal_event_failure_note(status, {}) is None

    def test_a_hostile_upstream_cannot_forge_log_lines_through_its_headers(
            self, monkeypatch):
        """The echoed value is not our secret, but it is not our data either."""
        monkeypatch.setenv(ENV, TOKEN)
        note = admin_auth.internal_event_failure_note(
            403, {"Server": "evil\r\n[admin-auth] ALL CLEAR, token fingerprint deadbeef"})
        assert "\n" not in note and "\r" not in note
        assert "ALL CLEAR" not in note or len(note.splitlines()) == 1
        assert len(note.splitlines()) == 1, "a note must stay one line"

    def test_it_survives_a_response_with_no_usable_headers(self, monkeypatch):
        """Never raise inside a failure handler - that converts a log line into a
        swallowed exception and loses the original status too."""
        monkeypatch.setenv(ENV, TOKEN)

        class Hostile:
            def get(self, name):
                raise RuntimeError("no headers for you")

        assert "admin-gate=no" in admin_auth.internal_event_failure_note(403, Hostile())
        assert "admin-gate=no" in admin_auth.internal_event_failure_note(403, None)


# --------------------------------------------------------------------------
# [F8] ...and every sender actually logs it
# --------------------------------------------------------------------------

class _CapturingLogger:
    """Stands in for a process logger.

    Substituted for the module's `logger` rather than captured with `caplog`
    because `get_process_logger` strips and re-adds root handlers on import, so
    capture through the logging tree depends on module import order.
    """

    def __init__(self):
        self.lines = []

    def _record(self, level):
        def emit(msg, *args, **kwargs):
            self.lines.append((level, str(msg)))
        return emit

    def __getattr__(self, name):
        if name in ("debug", "info", "warning", "error", "critical", "exception"):
            return self._record(name)
        raise AttributeError(name)

    def text(self):
        return "\n".join(m for _, m in self.lines)


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        from requests.structures import CaseInsensitiveDict
        self.status_code = status_code
        self.headers = CaseInsensitiveDict(headers or {})
        self.ok = 200 <= status_code < 300


def _drive_sender(monkeypatch, module_name, response):
    """POST one internal event through a real sender, with the socket faked.

    Returns the capturing logger. The point is that the *production* function
    runs: a test that reimplemented the log line would pass against a sender that
    never calls the note at all.

    Only ONE thing is faked for all three senders - the shared session factory -
    which is itself the assertion that all three route through it. Before this
    round each sender built its own client and this helper needed three different
    patches.
    """
    import asyncio
    import importlib

    import internal_event_client

    mod = importlib.import_module(module_name)
    cap = _CapturingLogger()
    monkeypatch.setattr(mod, "logger", cap)

    class _Sess:
        @staticmethod
        def post(url, **kwargs):
            return response

    monkeypatch.setattr(internal_event_client, "internal_event_session",
                        lambda: _Sess())

    if module_name == "run_watcher":
        mod.post_event("/internal/events/broadcast", {"event": "x"})
    else:
        asyncio.run(mod.post_event_async("/internal/events/broadcast", {"event": "x"}))
    return cap


#: Every daemon that POSTs to /internal/events/*. A fix applied to one sender
#: only is a defect this repo has already shipped on this exact endpoint, which is
#: why every case below is parametrized across all three rather than spot-checked.
SENDERS = ["run_watcher", "chain_ingestion_worker"]


class TestEverySenderLogsWhoRefused:

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_our_gate_403_is_attributed_to_the_gate_with_a_fingerprint(
            self, monkeypatch, module_name):
        monkeypatch.setenv(ENV, TOKEN)
        cap = _drive_sender(monkeypatch, module_name,
                            _FakeResponse(403, dict(OUR_CHALLENGE)))
        text = cap.text()
        assert "403" in text
        assert "admin-gate=yes" in text, f"{module_name} discarded the gate signal"
        assert admin_auth.token_fingerprint() in text
        assert TOKEN not in text, f"{module_name} logged the raw token"

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_an_upstream_403_is_not_blamed_on_the_token(
            self, monkeypatch, module_name):
        """The production shape: 403 with no challenge header of ours."""
        monkeypatch.setenv(ENV, TOKEN)
        cap = _drive_sender(monkeypatch, module_name,
                            _FakeResponse(403, {"Server": "nginx/1.24.0"}))
        text = cap.text()
        assert "admin-gate=no" in text, f"{module_name} discarded the gate signal"
        assert "NOT AN ADMIN-TOKEN FAILURE" in text
        assert "nginx/1.24.0" in text
        assert admin_auth.token_fingerprint() not in text

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_a_401_names_the_missing_variable(self, monkeypatch, module_name):
        monkeypatch.delenv(ENV, raising=False)
        cap = _drive_sender(monkeypatch, module_name,
                            _FakeResponse(401, dict(OUR_CHALLENGE)))
        text = cap.text()
        assert "admin-gate=yes" in text
        assert ENV in text

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_an_ordinary_500_is_logged_without_an_auth_paragraph(
            self, monkeypatch, module_name):
        monkeypatch.setenv(ENV, TOKEN)
        cap = _drive_sender(monkeypatch, module_name, _FakeResponse(500))
        text = cap.text()
        assert "500" in text
        assert "admin-gate" not in text, "a 500 must not read as an auth problem"

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_a_success_logs_nothing_about_tokens(self, monkeypatch, module_name):
        """The note is a failure-path diagnostic, not per-call noise."""
        monkeypatch.setenv(ENV, TOKEN)
        cap = _drive_sender(monkeypatch, module_name, _FakeResponse(200))
        assert "admin-gate" not in cap.text()
        assert TOKEN not in cap.text()

    def test_the_chain_sender_still_reports_delivery_as_a_bool(self, monkeypatch):
        """`broadcast_at` stamping keys off this return value.

        A row stamped as delivered when it was not is permanently stale - the
        undelivered-broadcast sweep only re-fires rows whose `broadcast_at` is
        still NULL - so the new logging branch must not disturb the contract.
        """
        monkeypatch.setenv(ENV, TOKEN)
        import asyncio
        import chain_ingestion_worker as ciw

        cap = _drive_sender(monkeypatch, "chain_ingestion_worker",
                            _FakeResponse(403, dict(OUR_CHALLENGE)))
        assert "admin-gate=yes" in cap.text()  # the new branch really ran

        import internal_event_client

        class _Sess:
            @staticmethod
            def post(url, **kwargs):
                return _FakeResponse(403, dict(OUR_CHALLENGE))

        monkeypatch.setattr(internal_event_client, "internal_event_session",
                            lambda: _Sess())
        monkeypatch.setattr(ciw, "logger", _CapturingLogger())
        assert asyncio.run(
            ciw.post_event_async("/internal/events/broadcast", {})) is False
        monkeypatch.setattr(internal_event_client, "internal_event_session",
                            lambda: type("S", (), {
                                "post": staticmethod(lambda url, **kw: _FakeResponse(200))})())
        assert asyncio.run(
            ciw.post_event_async("/internal/events/broadcast", {})) is True

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_the_sender_source_references_the_shared_note(self, module_name):
        """Textual, alongside the behavioural cases above, so a FOURTH daemon
        copying an old sender is caught here rather than during an incident."""
        import importlib
        import inspect

        mod = importlib.import_module(module_name)
        fn = "post_event" if module_name == "run_watcher" else "post_event_async"
        src = inspect.getsource(getattr(mod, fn))
        assert "internal_event_failure_note" in src, (
            f"{module_name}.{fn} logs a bare status code; a 401, a 403 from our "
            "gate and a 403 from a proxy are indistinguishable in its log")


class TestEveryDaemonAnnouncesItsFingerprintAtStartup:
    """One fingerprint is not a comparison; the pair is the diagnosis."""

    def test_the_server_banner_carries_it_in_every_state(self, monkeypatch):
        monkeypatch.setenv(ENV, TOKEN)
        assert admin_auth.token_fingerprint() in admin_auth.startup_banner()[1]
        monkeypatch.delenv(ENV, raising=False)
        assert admin_auth.FINGERPRINT_NONE in admin_auth.startup_banner()[1]
        monkeypatch.setenv(ENV, NON_ASCII_TOKEN)
        assert admin_auth.FINGERPRINT_UNUSABLE in admin_auth.startup_banner()[1]

    @pytest.mark.parametrize("env_value,level", [
        (TOKEN, "info"),
        (None, "warning"),          # the silent state: 200s while nothing is locked
        (NON_ASCII_TOKEN, "error"),
    ])
    def test_the_worker_banner_levels_match_the_servers(
            self, monkeypatch, env_value, level):
        if env_value is None:
            monkeypatch.delenv(ENV, raising=False)
        else:
            monkeypatch.setenv(ENV, env_value)
        got_level, msg = admin_auth.worker_token_banner("Some Worker")
        assert got_level == level
        assert admin_auth.token_fingerprint() in msg
        assert "Some Worker" in msg, "the line must say which process it describes"

    @pytest.mark.parametrize("module_name,func_name", [
        ("run_watcher", "main"),
        ("chain_ingestion_worker", "start_chain_ingestion_worker"),
    ])
    def test_each_daemon_startup_path_logs_the_banner(self, module_name, func_name):
        import importlib
        import inspect

        mod = importlib.import_module(module_name)
        src = inspect.getsource(getattr(mod, func_name))
        assert "startup_lines" in src, (
            f"{module_name}.{func_name} starts a process that presents the admin "
            "token without ever saying which token it holds")


# --------------------------------------------------------------------------
# [F8] The root cause: a loopback call that consulted proxy configuration
# --------------------------------------------------------------------------

class TestInternalCallsNeverConsultProxyConfiguration:
    """2026-07-30: a corporate proxy answered 403 for POSTs to 127.0.0.1.

    `requests` defaults `trust_env=True`, so a bare Session reads HTTP_PROXY and
    the Windows proxy registry, and ProxyOverride's `<local>` token exempts only
    dotless hostnames - `localhost` is bypassed, `127.0.0.1` is not. The worker's
    notification left the machine, and the proxy refused to relay to a private
    address. Every symptom followed: 403 rather than 401, ungated paths refusing
    too, immunity to restarts, and invisibility on a dev box with no proxy.
    """

    def test_the_shared_session_does_not_trust_the_environment(self):
        import internal_event_client

        sess = internal_event_client.internal_event_session()
        assert sess.trust_env is False, (
            "the session honours HTTP_PROXY and the Windows proxy registry; "
            "loopback notifications can be relayed off-box and refused")

    def test_the_session_is_reused_per_thread(self):
        """Keep-alive was the reason a session existed at all; do not lose it."""
        import internal_event_client

        assert (internal_event_client.internal_event_session()
                is internal_event_client.internal_event_session())

    def test_each_thread_gets_its_own_session(self):
        """`requests.Session` is not thread-safe and run_watcher posts from two."""
        import threading

        import internal_event_client

        seen = []
        main_session = internal_event_client.internal_event_session()

        def grab():
            seen.append(internal_event_client.internal_event_session())

        t = threading.Thread(target=grab)
        t.start()
        t.join()
        assert seen and seen[0] is not main_session

    @pytest.mark.parametrize("module_name", SENDERS)
    def test_no_sender_builds_its_own_client(self, module_name):
        """The enforcement that replaces a comment saying "remember to".

        This exact defect has been fixed sender-by-sender three times on this one
        endpoint. A fourth sender that calls `requests.post` directly re-opens it,
        so the bypass is what fails here - not the absence of a fix.
        """
        import importlib
        import inspect

        mod = importlib.import_module(module_name)
        fn = "post_event" if module_name == "run_watcher" else "post_event_async"
        src = inspect.getsource(getattr(mod, fn))
        assert "internal_event_session" in src, (
            f"{module_name}.{fn} does not use the shared session factory")
        for banned in ("requests.post(", "requests.Session("):
            assert banned not in src, (
                f"{module_name}.{fn} builds its own HTTP client ({banned}), which "
                "defaults to trusting proxy environment variables")

    def test_a_proxy_url_with_credentials_is_not_logged(self, monkeypatch):
        """The summary goes into a log file; proxy URLs routinely carry passwords."""
        import internal_event_client

        redacted = internal_event_client._redact_proxy(
            "http://svc_account:s3cr3t@proxy.corp:8080")
        assert "s3cr3t" not in redacted
        assert "svc_account" not in redacted
        assert "proxy.corp:8080" in redacted, "the diagnostic value must survive"

    def test_the_proxy_summary_names_a_configured_proxy(self, monkeypatch):
        """The fact whose absence from every log made this invisible for hours."""
        import internal_event_client

        monkeypatch.setattr("urllib.request.getproxies",
                            lambda: {"http": "http://proxy.corp:8080"})
        summary = internal_event_client.proxy_environment_summary()
        assert "proxy.corp:8080" in summary
        assert summary != "none"

    def test_the_proxy_summary_says_none_when_there_is_none(self, monkeypatch):
        import internal_event_client

        monkeypatch.setattr("urllib.request.getproxies", lambda: {})
        assert internal_event_client.proxy_environment_summary() == "none"

    def test_the_summary_never_raises_out_of_a_startup_path(self, monkeypatch):
        import internal_event_client

        def boom():
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr("urllib.request.getproxies", boom)
        assert isinstance(internal_event_client.proxy_environment_summary(), str)

    @pytest.mark.parametrize("url,expected", [
        ("http://127.0.0.1:8080", True),
        ("http://localhost:8081", True),
        ("http://api.corp.example:8080", False),
        ("not a url at all", False),
    ])
    def test_loopback_detection(self, url, expected):
        import internal_event_client

        assert internal_event_client.is_loopback(url) is expected

    def test_one_place_defines_the_web_servers_address(self):
        """Three modules previously repeated the literal independently."""
        import chain_ingestion_worker
        import internal_event_client
        import run_watcher

        assert (internal_event_client.DEFAULT_API_BASE_URL
                == "http://127.0.0.1:8080")
        for mod in (chain_ingestion_worker, run_watcher):
            assert mod.API_BASE_URL == internal_event_client.api_base_url(), (
                f"{mod.__name__} resolves the API address by itself")


class TestTheStartupCheckSaysWhatAFirstBroadcastWouldHaveDiscovered:
    """/health is ungated, which is what makes it a decisive probe."""

    @staticmethod
    def _probe(monkeypatch, response=None, exc=None):
        import internal_event_client

        class _Sess:
            @staticmethod
            def get(url, **kwargs):
                if exc is not None:
                    raise exc
                return response

        monkeypatch.setattr(internal_event_client, "internal_event_session",
                            lambda: _Sess())
        monkeypatch.setattr("urllib.request.getproxies", lambda: {})
        return internal_event_client.check_api_reachable("http://127.0.0.1:8080")

    def test_a_200_is_reported_as_direct(self, monkeypatch):
        level, msg = self._probe(monkeypatch, _FakeResponse(200))
        assert level == "info"
        assert "200" in msg

    def test_a_refused_connection_at_boot_is_not_an_alarm(self, monkeypatch):
        """The launcher starts the API and the workers seconds apart.

        An ERROR on every normal startup is an ERROR nobody reads, which would
        destroy the value of the one that matters.
        """
        import requests

        level, msg = self._probe(
            monkeypatch, exc=requests.exceptions.ConnectionError("refused"))
        assert level == "info"
        assert "normal during startup" in msg

    def test_any_http_status_on_health_is_an_error_that_names_the_proxy(
            self, monkeypatch):
        """The incident, caught at startup instead of at the first correction."""
        level, msg = self._probe(
            monkeypatch, _FakeResponse(403, {"Server": "squid/5.7"}))
        assert level == "error"
        assert "403" in msg
        assert "squid/5.7" in msg, "whoever answered must be named"
        assert "NO admin gate" in msg
        assert "NO_PROXY" in msg, "the remedy must be in the line, not in a doc"
        assert "프록시" in msg

    def test_the_probe_never_raises(self, monkeypatch):
        level, msg = self._probe(monkeypatch, exc=RuntimeError("anything"))
        assert level == "info" and isinstance(msg, str)

    def test_startup_lines_pair_the_token_with_the_reachability(self, monkeypatch):
        import internal_event_client

        monkeypatch.setenv(ENV, TOKEN)
        monkeypatch.setattr(internal_event_client, "check_api_reachable",
                            lambda base, **kw: ("info", "[internal-events] probed"))
        lines = internal_event_client.startup_lines("Some Worker",
                                                    "http://127.0.0.1:8080")
        text = "\n".join(m for _, m in lines)
        assert admin_auth.token_fingerprint() in text
        assert "Some Worker" in text
        assert "probed" in text
        assert TOKEN not in text

    def test_an_off_box_api_url_warns_but_does_not_refuse(self, monkeypatch):
        """A worker that refuses to start stops ingestion; a warned worker does not.

        The admin gate makes the same trade in the same direction - fail closed
        only where the harm is code execution.
        """
        import internal_event_client

        monkeypatch.delenv(ENV, raising=False)
        monkeypatch.setattr(internal_event_client, "check_api_reachable",
                            lambda base, **kw: ("info", "probed"))
        lines = internal_event_client.startup_lines("W", "http://elsewhere:8080")
        levels = [lvl for lvl, _ in lines]
        assert "warning" in levels
        assert "critical" not in levels
        assert any("not this machine" in m for _, m in lines)


def test_conftest_pins_the_variable_away_from_the_ambient_shell():
    """The suite's behaviour must not depend on whose machine it runs on.

    An operator who has exported ASSY_ADMIN_TOKEN (production setup tells them
    to) would otherwise run the whole suite with the gate enforcing, turning
    every pre-existing /admin test red for a reason unrelated to its subject.
    """
    assert os.environ.get(ENV) is None, (
        "conftest.py must pop ASSY_ADMIN_TOKEN; something re-set it")
