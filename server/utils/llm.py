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
    embedding_model   the gateway's embedding model (`embed`) - absent or blank: none, the admin help picks guide
                      sections by their words (owner 10-29)
    embedding_base_url · embedding_api_key   where `embed` calls and its key - absent or blank: base_url · api_key

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
#: The cells `embed` reads as "embedding_<cell>" when written - blank: the chat's (owner 10-29 «임베딩 모델은 api 주소가
#: 다른데»). Proxy, headers, time limit and the try loop are the same.
EMBEDDING_ENDPOINT_CELLS = ("base_url", "api_key")
DEFAULT_TIMEOUT_S = 60.0
#: Cells that are a number above 0: (default for an absent or null cell, whole number, what it counts).
#: batch_chars - the texts one ask_links request carries, counted as len(text) (a longer text goes alone):
#: the answer copies each link's sentence, so it grows with the texts; 4,000 keeps it far under a
#: 4k-token answer cap. known_chars - the dictionary lines and known links one request carries when the
#: mapper hands `known` (the same 4,000 - their sum is a second text block). known_per_seed - known links
#: drawn for each seed, bridges between seeds not counted. walk_chars - the cards one agent-walk request carries
#: (`text_links.walk_context`; its instructions and the answer's shape always go).
NUMBER_CELLS = {"timeout_s": (DEFAULT_TIMEOUT_S, False, "a number of seconds"),
                "batch_chars": (4000, True, "a whole number of characters"),
                "known_chars": (4000, True, "a whole number of characters"),
                "known_per_seed": (5, True, "a whole number of links"),
                "walk_chars": (4000, True, "a whole number of characters")}
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


class LlmNotAnObject(LlmRefused):
    """An answer came and holds no JSON object - `answer` its first 200 characters, the key masked: a caller may ask
    once more with it (소유자 10-26 «응답이 json 이 아니어서 멈추는 경우»). A call with no answer is `LlmCallFailed`."""

    def __init__(self, sentence, answer=""):
        super().__init__(sentence)
        self.answer = answer


class LlmCallFailed(LlmRefused):
    """The call itself failed - no answer came (connection, time limit, 5xx, 408, a 429), past its retries, or a 429
    asking to wait more than the window. Asking text by text would ask a gateway that is not answering (총괄 10-13 ②)."""


def settings():
    """The cells of config/llm_config.json - held until the file changes (`config_watcher.held`, e6a0bdbbd; read per
    call before). Refused by name when the file is absent (with the retired environment values named when they are
    still set) or a cell is not usable; a file that stops being usable after it was keeps the cells read before."""
    from database import config_watcher

    path = paths.config_path(CONFIG_FILE)
    return dict(config_watcher.held(config_watcher.names_of([path]), "llm.settings", _read_settings))


