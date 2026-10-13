# -*- coding: utf-8 -*-
"""The one seat a mapper asks a language model through (총괄 b5b335f2e ①), reached as
`mapper_sdk.ask_json`. Where it calls, which model, the key, the time limit, extra headers and the
proxy are cells of one declaration file read on every call - a change reaches the next call
(소유자 10-09 「환경설정으로 하지 말고 선언 파일로」 · 총괄 043915ab0 ①):

    config/llm_config.json      shape: config/sample/llm_config.json.sample
    base_url    an OpenAI-compatible endpoint
    model       the model name
    api_key     the key
    timeout_s   seconds one call may take (default 60)
    headers     extra request headers (default none)
    proxy       a proxy URL; absent or null = straight to base_url, the system proxy is not read
    requests_per_minute   calls in any 60 s, every process that asks together (default 20 - the
                          gateway's own limit, 소유자 10-13)
    batch_chars · known_chars · known_per_seed   `text_links.ask_links`' (NUMBER_CELLS)

Every call first waits for room under requests_per_minute - in the `llm_calls` table under an advisory
lock on PostgreSQL, so the chain's slots, the retroactive run and the server count together; within
the process on any other database - and says «[LLM] per-minute limit - waiting n s». A 429 answer is
asked again after its Retry-After (else one window), RATE_LIMITED_TRIES times, each through the gate; no
answer (connection, time limit, 5xx) after CALL_RETRY_WAITS within a minute of the first failure, likewise.

Every call writes two JSON lines to llm_requests.log beside the process logs - what is sent (before
the call, so a call that hangs still shows) and what came back. The key is in neither.

`openai` is imported inside the call, so an installation that never asks runs without it.
⚰️ ASSY_LLM_BASE_URL · ASSY_LLM_MODEL · ASSY_LLM_API_KEY · ASSY_LLM_TIMEOUT_S (10-06) are retired - a
box that still sets them and has no file is told to move them.
"""
import datetime
import json
import logging
import math
import os
import threading
import time
import uuid

import paths

logger = logging.getLogger(__name__)

CONFIG_FILE = "llm_config.json"
SAMPLE = "config/%s/%s.sample" % (paths.CONFIG_SAMPLE_DIRNAME, CONFIG_FILE)
REQUEST_LOG = "llm_requests.log"
REQUIRED_CELLS = ("base_url", "model", "api_key")
DEFAULT_TIMEOUT_S = 60.0
#: Cells that are a number above 0: (default for an absent or null cell, whole number, what it counts).
#: batch_chars - the texts one ask_links request carries, counted as len(text) (a longer text goes alone):
#: the answer copies each link's sentence, so it grows with the texts; 4,000 keeps it far under a
#: 4k-token answer cap. known_chars - the dictionary lines and known links one request carries when the
#: mapper hands `known` (the same 4,000 - their sum is a second text block). known_per_seed - known links
#: drawn for each seed, bridges between seeds not counted.
NUMBER_CELLS = {"timeout_s": (DEFAULT_TIMEOUT_S, False, "a number of seconds"),
                "requests_per_minute": (20, True, "a whole number of requests"),
                "batch_chars": (4000, True, "a whole number of characters"),
                "known_chars": (4000, True, "a whole number of characters"),
                "known_per_seed": (5, True, "a whole number of links")}
RETIRED_ENV = ("ASSY_LLM_BASE_URL", "ASSY_LLM_MODEL", "ASSY_LLM_API_KEY", "ASSY_LLM_TIMEOUT_S")
#: The per-minute limit's window, and the advisory lock its table is read and written under.
RATE_WINDOW_S = 60.0
RATE_LOCK = "llm_calls"
#: How many times a 429 answer is asked again before the call is refused.
RATE_LIMITED_TRIES = 3
TOO_MANY_REQUESTS = 429
#: No answer (connection, time limit, 5xx) is asked again after these waits, while the first such failure is within
#: the window - a gateway that blinks for under a minute does not fail the group (총괄 10-13 ④).
CALL_RETRY_WAITS = (5, 10, 20)
CALL_RETRY_WINDOW_S = 60.0
#: A gateway that refuses the key - the refusal says to check it.
KEY_REFUSED = (401, 403)
#: PostgreSQL's «relation does not exist».
UNDEFINED_TABLE = "42P01"
#: The gate's clock and sleep - tests replace them.
_clock = time.time
_sleep = time.sleep
#: The calls this process made in the window - the gate on a database without advisory locks.
_recent = []
_recent_lock = threading.Lock()
#: The first httpx that takes `proxy=` (0.26); an older one is refused by name.
HTTPX_WITH_PROXY = (0, 26)


