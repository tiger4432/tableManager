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

The one permitted exception: the fingerprint
--------------------------------------------
That discipline had a cost nobody paid until an incident presented the bill. The
banner said only "is set", the 403 body echoed nothing, and the workers logged
only a status code - so when a chain worker started taking 403 on
``/internal/events/broadcast``, **nothing in the product could tell an operator
whether the two processes held the same token**, which is the only thing a 403
from this gate can mean. Reading the source was the only diagnosis available.

:func:`token_fingerprint` is therefore allowed out: the first
:data:`TOKEN_FINGERPRINT_CHARS` hex characters of ``sha256(token)``, logged by
the API server and by every daemon that presents the header. It is one-way, it is
identical on both sides of a matching pair, and it turns "are these the same
token?" into a glance. Nothing else about the value may ever be logged - not a
length, not a prefix, not a character class.
"""
import hashlib
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

#: How many hex characters of the digest a fingerprint shows.
#:
#: Truncation is not the security dial here, and it is worth being precise about
#: why, because the intuition runs backwards. Anyone who can read a log line can
#: test a guessed token offline against a digest of ANY length; a short prefix
#: only makes a hit ambiguous (one false positive per 2**32 candidates at eight
#: hex) where the full 64-character digest confirms a guess outright. Truncating
#: therefore makes the fingerprint a *weaker* oracle than the full digest, not a
#: stronger one. What actually bounds that attack is the token's own entropy - a
#: dictionary word is confirmable from four hex characters, and a 32-character
#: random string is not confirmable from sixty-four.
#:
#: So the length is chosen for the human comparing two log files, possibly over
#: the phone: eight is the commit-prefix length this project already reads all
#: day, and against the handful of distinct tokens a deployment plausibly holds
#: at once (the right one, a stale one, a typo) the collision risk is ~1e-8.
TOKEN_FINGERPRINT_CHARS = 8

#: Stand-ins for the two states that have no digest. Deliberately non-hex and
#: deliberately distinct from each other: an operator comparing fingerprints
#: across two logs must never see one side print nothing (is it unset, or did the
#: line not run?), and "set but unusable" has a different remedy from "unset" -
#: the variable is already there and must be *replaced*, not added.
FINGERPRINT_NONE = "none"
FINGERPRINT_UNUSABLE = "unusable-non-ascii"


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


def token_fingerprint():
    """A log-safe name for whatever token this process holds.

    Returns the first :data:`TOKEN_FINGERPRINT_CHARS` hex characters of
    ``sha256(token)``, or :data:`FINGERPRINT_NONE` / :data:`FINGERPRINT_UNUSABLE`
    for the two states with no token to digest.

    Two processes that print the same fingerprint hold the same token; two that
    print different ones were started from different environments, which is the
    only thing a 403 from this gate can mean. An operator can reproduce it from
    the value in their password manager without going near a log::

        python -c "import hashlib;print(hashlib.sha256(b'<token>').hexdigest()[:8])"

    Plain ``sha256`` with no salt or pepper, precisely so that command works. A
    domain-separated digest would cost nothing to compute and would resist
    published rainbow tables, but it would also make the fingerprint
    irreproducible without reading this file - and mid-incident, a diagnostic the
    operator cannot check independently is a diagnostic they will not trust. The
    protection against a rainbow-table lookup is a token with enough entropy to
    not be in one; see docs/guide/DEPLOY_SETUP.md section 1-4.
    """
    # Checked first: a non-ASCII token IS set, and reporting it as "none" would
    # send the operator to add a variable that is already there.
    if token_is_unusable():
        return FINGERPRINT_UNUSABLE
    token = configured_token()
    if token is None:
        return FINGERPRINT_NONE
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:TOKEN_FINGERPRINT_CHARS]


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
            f"characters (token fingerprint {FINGERPRINT_UNUSABLE}), which "
            "cannot survive an HTTP header round trip. It is "
            "being IGNORED - the admin surface is NOT locked, and the two "
            "code-execution routes are disabled (503). Re-set "
            f"{ADMIN_TOKEN_ENV} to an ASCII-only value and restart. "
            "See docs/guide/DEPLOY_SETUP.md section 1-4."
        )
    if configured_token() is not None:
        return "info", (
            f"[admin-auth] {ADMIN_TOKEN_ENV} is set "
            f"(token fingerprint {token_fingerprint()}) - all /admin/* and "
            f"/internal/* routes require the {ADMIN_TOKEN_HEADER} header. Every "
            "daemon must log the SAME fingerprint; a different one means that "
            "process was started from a different environment."
        )
    return "warning", (
        f"[admin-auth] {ADMIN_TOKEN_ENV} is NOT set "
        f"(token fingerprint {FINGERPRINT_NONE}). "
        "POST /admin/scripts/code, POST /admin/auto-update/run-now and "
        "POST /admin/retroactive/{op}/run are DISABLED (503) because they execute "
        "code or rewrite whole tables; the remaining /admin/* "
        f"routes stay open to anyone on the network. Set the {ADMIN_TOKEN_ENV} "
        "environment variable and restart to lock the admin surface. "
        "See docs/guide/DEPLOY_SETUP.md section 1-4."
    )


def worker_token_banner(process_label):
    """The line a daemon logs once at startup, as ``(level, message)``.

    The server's banner alone cannot answer the question an operator actually has
    - "do the two sides hold the same token?" - because one fingerprint is not a
    comparison. This is the other half of the pair, and it is emitted
    unconditionally rather than only on a failure for one reason: the state that
    hurts most is the *silent* one. A tree where nobody holds a token serves 200s
    on every ``/internal/events/*`` call while the deployment record says the
    admin surface is locked, and no failure ever arrives to prompt a look.
    """
    fingerprint = token_fingerprint()
    if fingerprint == FINGERPRINT_UNUSABLE:
        return "error", (
            f"[admin-auth] {process_label}: {ADMIN_TOKEN_ENV} is set but contains "
            f"NON-ASCII characters (token fingerprint {fingerprint}), so this "
            f"process can send NO {ADMIN_TOKEN_HEADER} at all - every "
            "/internal/events/* notification will be refused 401 by a locked API "
            "server and real-time propagation dies silently. Re-set "
            f"{ADMIN_TOKEN_ENV} to an ASCII-only value and restart the whole "
            "launcher tree. See docs/guide/DEPLOY_SETUP.md section 1-4."
        )
    if fingerprint == FINGERPRINT_NONE:
        return "warning", (
            f"[admin-auth] {process_label}: {ADMIN_TOKEN_ENV} is NOT set "
            f"(token fingerprint {fingerprint}), so no {ADMIN_TOKEN_HEADER} is "
            "sent on /internal/events/*. Correct ONLY if the API server's "
            f"startup banner also shows fingerprint {FINGERPRINT_NONE} - if it "
            "shows a hex fingerprint, every notification 401s and the grids go "
            "stale with nothing on screen to say so."
        )
    return "info", (
        f"[admin-auth] {process_label}: presenting {ADMIN_TOKEN_HEADER} on "
        f"/internal/events/* (token fingerprint {fingerprint}). The API server's "
        "[admin-auth] startup banner must show the SAME fingerprint."
    )


#: Statuses on an ``/internal/events/*`` POST that could plausibly be an auth
#: refusal, ours or someone else's. Everything else (500, 404, 502...) gets no
#: note, so an ordinary API failure does not grow an auth paragraph.
_AUTH_SHAPED_STATUSES = (401, 403, 407)

#: Headers that name whoever answered, when it was not us. ``Via`` is the hop
#: record RFC 9110 requires a proxy to add; ``Server`` is what most of them
#: volunteer anyway.
_UPSTREAM_ID_HEADERS = ("Server", "Via")

_HEADER_ECHO_LIMIT = 60


def _safe_header_echo(value):
    """A response header value, made safe to concatenate into a log line.

    Not our secret, but not our data either: it comes from whatever answered, so
    it is collapsed to printable ASCII on a single line and truncated. Without
    that, an upstream free to choose its own ``Server`` value can fold newlines
    into our worker log and write log lines of its own.
    """
    if not value:
        return ""
    text = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in str(value))
    text = " ".join(text.split())
    if len(text) > _HEADER_ECHO_LIMIT:
        text = text[:_HEADER_ECHO_LIMIT] + "..."
    return text


def internal_event_failure_note(status_code, response_headers=None):
    """One line naming WHO refused an ``/internal/events/*`` POST, and the fix.

    Returns ``None`` when the status cannot be an auth refusal.

    The discriminator is :data:`GATE_CHALLENGE_HEADER`, which :func:`_enforce`
    attaches to every rejection the gate itself produces. Its presence means this
    application refused and the remedy is about tokens; **its absence on a 4xx
    means something in front of FastAPI refused, and no amount of restarting or
    re-tokening will fix it.** Those are two different incident classes, and until
    this function existed the workers logged a bare status code that could not
    tell them apart - the discriminator was built, sent, and then thrown away at
    the one place with a use for it.

    That is not hypothetical. A production chain worker took repeated 403s on
    ``POST /internal/events/broadcast``; the gate cannot answer 403 to a request
    with no header (it answers 401), so the refusal was upstream all along, and
    establishing that took source reading and git archaeology instead of one
    glance at a log line.
    """
    if status_code not in _AUTH_SHAPED_STATUSES:
        return None

    challenge = None
    if response_headers is not None:
        try:
            challenge = response_headers.get(GATE_CHALLENGE_HEADER)
        except Exception:
            challenge = None

    # Compared case-insensitively against the exact constant the gate sends: a
    # proxy's own `WWW-Authenticate: Basic realm=...` must NOT read as ours.
    ours = bool(challenge) and challenge.strip().lower() == ADMIN_TOKEN_HEADER.lower()

    if not ours:
        seen = []
        if challenge:
            seen.append(f"{GATE_CHALLENGE_HEADER}: {_safe_header_echo(challenge)}")
        for name in _UPSTREAM_ID_HEADERS:
            value = None
            if response_headers is not None:
                try:
                    value = response_headers.get(name)
                except Exception:
                    value = None
            if value:
                seen.append(f"{name}: {_safe_header_echo(value)}")
        detail = f" [{'; '.join(seen)}]" if seen else ""
        return (
            f"admin-gate=no{detail} | NOT AN ADMIN-TOKEN FAILURE: the response "
            f"carries no '{GATE_CHALLENGE_HEADER}: {ADMIN_TOKEN_HEADER}', which "
            f"this server attaches to every {status_code} its own gate produces - "
            "so something in FRONT of the API refused (reverse proxy blocking "
            "/internal/*, host firewall, security agent, or another process bound "
            "to the API_BASE_URL port). REMEDY: check what owns that port and "
            "whether it filters /internal/* - restarting processes and re-setting "
            f"{ADMIN_TOKEN_ENV} cannot fix this."
        )

    fingerprint = token_fingerprint()

    if status_code == 403:
        return (
            f"admin-gate=yes token-fingerprint={fingerprint} | REMEDY: the API "
            f"server holds a DIFFERENT {ADMIN_TOKEN_ENV} - compare this "
            "fingerprint with the server's [admin-auth] startup banner, then "
            "restart the WHOLE launcher tree from ONE shell (restarting the API "
            "alone is what splits the two environments in the first place)."
        )

    # 401 = the gate saw no header. Which of three things happened is decided by
    # what this process is holding, and all three have different remedies.
    if fingerprint == FINGERPRINT_UNUSABLE:
        return (
            f"admin-gate=yes token-fingerprint={fingerprint} | REMEDY: "
            f"{ADMIN_TOKEN_ENV} IS set here but is not ASCII, so no header could "
            "be sent. Re-set it to an ASCII-only value (do not just add it - it "
            "is already there) and restart the whole launcher tree."
        )
    if fingerprint != FINGERPRINT_NONE:
        return (
            f"admin-gate=yes token-fingerprint={fingerprint} | REMEDY: this "
            f"process DID send {ADMIN_TOKEN_HEADER} and the gate saw none, so it "
            "was stripped in transit - look for a reverse proxy or a redirect "
            "between this process and API_BASE_URL, not at the token."
        )
    return (
        f"admin-gate=yes token-fingerprint={fingerprint} | REMEDY: this process "
        f"sent no {ADMIN_TOKEN_HEADER} because {ADMIN_TOKEN_ENV} is unset in its "
        f"environment while the API server has one. Set {ADMIN_TOKEN_ENV} in the "
        "shell that starts run_decoupled_app.py and restart the whole tree - a "
        "worker cannot be given the variable after it has started."
    )