def _read_settings():
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
    embedding = loaded.get("embedding_model")
    cells.update(headers={str(k): str(v) for k, v in headers.items()},
                 proxy=None if is_blank_value(proxy) else proxy.strip(),
                 embedding_model=None if is_blank_value(embedding) else str(embedding).strip())
    for name in EMBEDDING_ENDPOINT_CELLS:
        own = loaded.get("embedding_" + name)
        cells["embedding_" + name] = cells[name] if is_blank_value(own) else str(own).strip()
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
    """The answer as a JSON object. A fenced block (```json ... ```) is read as its body; an answer with text around its
    JSON - a sentence before it, two fences - as the first whole {...} object in it (소유자 10-26 안 ㄱ)."""
    body = str(content or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    said = _masked(body[:200], key)
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = _first_object(body)
        if parsed is None:
            raise LlmNotAnObject("the answer is not JSON: %s" % said, said) from None
    if not isinstance(parsed, dict):
        raise LlmNotAnObject("the answer is JSON but not an object: %s" % type(parsed).__name__, said)
    return parsed


def _first_object(text):
    """The first whole {...} object in `text`, or None - its end found by the JSON reader, so a brace in a string ends
    nothing. Said once, with what was left around it."""
    decoder = json.JSONDecoder()
    at = text.find("{")
    while at != -1:
        try:
            parsed, end = decoder.raw_decode(text, at)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            logger.warning("[LLM] answer had text around its JSON - read the object (%d character(s) left)",
                           len(text) - (end - at))
            return parsed
        at = text.find("{", at + 1)
    return None


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


#: The token counts a gateway answer may say (`ask_json(usage=)`).
USAGE_CELLS = ("prompt_tokens", "completion_tokens", "total_tokens")


#: What a model may wrap an id in - taken off both ends before ids are compared.
ID_WRAPPING = "[]\"'“”‘’«»「」 "


def _text_id(value):
    """An id as compared: its text (`crud.clean_str_value` - 7, 7.0 and "7" alike, "007" not), brackets and
    quotes off both ends."""
    from database import crud

    return crud.clean_str_value(value).strip(ID_WRAPPING)


def _requests(texts, cap):
    """`texts` [(id, text)] in order, cut into requests of at most `cap` characters of text - a text
    longer than `cap` goes alone."""
    out, size = [], 0
    for item in texts:
        if out and out[-1] and size + len(item[1]) <= cap:
            out[-1].append(item)
            size += len(item[1])
        else:
            out.append([item])
            size = len(item[1])
    return out


def _ask(request, prompt_of, read, key):
    """One request -> ({id: rows}, {id: why}) for its texts [(id, text)]: the answer's item of each id,
    its list under `key` read by `read(text, items)` - ids compared as text, brackets and quotes off (`_text_id`). A request of one
    text answered {<key>: [...]} is that text's answer. An answer refused whole gives every text its
    sentence; a call that failed (`LlmCallFailed`) is raised - the whole batch fails (`max_group_attempts`)."""
    try:
        answer = ask_json(prompt_of(request))
        items = answer.get("texts")
        if not isinstance(items, list) and len(request) == 1 and isinstance(answer.get(key), list):
            items = [{"id": request[0][0], key: answer[key]}]       # one text, answered the one-text way
        if not isinstance(items, list):
            raise LlmRefused("the answer has no 'texts' list: %s" % sorted(answer)[:10])
    except LlmCallFailed:
        raise
    except LlmRefused as exc:
        return {}, {ident: str(exc) for ident, _text in request}
    by_id = {}
    for item in items:
        if isinstance(item, dict):
            by_id.setdefault(_text_id(item.get("id")), item)       # the first item of an id is its answer
    rows, why = {}, {}
    for ident, text in request:
        item = by_id.get(_text_id(ident))
        if item is None:
            why[ident] = "the answer has no item for text %r" % (ident,)
        elif not isinstance(item.get(key), list):
            why[ident] = "the answer's item for text %r has no '%s' list: %s" % (ident, key, sorted(item)[:10])
        else:
            try:
                rows[ident] = read(text, item[key])
            except LlmRefused as exc:
                why[ident] = str(exc)
    return rows, why


def ask_batch(texts, prompt_of, read, key, cap, log=None):
    """Texts [(id, text)] asked in requests of at most `cap` characters -> ({id: what `read` made}, {id: why}, calls).
    `prompt_of(request)` writes one request's prompt; the answer is {"texts": [{"id", <key>: [...]}, ...]} and
    `read(text, items)` reads one text's list under `key` (raising `LlmRefused` refuses that text). A text a
    request of several left unread is asked again alone, once; a call that failed (`LlmCallFailed`) is raised.
    `log`: the caller's logger for the asked-again line (default this module's).
    The one batching of the product's model calls - `text_links.ask_links` (key «links») and the chain's
    `derive: {kind: "ask"}` go through it (lead 10-27)."""
    log = log or logger
    rows, why, asked = {}, {}, 0
    for request in _requests(texts, cap):
        got, failed = _ask(request, prompt_of, read, key)
        asked += 1
        rows.update(got)
        if failed and len(request) > 1:
            log.warning("[LLM] a request of %d texts left %d unread - each asked alone: %s", len(request),
                           len(failed), "; ".join("%r: %s" % (ident, said[:160]) for ident, said in failed.items()))
            for ident, one in request:
                if ident in failed:
                    got, failed_alone = _ask([(ident, one)], prompt_of, read, key)
                    asked += 1
                    rows.update(got)
                    why.update(failed_alone)
        else:
            why.update(failed)
    return rows, why, asked


def ask_json(prompt, *, system=None, usage=None):
    """One call -> the JSON object the model answered (the first one, in text around it). Refused by name when the
    file refuses, the call fails (`_refused` says which class) or the answer holds no JSON object (`LlmNotAnObject`).
    Tried again as `_call` says. `usage`: a dict filled with the token counts the gateway said (`prompt_tokens` ·
    `completion_tokens` · `total_tokens`), left empty when it said none."""
    cells = settings()
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]

    def read(parsed):
        if usage is not None:
            said_usage = getattr(parsed, "usage", None)
            usage.update({name: getattr(said_usage, name) for name in USAGE_CELLS
                          if isinstance(getattr(said_usage, name, None), int)})
        return parsed.choices[0].message.content

    content = _call(cells, "chat/completions", {"model": cells["model"], "messages": messages},
                    lambda client: client.chat.completions.with_raw_response.create, read)
    return _object(content, cells["api_key"])