class LlmRefused(ValueError):
    """A call that gave no usable answer, said by name. Its sentence never carries the key."""


class LlmCallFailed(LlmRefused):
    """The call itself failed or could not be made - no answer came (connection, time limit, 5xx, a 429 past
    its tries or asking to wait more than a window, the per-minute table). Asking text by text would ask a
    gateway that is not answering (총괄 10-13 ②)."""


def settings():
    """The cells of config/llm_config.json, read now. Refused by name when the file is absent
    (with the retired environment values named when they are still set) or a cell is not usable."""
    from database.crud import _decode_config_text, _parse_position, is_blank_value

    path = paths.config_path(CONFIG_FILE)
    if not os.path.exists(path):
        still_set = [name for name in RETIRED_ENV if not is_blank_value(os.environ.get(name))]
        if still_set:
            raise LlmRefused("ASSY_LLM_* environment variables are not read any more - write server/config/%s "
                             "(sample: %s)" % (CONFIG_FILE, SAMPLE))
        raise LlmRefused("no language model is configured - write server/config/%s (sample: %s)"
                         % (CONFIG_FILE, SAMPLE))
    try:
        with open(path, "rb") as handle:
            loaded = json.loads(_decode_config_text(handle.read()))
    except (OSError, ValueError) as exc:
        raise LlmRefused("config/%s could not be read: %s" % (CONFIG_FILE, _parse_position(exc))) from None
    if not isinstance(loaded, dict):
        raise LlmRefused("config/%s is %s, not an object" % (CONFIG_FILE, type(loaded).__name__))
    cells = {name: None if is_blank_value(loaded.get(name)) else str(loaded[name]).strip()
             for name in REQUIRED_CELLS}
    missing = [name for name in REQUIRED_CELLS if cells[name] is None]
    if missing:
        raise LlmRefused("config/%s does not set %s" % (CONFIG_FILE, ", ".join(missing)))
    for name, (default, whole, what) in NUMBER_CELLS.items():
        value = loaded.get(name)
        if value is None:
            value = default
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
                or (whole and value != int(value))):
            raise LlmRefused("%s in config/%s is not %s above 0: %r" % (name, CONFIG_FILE, what, value))
        cells[name] = int(value) if whole else float(value)
    headers = loaded.get("headers") or {}
    if not isinstance(headers, dict):
        raise LlmRefused("headers in config/%s is not an object" % CONFIG_FILE)
    proxy = loaded.get("proxy")
    if proxy is not None and not isinstance(proxy, str):
        raise LlmRefused("proxy in config/%s is not a URL or null" % CONFIG_FILE)
    cells.update(headers={str(k): str(v) for k, v in headers.items()},
                 proxy=None if is_blank_value(proxy) else proxy.strip())
    return cells


def model():
    """The model the file names, or None - a label, so it never refuses."""
    try:
        return settings()["model"]
    except LlmRefused:
        return None


def _client(cells):
    """The OpenAI client over an httpx client that reads no proxy setting of its own: the file's
    proxy or none. Tests replace `openai`; nothing else builds a client."""
    try:
        from openai import OpenAI
    except ImportError:
        raise LlmRefused("the openai package is not installed - pip install openai") from None
    import httpx
    found = tuple(int(part) for part in httpx.__version__.split(".")[:2] if part.isdigit())
    if found < HTTPX_WITH_PROXY:
        raise LlmRefused("httpx %s cannot take a proxy - %s or later is needed: pip install -U httpx"
                         % (httpx.__version__, ".".join(map(str, HTTPX_WITH_PROXY))))
    from internal_event_client import _redact_proxy
    try:
        http_client = httpx.Client(proxy=cells["proxy"], trust_env=False)
    except Exception as exc:                                       # noqa: BLE001
        # not its words: they quote what it could not read - a raw «/» in the password ends the host early and
        # comes back as «Invalid port: '<the password's head>'» (총괄 93570a1ea)
        raise LlmRefused("proxy in config/%s is not a URL httpx reads (%s): %s"
                         % (CONFIG_FILE, type(exc).__name__, _redact_proxy(cells["proxy"]))) from None
    return OpenAI(base_url=cells["base_url"], api_key=cells["api_key"], timeout=cells["timeout_s"],
                  default_headers=cells["headers"] or None, http_client=http_client,
                  max_retries=0)       # every request takes a turn under the per-minute limit (총괄 10-13 ⑤)


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _masked(text, key):
    return str(text).replace(key, "***") if key else str(text)


