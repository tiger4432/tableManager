"""Shared-token gate for the ``/admin/*`` surface.

Production is an intranet share for a handful of people, so this is deliberately
**not** a login system: no users, no sessions, no password store. One secret,
read from the environment at startup, presented in a request header.

Threat model
------------
Before this module, every ``/admin/*`` route was reachable by anyone who could
route a packet to the server. Two of them chain into arbitrary code execution:
``POST /admin/scripts/code`` writes a Python file into ``mappers/`` or
``ingestion_workspace/``, and ``POST /admin/auto-update/run-now`` schedules it to
run. The ``GET`` routes are not merely informational either - they return source
code and enumerate the pipeline surface.

The two states
--------------
The gate has two behaviours, and the split is intentional:

``ASSY_ADMIN_TOKEN`` **set**
    Every ``/admin/*`` API route requires the header. Reads included.

``ASSY_ADMIN_TOKEN`` **unset**
    The two code-execution routes refuse with **503** (fail closed - forgetting
    to configure the secret must not leave the hole open), while the remaining
    admin routes keep serving. An operator who restarts into the new build is
    not locked out of the whole admin page before they have read the release
    note; they lose exactly the two routes that can hurt them.

Why an environment variable and not a config file
-------------------------------------------------
``server/config/`` is gitignored, so a file there would also be safe from a
commit - but the repo already has a settled convention for operator-supplied
secrets and locations (``DATABASE_URL``, ``ASSY_DATA_ROOT``, ``ASSY_API_PORT``),
and an env var is the only option that never lands on disk inside the repo at
all. It also cannot be picked up by the snapshot tooling that copies
``server/config/**`` into an isolated data root, which would otherwise duplicate
the secret into a second tree.

Leak discipline
---------------
The token value must never reach a log line, an audit row, an error body, or a
traceback:

* It travels in ``X-Admin-Token``. The context middleware in ``main.py`` reads
  ``X-User`` / ``X-Transaction-ID`` / ``X-Source`` (and their query-parameter
  fallbacks) - different names, so the token cannot ride into ``request_user``,
  ``request_transaction_id`` or ``request_source``, and therefore cannot reach
  an ``AuditLog`` row.
* It is never a query parameter, so it never reaches the uvicorn access log.
* The rejection details below are constant strings. They do not echo what was
  presented, and the comparison is wrapped so that a malformed header value
  produces a plain 403 instead of a ``TypeError`` traceback carrying the value.
* Declaring the header via ``Request`` rather than ``Header(...)`` is also part
  of this: a FastAPI validation error would render the offending value into the
  422 response body.
"""
import os
import secrets

from fastapi import HTTPException, Request

#: Environment variable the operator sets. Documented in guide/DEPLOY_SETUP.md.
ADMIN_TOKEN_ENV = "ASSY_ADMIN_TOKEN"

#: Request header the client presents it in. Deliberately distinct from the
#: X-User / X-Transaction-ID / X-Source names the context middleware consumes.
ADMIN_TOKEN_HEADER = "X-Admin-Token"

_UNSET_DETAIL = (
    "이 기능은 관리자 토큰이 설정되어야 사용할 수 있습니다. "
    f"서버 환경변수 {ADMIN_TOKEN_ENV}를 설정한 뒤 서버를 재시작하세요."
)
_MISSING_DETAIL = "관리자 토큰이 필요합니다."
_MISMATCH_DETAIL = "관리자 토큰이 올바르지 않습니다."

#: Sent with every rejection the gate itself produces, so a client can tell an
#: AUTH failure from a same-status failure raised by a handler for its own
#: reasons. `_resolve_admin_script_path` answers 403 when an isolated server is
#: asked to write into the live tree; without this header the admin page treated
#: that as "your token is wrong", re-prompted, and overwrote a perfectly good
#: token with whatever the confused operator typed.
GATE_CHALLENGE_HEADER = "WWW-Authenticate"
_GATE_HEADERS = {GATE_CHALLENGE_HEADER: ADMIN_TOKEN_HEADER}


def _raw_token():
    return (os.environ.get(ADMIN_TOKEN_ENV) or "").strip()


def token_is_unusable():
    """True when a token IS set but can never authenticate.

    HTTP headers arrive as latin-1 decoded text; any non-ASCII secret therefore
    cannot survive the round trip intact, and every correct attempt would be
    answered "your token is wrong" while the startup banner reassuringly said
    the surface was locked. That is a worse failure than no token at all, so it
    is detected explicitly rather than left to fail at request time.
    """
    raw = _raw_token()
    return bool(raw) and not raw.isascii()


