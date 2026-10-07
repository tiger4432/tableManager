# -*- coding: utf-8 -*-
"""총괄 2095014ee + 10-07 판정: company sign-in over OIDC (ADFS). A fake issuer answers every HTTP
call - `requests.Session.send` is replaced before a request can leave, and an address it does not
serve fails the test. The settings file is a temp file; sessions and keys live in the suite's
in-memory database."""
import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit

import pytest
import requests
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import OctKey, RSAKey
from starlette.websockets import WebSocketDisconnect

import main
from admin import auth, sso
from database import database, models

ISSUER = "https://adfs.example.test/adfs"
CLIENT_ID = "assy-client"
CLIENT_SECRET = "client-secret"
RETURNS = ("https://testserver/auth/callback", "https://testserver/")
JWKS = ISSUER + "/discovery/keys"
TOKEN = ISSUER + "/oauth2/token"
AUTHORIZE = ISSUER + "/oauth2/authorize"
UPN = "kim@corp.test"
ADFS_CLAIMS = {"upn": UPN, "unique_name": "CORP\\kim", "sub": "s-kim"}
ADMIN_TOKEN = "worker-token-for-tests"
CHALLENGE = auth.GATE_CHALLENGE_HEADER
HEALTH_KEYS = {"status", "checked_at", "problems", "checks"}
HEALTH_CHECKS = {"database", "workers", "outbox", "supervisor", "config_backup"}


