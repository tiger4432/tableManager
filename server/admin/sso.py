"""Company sign-in over OIDC (lead 2095014ee, ADFS).

On only when auth_config.json says ``enabled`` and names the issuer, the client id and the return
address, the client secret is in the environment, and the return address is https - read once, at
start. Then every route but ``/auth/*``,
``/internal/*`` and ``/health`` needs a person, and the admin gate asks for a name on the admin
list instead of ``X-Admin-Token``. Sessions, login rounds and personal keys are server-side rows
holding digests, never secrets.
"""
import functools
import hashlib
import html
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.requests import HTTPConnection

import paths
from admin.auth import GATE_CHALLENGE_HEADER
from database import database, models
from database.crud import is_blank_value

logger = logging.getLogger("Server")

CONFIG_FILE = "auth_config.json"
CONFIG_PATH = paths.config_path(CONFIG_FILE)
#: The one secret stays in the environment: the snapshot tooling copies server/config/** into an
#: isolated data root, so a secret in the file would exist twice (admin/auth.py).
CLIENT_SECRET_ENV = "ASSY_OIDC_CLIENT_SECRET"
REQUIRED_CELLS = ("issuer", "client_id", "redirect_uri")
SCOPE = "openid"
SESSION_SECONDS = 12 * 3600
LOGIN_ROUND_SECONDS = 10 * 60
#: Leeway on the ID token's exp / iat / nbf - authlib's own default leeway for token expiry.
CLOCK_SKEW_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 10
ERROR_DESCRIPTION_CHARS = 200
COOKIE_NAME = "assy_session"
OPEN_PREFIXES = ("/auth/", "/internal/")
OPEN_PATHS = ("/health",)
#: What this gate's refusals name in WWW-Authenticate, as the token gate names X-Admin-Token.
SESSION_CHALLENGE = "Session"
_CHALLENGE = {GATE_CHALLENGE_HEADER: SESSION_CHALLENGE}

LOGIN_REQUIRED = {"reason": "login_required", "login": "/auth/login", "message": "Sign in to continue."}
ADMIN_REQUIRED = {"reason": "admin_required", "message": "This needs an administrator."}

router = APIRouter()


@functools.lru_cache(maxsize=None)
def settings():
    """Every sign-in setting, read in one place and once per process - a change waits for the
    restart (lead 10-07): auth_config.json and the client secret."""
    loaded = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            loaded = json.load(handle)
    cells = {name: loaded.get(name) for name in REQUIRED_CELLS + ("name_claim",)}
    cells = {name: None if is_blank_value(value) else str(value) for name, value in cells.items()}
    cells["enabled"] = loaded.get("enabled") is True
    cells["admins"] = [str(name) for name in loaded.get("admins") or []]
    secret = os.environ.get(CLIENT_SECRET_ENV)
    cells["client_secret"] = None if is_blank_value(secret) else secret.strip()
    return cells


def off_reason():
    """Why sign-in is off, as one sentence naming only the missing cells, or None when it is on."""
    cells = settings()
    if not cells["enabled"]:
        return "enabled is not true in %s" % CONFIG_FILE
    missing = ["%s (%s)" % (name, CONFIG_FILE) for name in REQUIRED_CELLS if cells[name] is None]
    if cells["client_secret"] is None:
        missing.append(CLIENT_SECRET_ENV)
    if missing:
        return "enabled is true but not set: " + ", ".join(missing)
    if not cells["redirect_uri"].lower().startswith("https://"):
        return ("redirect_uri (%s) is not an https address - the session cookie is Secure, so a "
                "browser on http would never send it back" % CONFIG_FILE)
    return None


def enabled():
    return off_reason() is None


def startup_banner():
    """``(level, message)`` the server logs once at startup."""
    reason = off_reason()
    if reason is None:
        return "info", ("[sso] ON - issuer %s, return address %s. Every route but /auth/*, "
                        "/internal/* and /health needs a signed-in person; admin routes need a name "
                        "on the admin list." % (settings()["issuer"], settings()["redirect_uri"]))
    level = "info" if reason.startswith("enabled is not true") else "warning"
    return level, "[sso] OFF - %s. Sign-in is not required." % reason


