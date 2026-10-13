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
    batch_chars · known_chars · known_per_seed   `text_links.ask_links`' (NUMBER_CELLS)

The pace is the gateway's: no limit is kept here (소유자 10-13 「어차피 서버가 거절함」). No answer (connection,
time limit, 5xx, 408) and a 429 are asked again - after CALL_RETRY_WAITS, a 429 after its Retry-After - while the
next try starts within CALL_RETRY_WINDOW_S of the first failure: a gateway back within about 55 s of it is not a
failure; past that, or a Retry-After over the window, `LlmCallFailed`. Every wait is `_wait`: slices that are
progress on this thread's claim and, in a chain group, a stage boundary a pause rewinds at.

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
                "batch_chars": (4000, True, "a whole number of characters"),
                "known_chars": (4000, True, "a whole number of characters"),
                "known_per_seed": (5, True, "a whole number of links")}
RETIRED_ENV = ("ASSY_LLM_BASE_URL", "ASSY_LLM_MODEL", "ASSY_LLM_API_KEY", "ASSY_LLM_TIMEOUT_S")
TOO_MANY_REQUESTS = 429
REQUEST_TIMEOUT = 408
#: No answer (connection, time limit, 5xx, 408) and a 429 are asked again after these waits (a 429 after its
#: Retry-After instead) while the next try would start within the window of the first failure - tries at
#: 0 · 5 · 15 · 35 · 55 s: a gateway back within about 55 s of the first failure is not a failure (총괄 10-13 ④ ·
#: 최종 검수 1). A Retry-After over the window is not waited for.
CALL_RETRY_WAITS = (5, 10, 20, 20)
CALL_RETRY_WINDOW_S = 60.0
#: A wait is slept in slices this long - each one progress on the claim and, in a chain group, a pause check.
WAIT_SLICE_S = 1.0
#: A gateway that refuses the key - the refusal says to check it.
KEY_REFUSED = (401, 403)
#: The retry window's clock and the sleep - tests replace them.
_steady = time.monotonic
_sleep = time.sleep
#: The first httpx that takes `proxy=` (0.26); an older one is refused by name.
HTTPX_WITH_PROXY = (0, 26)


class LlmRefused(ValueError):
    """A call that gave no usable answer, said by name. Its sentence never carries the key."""


class LlmCallFailed(LlmRefused):
    """The call itself failed - no answer came (connection, time limit, 5xx, 408, a 429), past its retries, or a 429
    asking to wait more than the window. Asking text by text would ask a gateway that is not answering (총괄 10-13 ②)."""


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
                  max_retries=0)       # the client asks once - every try is this seat's (총괄 10-13 ⑤)


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


def _wait(seconds):
    """Sleep `seconds` in WAIT_SLICE_S slices. Each slice is progress on this thread's claim - a queue does not read
    the wait as a stall - and, inside a chain group, a stage boundary: a pause raises `ChainPaused` here and the group
    is rewound as at any boundary, not failed."""
    from chain import control
    from database.context import request_chain_group
    from utils import heartbeat

    left = float(seconds)
    while left > 0:
        if request_chain_group.get():
            control.raise_if_paused()
        heartbeat.progress(None)
        step = min(WAIT_SLICE_S, left)
        _sleep(step)
        left -= step


def _retry_after(exc):
    """The seconds a 429 answer asks for (its Retry-After header), or None."""
    try:
        said = float(getattr(getattr(exc, "response", None), "headers", {}).get("retry-after"))
    except (TypeError, ValueError):
        return None
    return said if said > 0 else None


def _no_answer(exc, status):
    """No answer came - asked again (CALL_RETRY_WAITS) as a 429 is: a 5xx or a 408, or no status at all from a
    connection that failed or timed out. Any other exception (a TypeError, a UnicodeEncodeError ...) is not."""
    if status is not None:
        return status >= 500 or status == REQUEST_TIMEOUT
    import sys
    kinds = [ConnectionError, TimeoutError]
    for module, name in (("httpx", "TransportError"), ("openai", "APIConnectionError")):
        kind = getattr(sys.modules.get(module), name, None)
        if isinstance(kind, type):
            kinds.append(kind)
    return isinstance(exc, tuple(kinds))


def _refused(status, built, error, asked=None):
    """The refusal of a call that gave no answer, by what came back (총괄 10-13 ⑧): no answer, a 5xx, a 408 or a
    429 past its retries - or one asking more than the window - is `LlmCallFailed` (not asked text by text);
    401 · 403 says to check the key; a client that could not be built and any other 4xx (400, 413 too large,
    404 ...) is `LlmRefused` - a request of many texts is then asked text by text. `error` is masked."""
    said = "the language model call failed: %s" % error
    if not built:
        return LlmRefused(said)
    if status in KEY_REFUSED:
        return LlmRefused("the gateway refused the key (%s) - check api_key and headers in config/%s: %s"
                          % (status, CONFIG_FILE, error))
    if status is None or status >= 500 or status in (TOO_MANY_REQUESTS, REQUEST_TIMEOUT):
        if asked is not None:
            said += " - it asked to wait %d s (Retry-After), more than %d s" % (math.ceil(asked), CALL_RETRY_WINDOW_S)
        return LlmCallFailed(said)
    return LlmRefused(said)


def ask_json(prompt, *, system=None):
    """One call -> the JSON object the model answered. Refused by name when the file refuses, the
    call fails or the answer is not a JSON object (`_refused` says which class). `from None` keeps the
    client's own exception - which may quote the key - out of every traceback. No answer (`_no_answer`) and a 429
    are tried again after CALL_RETRY_WAITS (a 429 after its Retry-After) while the next try starts within
    CALL_RETRY_WINDOW_S of the first failure - a gateway back within about 55 s passes; a longer stop, or a
    Retry-After over the window, is `LlmCallFailed` (총괄 10-13 ④)."""
    cells = settings()
    key = cells["api_key"]
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    payload = {"model": cells["model"], "messages": messages}
    from internal_event_client import _redact_proxy
    proxy = _redact_proxy(cells["proxy"]) if cells["proxy"] else None
    failed, failed_at = 0, None
    while True:
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
            asked = _retry_after(exc) if status == TOO_MANY_REQUESTS else None
            if client is not None and (status == TOO_MANY_REQUESTS or _no_answer(exc, status)) and (
                    asked is None or asked <= CALL_RETRY_WINDOW_S) and failed < len(CALL_RETRY_WAITS):
                failed_at = _steady() if failed_at is None else failed_at
                wait = asked if asked is not None else CALL_RETRY_WAITS[failed]
                if _steady() - failed_at + wait <= CALL_RETRY_WINDOW_S:
                    again, failed = wait, failed + 1
                    said = "[LLM] call failed (%s) - retrying in %d s (%d of %d)" % (
                        error[:300], math.ceil(again), failed, len(CALL_RETRY_WAITS))
            if again is None:
                raise _refused(status, client is not None, error,
                               asked if asked is not None and asked > CALL_RETRY_WINDOW_S else None) from None
        finally:
            _log({"received": _now(), **back, "ms": round((time.monotonic() - started) * 1000)}, key)
        if again is None:
            return _object(content, key)
        logger.warning(said)
        _wait(again)