def embed(texts):
    """[vector] of `texts`, in order, from the file's `embedding_model` - one call, tried again as `_call` says.
    Refused by name when no embedding model is set (owner 10-29: the gateway's bge-m3)."""
    cells = settings()
    if not cells.get("embedding_model"):
        raise LlmRefused("no embedding_model in config/%s" % CONFIG_FILE)
    own = dict(cells, **{name: cells["embedding_" + name] for name in EMBEDDING_ENDPOINT_CELLS})
    return _call(own, "embeddings", {"model": cells["embedding_model"], "input": list(texts)},
                 lambda client: client.embeddings.with_raw_response.create,
                 lambda parsed: [list(item.embedding) for item in parsed.data])


def _call(cells, endpoint, payload, create, read):
    """`read(parsed answer)` of one request to `endpoint` - the one try loop of the product's model calls (`ask_json`,
    `embed`). `create(client)` is the SDK's raw-response create. `from None` keeps the client's own exception - which
    may quote the key - out of every traceback. No answer (`_no_answer`) and a 429 are tried again after
    CALL_RETRY_WAITS (a 429 after its Retry-After) while the next try starts within CALL_RETRY_WINDOW_S of the first
    failure - a gateway back within about 55 s passes; a longer stop, or a Retry-After over the window, is
    `LlmCallFailed` (총괄 10-13 ④). Every try writes its sent and received lines to llm_requests.log."""
    key = cells["api_key"]
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
            _log({"sent": _now(), "id": back["id"], "url": str(client.base_url) + endpoint,
                  "model": payload["model"], "headers": dict(client.default_headers), "payload": payload,
                  "proxy": proxy}, key)
            raw = create(client)(**payload)
            back.update(status=raw.status_code, answer=_body(raw.text))
            said = read(raw.parse())
        except Exception as exc:                                       # noqa: BLE001
            if client is None:
                # no sent line - where it was going, from the file (총괄 93570a1ea)
                back.update(url=cells["base_url"].rstrip("/") + "/" + endpoint, proxy=proxy)
            status = back["status"] or getattr(exc, "status_code", None)
            back.update(status=status, error=_why(exc, cells["proxy"]))
            error = _masked(back["error"], key)
            asked = _retry_after(exc) if status == TOO_MANY_REQUESTS else None
            if client is not None and (status == TOO_MANY_REQUESTS or _no_answer(exc, status)) and (
                    failed < len(CALL_RETRY_WAITS)):
                failed_at = _steady() if failed_at is None else failed_at
                wait = asked if asked is not None else CALL_RETRY_WAITS[failed]
                if _steady() - failed_at + wait <= CALL_RETRY_WINDOW_S:
                    again, failed = wait, failed + 1
                    told_line = "[LLM] call failed (%s) - retrying in %d s (%d of %d)" % (
                        error[:300], math.ceil(again), failed, len(CALL_RETRY_WAITS))
            if again is None:
                raise _refused(status, client is not None, error,
                               asked if asked is not None and asked > CALL_RETRY_WINDOW_S else None) from None
        finally:
            _log({"received": _now(), **back, "ms": round((time.monotonic() - started) * 1000)}, key)
        if again is None:
            return said
        logger.warning(told_line)
        _wait(again)