def _digest(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _now():
    return int(time.time())


def _iso(seconds):
    return None if seconds is None else datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def identify(connection: HTTPConnection):
    """The signed-in person's name from the session cookie or a personal key, else None."""
    cookie = connection.cookies.get(COOKIE_NAME)
    bearer = connection.headers.get("authorization") or ""
    key = bearer[7:].strip() if bearer[:7].lower() == "bearer " else ""
    if not cookie and not key:
        return None
    with database.SessionLocal() as db:
        if cookie:
            row = db.get(models.AuthSession, _digest(cookie))
            if row is not None and row.expires_at > _now():
                return row.user_name
        if key:
            row = db.query(models.AuthApiKey).filter_by(key_hash=_digest(key)).first()
            if row is not None:
                name = row.user_name
                row.last_used_at = _now()
                db.commit()
                return name
    return None




def admit(request: Request):
    """The login door, while sign-in is on: finish a sign-in coming back to the return address,
    remember who this is, and answer for them when they must sign in first."""
    query = request.query_params
    if (request.url.path == urlsplit(settings()["redirect_uri"]).path and query.get("state")
            and (query.get("code") or query.get("error"))):
        return _returned(query)
    request.state.sso_user = identify(request)
    path = request.url.path
    if request.state.sso_user is not None or path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return None
    if request.method == "GET" and "text/html" in (request.headers.get("accept") or ""):
        here = path + ("?" + request.url.query if request.url.query else "")
        return RedirectResponse("/auth/login?next=" + quote(here, safe=""), status_code=302)
    return JSONResponse(status_code=401, content={"detail": LOGIN_REQUIRED}, headers=dict(_CHALLENGE))


def who(request: Request, fallback):
    """Who did this: the signed-in name, else the seat's own answer as before - sign-in off, or an
    open path with nobody signed in (lead 10-07 ㄱ)."""
    user = getattr(request.state, "sso_user", None)
    return fallback if user is None else user


def _person(request: Request):
    user = getattr(request.state, "sso_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail=LOGIN_REQUIRED, headers=dict(_CHALLENGE))
    return user


def require_admin(request: Request):
    if _person(request) not in settings()["admins"]:
        raise HTTPException(status_code=403, detail=ADMIN_REQUIRED, headers=dict(_CHALLENGE))


def _same_origin_path(target):
    if not target.startswith("/") or target.startswith("/\\"):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


def _get_json(address):
    import requests

    answer = requests.get(address, timeout=HTTP_TIMEOUT_SECONDS)
    answer.raise_for_status()
    return answer.json()


def _discovery():
    return _get_json(settings()["issuer"].rstrip("/") + "/.well-known/openid-configuration")


def _client():
    from authlib.integrations.requests_client import OAuth2Session

    cells = settings()
    return OAuth2Session(cells["client_id"], cells["client_secret"], scope=SCOPE,
                         redirect_uri=cells["redirect_uri"], code_challenge_method="S256")


def _verified_claims(id_token, meta, nonce):
    """The ID token's claims once its signature, issuer, audience, expiry and nonce hold. A kid the
    keys do not hold reads the keys once more - the issuer rotates its signing certificate."""
    from joserfc import jwt
    from joserfc.errors import InvalidKeyIdError
    from joserfc.jwk import KeySet

    algorithms = meta.get("id_token_signing_alg_values_supported") or ["RS256"]
    try:
        token = jwt.decode(id_token, KeySet.import_key_set(_get_json(meta["jwks_uri"])), algorithms)
    except InvalidKeyIdError:
        token = jwt.decode(id_token, KeySet.import_key_set(_get_json(meta["jwks_uri"])), algorithms)
    jwt.JWTClaimsRegistry(leeway=CLOCK_SKEW_SECONDS,
                          iss={"essential": True, "value": meta["issuer"]},
                          aud={"essential": True, "value": settings()["client_id"]},
                          exp={"essential": True},
                          nonce={"essential": True, "value": nonce}).validate(token.claims)
    return token.claims


def _refused(status, sentence):
    """Every sign-in refusal: one sentence, logged as said, and one way on. No automatic move."""
    logger.warning("[sso] %s", sentence)
    return HTMLResponse(status_code=status, content=(
        '<!doctype html><title>Sign-in refused</title><p>%s</p><p><a href="/auth/login">Try again</a></p>'
        % html.escape(sentence, quote=False)))


def _sweep(db):
    """A login round leaves by its return; one that never returned, and expired sessions, leave here."""
    now = _now()
    db.query(models.AuthLoginRound).filter(
        models.AuthLoginRound.created_at < now - LOGIN_ROUND_SECONDS).delete(synchronize_session=False)
    db.query(models.AuthSession).filter(
        models.AuthSession.expires_at <= now).delete(synchronize_session=False)


def _returned(query):
    """The issuer sent the browser back: spend the login round, then open a session or refuse."""
    with database.SessionLocal() as db:
        row = db.get(models.AuthLoginRound, query["state"])
        round_ = None if row is None else (row.nonce, row.code_verifier, row.next_path, row.created_at)
        if row is not None:
            db.delete(row)
            db.commit()
    if round_ is None or round_[3] < _now() - LOGIN_ROUND_SECONDS:
        return _refused(400, "This sign-in has expired or was already used.")
    if query.get("error"):
        description = query.get("error_description") or ""
        if len(description) > ERROR_DESCRIPTION_CHARS:
            description = description[:ERROR_DESCRIPTION_CHARS] + "..."
        return _refused(400, "The identity provider refused the sign-in: %s%s" % (
            query["error"], (" - " + description) if description else ""))
    nonce, verifier, next_path, _created = round_
    try:
        meta = _discovery()
        token = _client().fetch_token(meta["token_endpoint"], code=query["code"], code_verifier=verifier)
        claims = _verified_claims(token.get("id_token") or "", meta, nonce)
    except Exception as exc:
        return _refused(401, "Sign-in refused: the ID token did not verify (%s)." % type(exc).__name__)
    name_claim = settings()["name_claim"]
    name = None if name_claim is None else claims.get(name_claim)
    if is_blank_value(name) or not isinstance(name, str):
        return _refused(403, "Sign-in refused: name_claim in %s is %r, and the ID token has no such "
                             "claim. Claims in the token: %s."
                        % (CONFIG_FILE, name_claim or "", ", ".join(sorted(claims))))
    secret = secrets.token_urlsafe(32)
    now = _now()
    with database.SessionLocal() as db:
        db.add(models.AuthSession(id_hash=_digest(secret), user_name=name, created_at=now,
                                  expires_at=now + SESSION_SECONDS))
        db.commit()
    response = RedirectResponse(next_path, status_code=302)
    response.set_cookie(COOKIE_NAME, secret, max_age=SESSION_SECONDS, path="/", secure=True,
                        httponly=True, samesite="lax")
    return response


def _require_on():
    if not enabled():
        raise HTTPException(status_code=404, detail="Sign-in is not set up on this server.")


@router.get("/auth/login")
def login(next: str = "/"):
    _require_on()
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    meta = _discovery()
    with database.SessionLocal() as db:
        _sweep(db)
        db.add(models.AuthLoginRound(state=state, nonce=nonce, code_verifier=verifier,
                                     next_path=next if _same_origin_path(next) else "/",
                                     created_at=_now()))
        db.commit()
    address, _ = _client().create_authorization_url(
        meta["authorization_endpoint"], state=state, code_verifier=verifier, nonce=nonce)
    return RedirectResponse(address, status_code=302)


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    _require_on()
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        with database.SessionLocal() as db:
            db.query(models.AuthSession).filter_by(id_hash=_digest(cookie)).delete()
            db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/auth/me")
def me(request: Request):
    if not enabled():
        return {"user": None, "is_admin": None, "sso": False}
    user = getattr(request.state, "sso_user", None)
    return {"user": user, "is_admin": user is not None and user in settings()["admins"], "sso": True}


def _key_answer(row):
    return {"id": row.id, "name": row.name, "created_at": _iso(row.created_at)}


@router.post("/auth/keys", status_code=201)
def create_key(request: Request, payload: dict = Body(...)):
    _require_on()
    user = _person(request)
    name = payload.get("name")
    if is_blank_value(name):
        raise HTTPException(status_code=422, detail={
            "reason": "key_name_required", "message": "Give the key a name."})
    name = str(name).strip()
    secret = secrets.token_urlsafe(32)
    with database.SessionLocal() as db:
        if db.query(models.AuthApiKey).filter_by(user_name=user, name=name).first() is not None:
            raise HTTPException(status_code=409, detail={
                "reason": "key_name_taken", "message": 'You already have a key named "%s".' % name})
        row = models.AuthApiKey(id=uuid.uuid4().hex, user_name=user, name=name,
                                key_hash=_digest(secret), created_at=_now())
        db.add(row)
        db.commit()
        return dict(_key_answer(row), key=secret)


@router.get("/auth/keys")
def list_keys(request: Request):
    _require_on()
    user = _person(request)
    with database.SessionLocal() as db:
        rows = db.query(models.AuthApiKey).filter_by(user_name=user).order_by(
            models.AuthApiKey.created_at).all()
        return [dict(_key_answer(row), last_used_at=_iso(row.last_used_at)) for row in rows]


@router.delete("/auth/keys/{key_id}", status_code=204)
def delete_key(key_id: str, request: Request):
    _require_on()
    user = _person(request)
    with database.SessionLocal() as db:
        gone = db.query(models.AuthApiKey).filter_by(id=key_id, user_name=user).delete()
        db.commit()
    if not gone:
        raise HTTPException(status_code=404, detail={
            "reason": "key_unknown", "message": "No key of yours has that id."})
    return Response(status_code=204)