def configured_token():
    """The operator's secret, or ``None`` when it is not usable.

    Read at call time rather than captured at import so that tests can
    monkeypatch the environment without reimporting ``main``. A whitespace-only
    value counts as unset - an operator who exports an empty string has not
    configured anything, and treating it as a real token would produce a secret
    that any request can guess.

    A non-ASCII value also resolves to ``None`` (see :func:`token_is_unusable`).
    That deliberately lands the server in the *unconfigured* state - code
    execution refused, everything else open - rather than the locked-out state,
    and :func:`startup_banner` reports it at ERROR level naming the cause. The
    alternative, enforcing with a secret nobody can present, bricks all 16
    routes and is only recoverable by unsetting the variable and restarting.
    """
    raw = _raw_token()
    if not raw or not raw.isascii():
        return None
    return raw


def _matches(presented, expected):
    """Constant-time compare. Never raises, never surfaces either operand."""
    try:
        return secrets.compare_digest(
            presented.encode("utf-8"), expected.encode("utf-8")
        )
    except Exception:
        # A header value Starlette decoded as latin-1 may not survive the
        # round-trip. Any such input is simply not the token.
        return False


def _enforce(request, fail_closed):
    expected = configured_token()
    if expected is None:
        if fail_closed:
            raise HTTPException(status_code=503, detail=_UNSET_DETAIL)
        return
    presented = request.headers.get(ADMIN_TOKEN_HEADER)
    if not presented:
        raise HTTPException(status_code=401, detail=_MISSING_DETAIL,
                            headers=dict(_GATE_HEADERS))
    if not _matches(presented, expected):
        raise HTTPException(status_code=403, detail=_MISMATCH_DETAIL,
                            headers=dict(_GATE_HEADERS))


def require_admin_token(request: Request) -> None:
    """Gate for ordinary ``/admin/*`` routes.

    Enforces the header when a token is configured; stays open when it is not,
    so a first restart into this build does not black out the admin page.
    """
    _enforce(request, fail_closed=False)


def require_admin_token_strict(request: Request) -> None:
    """Gate for the ``/admin/*`` routes that reach code execution.

    Same as :func:`require_admin_token` when a token is configured, but refuses
    with 503 when it is not. These routes are never open.
    """
    _enforce(request, fail_closed=True)


#: Every dependency this module offers. The route-coverage test walks the
#: FastAPI app and asserts each /admin route resolves to one of these, so a new
#: admin route added later fails the suite instead of shipping unprotected.
ADMIN_GATES = (require_admin_token, require_admin_token_strict)


def internal_event_headers():
    """Headers a worker must attach when calling ``/internal/events/*``.

    The workers are children of ``run_decoupled_app.py`` and inherit its
    environment (``process_supervisor.py`` builds each child's env from
    ``os.environ.copy()``), so setting the variable once for the launcher is
    enough. Empty dict when no token is configured, which matches the gate
    staying open in that state.
    """
    token = configured_token()
    return {ADMIN_TOKEN_HEADER: token} if token else {}


def startup_banner():
    """The line the server logs at startup, as ``(level, message)``.

    An operator restarting into this build must not have to discover the new
    requirement by trial, so the unset case names the variable and says exactly
    what stops working.
    """
    if token_is_unusable():
        # Loudest of the three: the operator believes the surface is locked.
        return "error", (
            f"[admin-auth] {ADMIN_TOKEN_ENV} is set but contains NON-ASCII "
            "characters, which cannot survive an HTTP header round trip. It is "
            "being IGNORED - the admin surface is NOT locked, and the two "
            "code-execution routes are disabled (503). Re-set "
            f"{ADMIN_TOKEN_ENV} to an ASCII-only value and restart. "
            "See docs/guide/DEPLOY_SETUP.md section 1-4."
        )
    if configured_token() is not None:
        return "info", (
            f"[admin-auth] {ADMIN_TOKEN_ENV} is set - all /admin/* and "
            f"/internal/* routes require the {ADMIN_TOKEN_HEADER} header."
        )
    return "warning", (
        f"[admin-auth] {ADMIN_TOKEN_ENV} is NOT set. "
        "POST /admin/scripts/code and POST /admin/auto-update/run-now are "
        "DISABLED (503) because they can execute code; the remaining /admin/* "
        f"routes stay open to anyone on the network. Set the {ADMIN_TOKEN_ENV} "
        "environment variable and restart to lock the admin surface. "
        "See docs/guide/DEPLOY_SETUP.md section 1-4."
    )