class FakeIssuer:
    def __init__(self, returns):
        self.returns = returns
        self.keys = {"k1": RSAKey.generate_key(2048, parameters={"kid": "k1"})}
        self.published = [["k1"]]          # one entry per JWKS read; the last repeats
        self.signing = "k1"
        self.claims = dict(ADFS_CLAIMS)
        self.overrides = {}
        self.algorithms = ["RS256"]           # what discovery lists
        self.forge = None                      # "none" | "HS256": the token the issuer hands back
        self.secret_key = OctKey.import_key("s" * 32, parameters={"kid": "k-oct"})
        self.codes = {}
        self.answered = []

    def key(self, kid):
        return self.keys.setdefault(kid, RSAKey.generate_key(2048, parameters={"kid": kid}))

    def authorize(self, location):
        assert location.startswith(AUTHORIZE + "?")
        query = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        assert (query["client_id"], query["redirect_uri"], query["scope"], query["code_challenge_method"]) == (
            CLIENT_ID, self.returns, sso.SCOPE, "S256")
        code = secrets.token_urlsafe(8)
        self.codes[code] = (query["code_challenge"], query["nonce"])
        return code, query["state"]

    def _answer(self, request, status, body):
        answer = requests.Response()
        answer.status_code = status
        answer.headers["Content-Type"] = "application/json"
        answer._content = json.dumps(body).encode()
        answer.url = request.url
        answer.request = request
        return answer

    def send(self, _session, request, **_kw):
        address = request.url
        self.answered.append(address)
        if address == ISSUER + "/.well-known/openid-configuration":
            return self._answer(request, 200, {
                "issuer": ISSUER, "authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN,
                "jwks_uri": JWKS, "id_token_signing_alg_values_supported": self.algorithms})
        if address == JWKS:
            kids = self.published.pop(0) if len(self.published) > 1 else self.published[0]
            keys = [self.key(k).as_dict(private=False) for k in kids]
            if self.forge == "HS256":
                keys.append(self.secret_key.as_dict())      # a symmetric key in the published set
            return self._answer(request, 200, {"keys": keys})
        if address == TOKEN:
            form = {k: v[0] for k, v in parse_qs(request.body).items()}
            basic = base64.b64encode(("%s:%s" % (CLIENT_ID, CLIENT_SECRET)).encode()).decode()
            challenge, nonce = self.codes.pop(form["code"])
            proof = base64.urlsafe_b64encode(
                hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            if (request.headers.get("Authorization") != "Basic " + basic or proof != challenge
                    or form["redirect_uri"] != self.returns):
                return self._answer(request, 400, {"error": "invalid_grant"})
            now = int(time.time())
            claims = dict({"iss": ISSUER, "aud": CLIENT_ID, "iat": now, "exp": now + 3600,
                           "nonce": nonce}, **self.claims)
            claims.update(self.overrides)
            if self.forge == "none":
                id_token = ".".join(base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()
                                    for part in ({"alg": "none", "kid": "k1"}, claims)) + "."
            elif self.forge == "HS256":
                id_token = jwt.encode({"alg": "HS256", "kid": "k-oct"}, claims, self.secret_key)
            else:
                id_token = jwt.encode({"alg": "RS256", "kid": self.signing}, claims, self.key(self.signing))
            return self._answer(request, 200, {"access_token": "at", "token_type": "Bearer",
                                               "expires_in": 3600, "id_token": id_token})
        raise AssertionError("the fake issuer does not serve %s" % address)


def _clear():
    with database.SessionLocal() as db:
        for model in (models.AuthSession, models.AuthLoginRound, models.AuthApiKey):
            db.query(model).delete()
        db.commit()


def _setup(monkeypatch, tmp_path, returns, **cells):
    fake = FakeIssuer(returns)
    monkeypatch.setattr(requests.Session, "send",
                        lambda session, request, **kw: fake.send(session, request, **kw))
    monkeypatch.setenv(sso.CLIENT_SECRET_ENV, CLIENT_SECRET)
    monkeypatch.setenv(auth.ADMIN_TOKEN_ENV, ADMIN_TOKEN)
    path = tmp_path / sso.CONFIG_FILE
    monkeypatch.setattr(sso, "CONFIG_PATH", str(path))
    written = {"enabled": True, "issuer": ISSUER, "client_id": CLIENT_ID, "redirect_uri": returns,
               "name_claim": "upn", "admins": []}

    def config(**changes):
        written.update(changes)
        path.write_text(json.dumps(written), encoding="utf-8")
        sso.settings.cache_clear()
    fake.config = config
    config(**cells)
    _clear()
    return fake


@pytest.fixture(params=RETURNS)
def issuer(request, monkeypatch, tmp_path):
    yield _setup(monkeypatch, tmp_path, request.param)
    sso.settings.cache_clear()
    _clear()


@pytest.fixture
def off(monkeypatch, tmp_path):
    monkeypatch.setattr(sso, "CONFIG_PATH", str(tmp_path / "absent.json"))
    monkeypatch.delenv(sso.CLIENT_SECRET_ENV, raising=False)
    monkeypatch.setenv(auth.ADMIN_TOKEN_ENV, ADMIN_TOKEN)
    sso.settings.cache_clear()
    yield
    sso.settings.cache_clear()


def _client():
    return TestClient(main.app, base_url="https://testserver")


def _back(client, fake, **query):
    return client.get(urlsplit(fake.returns).path, params=query, follow_redirects=False)


def _sign_in(client, fake, next_path="/"):
    started = client.get("/auth/login", params={"next": next_path}, follow_redirects=False)
    assert started.status_code == 302
    code, state = fake.authorize(started.headers["location"])
    return _back(client, fake, code=code, state=state)


def _session_rows():
    with database.SessionLocal() as db:
        return [(row.id_hash, row.user_name, row.expires_at - row.created_at)
                for row in db.query(models.AuthSession).all()]


def _rounds():
    with database.SessionLocal() as db:
        return db.query(models.AuthLoginRound).count()


# --- the switch: enabled x (the rest all there / some missing), and a return that is not https --

@pytest.mark.parametrize("enabled, drop, level, words", [
    (True, None, "info", None),
    (True, "secret", "warning", "enabled is true but not set: " + sso.CLIENT_SECRET_ENV),
    (True, "client_id", "warning", "enabled is true but not set: client_id (%s)" % sso.CONFIG_FILE),
    (False, None, "info", "enabled is not true"),
    (False, "secret", "info", "enabled is not true"),
    (True, "http", "warning", "redirect_uri (%s) is not an https address" % sso.CONFIG_FILE),
])
def test_sign_in_is_on_only_when_enabled_and_every_setting_is_there(monkeypatch, tmp_path,
                                                                     enabled, drop, level, words):
    fake = _setup(monkeypatch, tmp_path, RETURNS[0], enabled=enabled)
    if drop == "secret":
        monkeypatch.delenv(sso.CLIENT_SECRET_ENV)
    elif drop == "client_id":
        fake.config(client_id="  ")
    elif drop == "http":
        fake.config(redirect_uri="http://testserver/auth/callback")
    sso.settings.cache_clear()
    said = sso.startup_banner()
    assert said[0] == level
    if words is None:
        assert said[1].startswith("[sso] ON") and ISSUER in said[1] and RETURNS[0] in said[1]
        assert _client().get("/auth/me").json() == {"user": None, "is_admin": False, "sso": True}
    else:
        assert said[1].startswith("[sso] OFF") and words in said[1] and CLIENT_SECRET not in said[1]
        assert _client().get("/auth/me").json() == {"user": None, "is_admin": None, "sso": False}
    assert fake.answered == []
    sso.settings.cache_clear()


def test_a_change_waits_for_the_restart(issuer):
    assert sso.enabled()
    with open(sso.CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump({"enabled": False}, handle)
    assert sso.enabled()                                          # read once per process
    sso.settings.cache_clear()
    assert not sso.enabled()


def test_off_never_says_login_required_and_the_admin_token_still_rules(off):
    client = _client()
    answers = [client.get("/admin/chain/pause"),
               client.get("/admin/chain/pause", headers={auth.ADMIN_TOKEN_HEADER: "wrong"}),
               client.get("/admin/chain/pause", headers={auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN}),
               client.get("/auth/me"), client.get("/auth/keys"), client.get("/auth/login"),
               client.get("/admin", headers={"Accept": "text/html"}, follow_redirects=False)]
    assert [answers[0].status_code, answers[0].headers[CHALLENGE]] == [401, auth.ADMIN_TOKEN_HEADER]
    assert [answers[1].status_code, answers[1].headers[CHALLENGE]] == [403, auth.ADMIN_TOKEN_HEADER]
    assert answers[2].status_code == 200
    assert answers[4].status_code == 404 and answers[5].status_code == 404
    assert all("login_required" not in answer.text for answer in answers)
    with client.websocket_connect("/ws"):
        pass


# --- before signing in --------------------------------------------------------------------------

def test_an_api_call_is_refused_and_a_page_is_sent_to_sign_in(issuer):
    client = _client()
    for route in ("/tables", "/admin/chain/pause"):          # the door alone · the door and the gate
        api = client.get(route, headers={auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN})
        assert (api.status_code, api.json(), api.headers[CHALLENGE]) == (
            401, {"detail": sso.LOGIN_REQUIRED}, sso.SESSION_CHALLENGE), route
    page = client.get("/admin?tab=1", headers={"Accept": "text/html"}, follow_redirects=False)
    assert page.status_code == 302 and page.headers["location"] == "/auth/login?next=" + quote(
        "/admin?tab=1", safe="")
    heard = {}

    def listen(socket):
        try:
            socket.receive_text()
        except WebSocketDisconnect as closed:
            heard["closed"] = (closed.code, closed.reason)
    with client.websocket_connect("/ws") as socket:
        listener = threading.Thread(target=listen, args=(socket,), daemon=True)
        listener.start()
        listener.join(5)                      # a socket left open must fail here, not hang
    assert heard.get("closed") == (4401, "login_required")


def test_health_answers_without_signing_in_and_carries_no_table_data(issuer):
    answer = _client().get("/health")
    assert answer.status_code in (200, 503)
    assert set(answer.json()) == HEALTH_KEYS and set(answer.json()["checks"]) == HEALTH_CHECKS


def test_workers_keep_their_token_on_internal(issuer):
    client = _client()
    body = {"event_type": "noop", "payload": {}}
    refused = client.post("/internal/events/broadcast", json=body)
    assert (refused.status_code, refused.headers[CHALLENGE]) == (401, auth.ADMIN_TOKEN_HEADER)
    assert client.post("/internal/events/broadcast", json=body,
                       headers={auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN}).status_code == 200


# --- signing in, at either return address ------------------------------------------------------

def test_signing_in_opens_a_server_side_session_with_a_secure_cookie(issuer):
    client = _client()
    back = _sign_in(client, issuer, "/admin#ontology")
    assert back.status_code == 302 and back.headers["location"] == "/admin#ontology"
    cookie = back.headers["set-cookie"]
    for part in ("%s=" % sso.COOKIE_NAME, "Secure", "HttpOnly", "SameSite=lax", "Path=/",
                 "Max-Age=%d" % sso.SESSION_SECONDS):
        assert part in cookie, part
    secret = client.cookies.get(sso.COOKIE_NAME)
    assert _session_rows() == [(hashlib.sha256(secret.encode()).hexdigest(), UPN, sso.SESSION_SECONDS)]
    assert _rounds() == 0
    assert client.get("/auth/me").json() == {"user": UPN, "is_admin": False, "sso": True}
    assert {JWKS, TOKEN} <= set(issuer.answered)


def test_the_return_address_without_code_or_error_is_the_screen_it_always_was(issuer, monkeypatch):
    client = _client()
    _sign_in(client, issuer)
    path = urlsplit(issuer.returns).path
    signed_in = client.get(path, params={"state": "s"}, follow_redirects=False)
    monkeypatch.setattr(sso, "CONFIG_PATH", sso.CONFIG_PATH + ".absent")
    sso.settings.cache_clear()
    today = _client().get(path, params={"state": "s"}, follow_redirects=False)
    assert (signed_in.status_code, signed_in.content) == (today.status_code, today.content)


def test_a_next_that_leaves_the_server_comes_back_to_the_root(issuer):
    for target in ("//evil.test/x", "https://evil.test/x", "/\\evil.test", "admin"):
        assert _sign_in(_client(), issuer, target).headers["location"] == "/"


@pytest.mark.parametrize("override", [
    {"aud": "someone-else"}, {"iss": "https://other.test/adfs"}, {"nonce": "replayed"},
    {"exp": "PAST"}, {"signing": "forged"},
])
def test_a_token_that_does_not_verify_opens_no_session(issuer, override):
    if "signing" in override:
        issuer.keys["forged"] = RSAKey.generate_key(2048, parameters={"kid": "k1"})
        issuer.signing = "forged"
    elif override.get("exp") == "PAST":
        issuer.overrides["exp"] = int(time.time()) - sso.CLOCK_SKEW_SECONDS - 30
    else:
        issuer.overrides.update(override)
    back = _sign_in(_client(), issuer)
    assert back.status_code == 401 and "did not verify" in back.text and "Try again" in back.text
    assert _session_rows() == []


def test_a_clock_a_little_behind_is_forgiven(issuer):
    issuer.overrides["exp"] = int(time.time()) - 30           # thirty seconds: inside the leeway
    assert _sign_in(_client(), issuer).status_code == 302 and len(_session_rows()) == 1


@pytest.mark.parametrize("answer", ["code", "error"])
def test_a_state_the_server_does_not_hold_is_refused_alike(issuer, answer):
    back = _back(_client(), issuer, state="never-issued", **{answer: "x"})
    assert back.status_code == 400 and "expired or was already used" in back.text
    assert "location" not in back.headers and _session_rows() == []


def test_a_login_round_is_spent_once(issuer):
    client = _client()
    started = client.get("/auth/login", follow_redirects=False)
    code, state = issuer.authorize(started.headers["location"])
    assert _back(client, issuer, code=code, state=state).status_code == 302
    again = _back(client, issuer, code=code, state=state)
    assert again.status_code == 400 and "expired or was already used" in again.text


def test_the_issuer_refusing_shows_why_and_moves_nowhere(issuer, caplog):
    client = _client()
    started = client.get("/auth/login", follow_redirects=False)
    _code, state = issuer.authorize(started.headers["location"])
    with caplog.at_level(logging.WARNING, logger="Server"):
        back = _back(client, issuer, state=state, error="<b>access_denied</b>",
                     error_description="d" * (sso.ERROR_DESCRIPTION_CHARS + 50))
    assert back.status_code == 400 and "location" not in back.headers and "refresh" not in back.text.lower()
    assert "&lt;b&gt;access_denied&lt;/b&gt;" in back.text and "<b>access" not in back.text
    assert "d" * sso.ERROR_DESCRIPTION_CHARS + "..." in back.text
    assert "d" * (sso.ERROR_DESCRIPTION_CHARS + 1) not in back.text
    assert '<a href="/auth/login">Try again</a>' in back.text
    assert any("access_denied" in record.getMessage() for record in caplog.records)
    assert _rounds() == 0 and _session_rows() == []


# --- ADFS: the name claim ----------------------------------------------------------------------

@pytest.mark.parametrize("name_claim", ["email", ""])
def test_a_name_claim_the_token_lacks_refuses_and_names_what_the_token_has(issuer, caplog, name_claim):
    issuer.config(name_claim=name_claim)
    with caplog.at_level(logging.WARNING, logger="Server"):
        back = _sign_in(_client(), issuer)
    assert back.status_code == 403
    assert repr(name_claim) in back.text and all(claim in back.text for claim in ADFS_CLAIMS)
    assert all(value not in back.text for value in (UPN, "kim", "s-kim"))
    assert any(repr(name_claim) in record.getMessage() for record in caplog.records)
    assert _session_rows() == []


# --- the issuer rotates its signing key --------------------------------------------------------

def test_a_kid_the_keys_lack_reads_the_keys_once_more(issuer):
    issuer.published = [["k1"], ["k1", "k2"]]
    issuer.signing = "k2"
    assert _sign_in(_client(), issuer).status_code == 302
    assert issuer.answered.count(JWKS) == 2


@pytest.mark.parametrize("forged", ["none", "HS256"])
def test_an_unsigned_or_symmetric_token_is_refused_whatever_discovery_lists(issuer, forged):
    """총괄 10-07: joserfc takes `none`, or HS256 against a symmetric key in the set, when the
    caller lists them - so the list discovery hands over is cut to asymmetric families."""
    issuer.algorithms = ["none", "HS256"]
    issuer.forge = forged
    back = _sign_in(_client(), issuer)
    assert back.status_code == 401 and _session_rows() == []


def test_a_kid_the_issuer_never_published_is_refused_after_one_more_read(issuer):
    issuer.signing = "k9"
    back = _sign_in(_client(), issuer)
    assert back.status_code == 401 and _session_rows() == []
    assert issuer.answered.count(JWKS) == 2


# --- admins ------------------------------------------------------------------------------------

def test_admin_routes_want_a_name_on_the_list_and_not_the_token(issuer):
    spelled = "Kim@Corp.Test"                             # the token's spelling is what is kept
    issuer.claims["upn"] = spelled
    client = _client()
    _sign_in(client, issuer)
    refused = client.get("/admin/chain/pause", headers={auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN})
    assert (refused.status_code, refused.json(), refused.headers[CHALLENGE]) == (
        403, {"detail": sso.ADMIN_REQUIRED}, sso.SESSION_CHALLENGE)
    issuer.config(admins=[spelled.upper()])              # AD reads a upn in any case (총괄 10-07)
    assert client.get("/admin/chain/pause").status_code == 200
    assert client.get("/auth/me").json() == {"user": spelled, "is_admin": True, "sso": True}


# --- leaving -----------------------------------------------------------------------------------

def test_signing_out_ends_the_session(issuer):
    client = _client()
    _sign_in(client, issuer)
    assert client.post("/auth/logout").status_code == 204
    assert _session_rows() == []
    assert client.get("/auth/keys").status_code == 401


def test_a_session_past_its_hours_is_no_one(issuer):
    client = _client()
    _sign_in(client, issuer)
    with database.SessionLocal() as db:
        db.query(models.AuthSession).update({"expires_at": int(time.time()) - 1})
        db.commit()
    assert client.get("/auth/me").json()["user"] is None


def test_a_new_login_sweeps_stale_rounds_and_expired_sessions(issuer):
    now = int(time.time())
    with database.SessionLocal() as db:
        db.add(models.AuthSession(id_hash="old", user_name="x", created_at=now - 99999, expires_at=now - 1))
        db.add(models.AuthSession(id_hash="live", user_name="y", created_at=now, expires_at=now + 60))
        db.add(models.AuthLoginRound(state="stale", nonce="n", code_verifier="v", next_path="/",
                                     created_at=now - sso.LOGIN_ROUND_SECONDS - 1))
        db.commit()
    _client().get("/auth/login", follow_redirects=False)
    with database.SessionLocal() as db:
        assert [r.id_hash for r in db.query(models.AuthSession).all()] == ["live"]
        assert db.get(models.AuthLoginRound, "stale") is None
    assert _rounds() == 1


# --- personal keys -----------------------------------------------------------------------------

def test_a_personal_key_speaks_for_its_owner_until_deleted(issuer):
    client = _client()
    _sign_in(client, issuer)
    made = client.post("/auth/keys", json={"name": "nightly"})
    assert made.status_code == 201 and set(made.json()) == {"id", "name", "key", "created_at"}
    key = made.json()["key"]
    with database.SessionLocal() as db:
        assert [r.key_hash for r in db.query(models.AuthApiKey).all()] == [
            hashlib.sha256(key.encode()).hexdigest()]
    script, bearer = _client(), {"Authorization": "Bearer " + key}
    assert script.get("/auth/me", headers=bearer).json()["user"] == UPN
    listed = client.get("/auth/keys").json()
    assert [k["name"] for k in listed] == ["nightly"] and listed[0]["last_used_at"] is not None
    assert "key" not in listed[0]
    taken = client.post("/auth/keys", json={"name": "nightly"})
    assert (taken.status_code, taken.json()["detail"]["reason"]) == (409, "key_name_taken")
    blank = client.post("/auth/keys", json={"name": "  "})
    assert (blank.status_code, blank.json()["detail"]["reason"]) == (422, "key_name_required")
    assert client.delete("/auth/keys/" + made.json()["id"]).status_code == 204
    assert script.get("/auth/me", headers=bearer).json()["user"] is None


def test_a_key_is_deleted_only_by_its_owner(issuer):
    owner = _client()
    _sign_in(owner, issuer)
    key_id = owner.post("/auth/keys", json={"name": "mine"}).json()["id"]
    issuer.claims["upn"] = "lee@corp.test"
    other = _client()
    _sign_in(other, issuer)
    assert other.delete("/auth/keys/" + key_id).status_code == 404
    assert [k["id"] for k in owner.get("/auth/keys").json()] == [key_id]


# --- who did this: five seats x (on, off), and the three open paths while on -------------------

SPOOF = {"X-User": "spoof"}


class _Recorder:
    def __init__(self, real):
        self.real, self.values = real, []

    def set(self, value):
        self.values.append(value)
        return self.real.set(value)

    def reset(self, token):
        return self.real.reset(token)


@pytest.fixture
def seats(monkeypatch, tmp_path):
    from chain import control as chain_control
    from ledger import schema

    heard = {"world": []}
    recorder = _Recorder(main.request_user)
    monkeypatch.setattr(main, "request_user", recorder)
    monkeypatch.setattr(chain_control, "pause_now",
                        lambda db, by, reason: heard.__setitem__("pause", by) or {"by": by})

    def refuse(*args):
        heard["world"].append(args[-1])
        raise LookupError("stub")
    monkeypatch.setattr(schema, "set_live", refuse)
    monkeypatch.setattr(schema, "require_world", lambda world: world)
    monkeypatch.setattr(schema, "ensure_world", lambda engine, world: None)
    monkeypatch.setattr(schema, "operate", refuse)
    raws = tmp_path / "raws"
    monkeypatch.setattr(main.paths, "workspace_path", lambda table, *parts: str(raws))

    def call(client, headers, params=None):
        token = dict(headers, **{auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN})
        del recorder.values[:]
        client.post("/admin/chain/pause", json={"reason": "r"}, headers=token, params=params)
        client.put("/admin/ontology-explorer/worlds/w/live", json={"live": False}, headers=token)
        client.put("/admin/ontology-explorer/worlds/operating", json={"world": "w"}, headers=token)
        client.post("/tables/t/upload", headers=headers, params=params, files={"file": ("a.csv", b"x")})
        uploaded = sorted(p.name for p in raws.iterdir())
        assert len(uploaded) == 1 and len(heard["world"]) == 2 and len(recorder.values) == 4  # canary
        return {"middleware": recorder.values[0], "pause": heard["pause"], "live": heard["world"][0],
                "operating": heard["world"][1], "upload": uploaded[0].split(")")[0] + ")"}
    return call


def test_on_every_seat_records_the_signed_in_name_whatever_the_request_claims(issuer, seats):
    issuer.config(admins=[UPN])
    client = _client()
    _sign_in(client, issuer)
    assert seats(client, SPOOF, params={"user": "spoof"}) == {
        "middleware": UPN, "pause": UPN, "live": UPN, "operating": UPN, "upload": "user(%s)" % UPN}


@pytest.mark.parametrize("headers, params, expected", [
    (SPOOF, {"user": "q"}, {"middleware": "spoof", "pause": "spoof", "live": "spoof",
                            "operating": "spoof", "upload": "user(q)"}),
    ({}, None, {"middleware": "user", "pause": "operator", "live": None, "operating": None,
                "upload": "user(Unknown)"}),
])
def test_off_every_seat_records_what_it_did_before(off, seats, headers, params, expected):
    assert seats(_client(), headers, params=params) == expected


@pytest.mark.parametrize("path", ["/health", "/auth/me", "/internal/events/broadcast"])
def test_on_an_open_path_with_nobody_signed_in_keeps_todays_answer(issuer, monkeypatch, path):
    recorder = _Recorder(main.request_user)
    monkeypatch.setattr(main, "request_user", recorder)
    client = _client()
    for headers in (dict(SPOOF, **{auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN}),
                    {auth.ADMIN_TOKEN_HEADER: ADMIN_TOKEN}):
        if path.startswith("/internal"):
            client.post(path, json={"event_type": "noop", "payload": {}}, headers=headers)
        else:
            client.get(path, headers=headers)
    assert recorder.values == ["spoof", "user"]