def _log(line, key):
    """One JSON line to llm_requests.log, the key masked over the whole line. A log that cannot be
    written is said once here and the call goes on."""
    text = _masked(json.dumps(line, ensure_ascii=False, default=str), key) + "\n"
    try:
        with open(paths.log_path(REQUEST_LOG), "ab") as handle:
            handle.write(text.encode("utf-8"))
    except OSError as exc:
        logger.warning("[LLM] %s not written (%s) - this call goes on without its log line", REQUEST_LOG, exc)


def _body(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _object(content, key):
    """The answer as a JSON object. A fenced block (```json ... ```) is read as its body."""
    body = str(content or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError:
        raise LlmRefused("the answer is not JSON: %s" % _masked(body[:200], key)) from None
    if not isinstance(parsed, dict):
        raise LlmRefused("the answer is JSON but not an object: %s" % type(parsed).__name__)
    return parsed


def _why(exc, proxy):
    """A failed call as one line: the exception and every cause under it, down to the innermost (총괄 024e3d31f -
    the client says «Connection error.», the reason is in its cause: a name not found, a refusal, the proxy, the
    clock), and the proxy the call went through."""
    from internal_event_client import _redact_proxy

    said, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        said.append("%s: %s" % (type(exc).__name__, exc))
        exc = exc.__cause__ if exc.__cause__ is not None else (None if exc.__suppress_context__ else exc.__context__)
    return " <- ".join(said) + " · proxy: " + (_redact_proxy(proxy) if proxy else "none (direct)")


def _wait_s(times, now, cap):
    """Seconds until one more call fits: 0 while fewer than `cap` of `times` fall in the window
    ending `now`, else until the cap-th newest of them leaves it."""
    inside = sorted(t for t in times if t > now - RATE_WINDOW_S)
    return 0.0 if len(inside) < cap else inside[-cap] + RATE_WINDOW_S - now


def _take_a_turn(cap):
    """Wait until one more call fits under `cap` a minute, then write this call down. On PostgreSQL
    the calls are the `llm_calls` rows, read and written under one advisory lock, so every process
    counts against the same cap; elsewhere (SQLite) this process's own list."""
    from database import database

    engine = database.engine
    shared = engine.dialect.name == "postgresql"
    while True:
        now = _clock()
        if shared:
            wait = _shared_turn(engine, now, cap)
        else:
            with _recent_lock:
                _recent[:] = [t for t in _recent if t > now - RATE_WINDOW_S]
                wait = _wait_s(_recent, now, cap)
                if wait <= 0:
                    _recent.append(now)
        if wait <= 0:
            return
        logger.info("[LLM] per-minute limit - waiting %d s (%d requests a minute)", math.ceil(wait), cap)
        _sleep(wait)


def _shared_turn(engine, now, cap):
    """One look at `llm_calls` under the lock: the rows past the window deleted, `now` written when it
    fits -> the seconds to wait (0: written). A table that cannot be used is refused by name - the call
    could not be made, so `LlmCallFailed`; the boot is named only when the table is missing."""
    from sqlalchemy import select, text
    from sqlalchemy.exc import SQLAlchemyError

    from database import models

    table = models.LlmCall.__table__
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": RATE_LOCK})
            conn.execute(table.delete().where(table.c.called_at <= now - RATE_WINDOW_S))
            wait = _wait_s([at for (at,) in conn.execute(select(table.c.called_at))], now, cap)
            if wait <= 0:
                conn.execute(table.insert().values(called_at=now))
            return wait
    except SQLAlchemyError as exc:
        said = str(getattr(exc, "orig", None) or exc).strip().splitlines()
        missing = getattr(getattr(exc, "orig", None), "pgcode", None) == UNDEFINED_TABLE
        raise LlmCallFailed("the per-minute limit could not use table %s (%s: %s)%s"
                            % (table.name, type(exc).__name__, said[0] if said else "",
                               " - it is made by the web server's boot (create_all): start it once on this code"
                               if missing else "")) from None


def _retry_after(exc):
    """The seconds a 429 answer asks for (its Retry-After header), else one window."""
    try:
        said = float(getattr(getattr(exc, "response", None), "headers", {}).get("retry-after"))
    except (TypeError, ValueError):
        return RATE_WINDOW_S
    return said if said > 0 else RATE_WINDOW_S


def _refused(status, built, error, asked=None):
    """The refusal of a call that gave no answer, by what came back (총괄 10-13 ⑧): no answer, a 5xx or a 429
    past its tries - or one asking more than a window - is `LlmCallFailed` (asked again later, not text by text);
    401 · 403 says to check the key; a client that could not be built and any other 4xx (400, 413 too large,
    404 ...) is `LlmRefused` - a request of many texts is then asked text by text. `error` is masked."""
    said = "the language model call failed: %s" % error
    if not built:
        return LlmRefused(said)
    if status in KEY_REFUSED:
        return LlmRefused("the gateway refused the key (%s) - check api_key and headers in config/%s: %s"
                          % (status, CONFIG_FILE, error))
    if status is None or status >= 500 or status == TOO_MANY_REQUESTS:
        if asked is not None:
            said += " - it asked to wait %d s (Retry-After), more than %d s" % (math.ceil(asked), RATE_WINDOW_S)
        return LlmCallFailed(said)
    return LlmRefused(said)


def ask_json(prompt, *, system=None):
    """One call -> the JSON object the model answered. Refused by name when the file refuses, the
    call fails or the answer is not a JSON object (`_refused` says which class). `from None` keeps the
    client's own exception - which may quote the key - out of every traceback. Each try first takes a
    turn under the per-minute limit. A 429 is tried again RATE_LIMITED_TRIES times, after its Retry-After
    when that is at most one window. No answer (connection, time limit, 5xx) is tried again after
    CALL_RETRY_WAITS while the first such failure is within CALL_RETRY_WINDOW_S - a gateway's blink passes,
    a longer stop is `LlmCallFailed` (총괄 10-13 ④)."""
    cells = settings()
    key = cells["api_key"]
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    payload = {"model": cells["model"], "messages": messages}
    from internal_event_client import _redact_proxy
    proxy = _redact_proxy(cells["proxy"]) if cells["proxy"] else None
    limited, failed, failed_at = 0, 0, None
    while True:
        _take_a_turn(cells["requests_per_minute"])
        back = {"id": uuid.uuid4().hex[:12], "status": None}
        client, again = None, None
        started = time.monotonic()
        try:
            # built in here: a client that cannot be built fails like a call - a received line, one refusal (총괄 93570a1ea)
            client = _client(cells)
            # the URL the client posts to: its base_url always ends in "/" (the SDK adds it)
            _log({"sent": _now(), "id": back["id"], "url": str(client.base_url) + "chat/completions",
                  "model": cells["model"], "headers": dict(client.default_headers), "payload": payload,
                  "proxy": proxy}, key)
            raw = client.chat.completions.with_raw_response.create(**payload)
            back.update(status=raw.status_code, answer=_body(raw.text))
            content = raw.parse().choices[0].message.content
        except Exception as exc:                                       # noqa: BLE001
            if client is None:
                # no sent line - where it was going, from the file (총괄 93570a1ea)
                back.update(url=cells["base_url"].rstrip("/") + "/chat/completions", proxy=proxy)
            status = back["status"] or getattr(exc, "status_code", None)
            back.update(status=status, error=_why(exc, cells["proxy"]))
            error = _masked(back["error"], key)
            if status == TOO_MANY_REQUESTS and limited < RATE_LIMITED_TRIES:
                again, limited = _retry_after(exc), limited + 1
                said = ("[LLM] the gateway answered 429 (too many requests) - waiting %d s, then try %d of %d"
                        % (math.ceil(again), limited + 1, RATE_LIMITED_TRIES + 1))
            elif client is not None and (status is None or status >= 500):
                failed_at = _clock() if failed_at is None else failed_at
                if failed < len(CALL_RETRY_WAITS) and (
                        _clock() - failed_at + CALL_RETRY_WAITS[failed] <= CALL_RETRY_WINDOW_S):
                    again, failed = CALL_RETRY_WAITS[failed], failed + 1
                    said = "[LLM] call failed (%s) - retrying in %d s (%d of %d)" % (
                        error[:300], again, failed, len(CALL_RETRY_WAITS))
            if again is None or again > RATE_WINDOW_S:
                raise _refused(status, client is not None, error, again) from None
        finally:
            _log({"received": _now(), **back, "ms": round((time.monotonic() - started) * 1000)}, key)
        if again is None:
            return _object(content, key)
        logger.warning(said)
        _sleep(again)
