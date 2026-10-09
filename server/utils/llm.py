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

Every call writes two JSON lines to llm_requests.log beside the process logs - what is sent (before
the call, so a call that hangs still shows) and what came back. The key is in neither.

`openai` is imported inside the call, so an installation that never asks runs without it.
⚰️ ASSY_LLM_BASE_URL · ASSY_LLM_MODEL · ASSY_LLM_API_KEY · ASSY_LLM_TIMEOUT_S (10-06) are retired - a
box that still sets them and has no file is told to move them.
"""
import datetime
import json
import logging
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
RETIRED_ENV = ("ASSY_LLM_BASE_URL", "ASSY_LLM_MODEL", "ASSY_LLM_API_KEY", "ASSY_LLM_TIMEOUT_S")
#: The first httpx that takes `proxy=` (0.26); an older one is refused by name.
HTTPX_WITH_PROXY = (0, 26)


class LlmRefused(ValueError):
    """A call that gave no usable answer, said by name. Its sentence never carries the key."""


def settings():
    """The six cells of config/llm_config.json, read now. Refused by name when the file is absent
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
    timeout = loaded.get("timeout_s")
    if timeout is None:
        timeout = DEFAULT_TIMEOUT_S
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise LlmRefused("timeout_s in config/%s is not a number of seconds above 0: %r"
                         % (CONFIG_FILE, timeout))
    headers = loaded.get("headers") or {}
    if not isinstance(headers, dict):
        raise LlmRefused("headers in config/%s is not an object" % CONFIG_FILE)
    proxy = loaded.get("proxy")
    if proxy is not None and not isinstance(proxy, str):
        raise LlmRefused("proxy in config/%s is not a URL or null" % CONFIG_FILE)
    cells.update(timeout_s=float(timeout), headers={str(k): str(v) for k, v in headers.items()},
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
    return OpenAI(base_url=cells["base_url"], api_key=cells["api_key"], timeout=cells["timeout_s"],
                  default_headers=cells["headers"] or None,
                  http_client=httpx.Client(proxy=cells["proxy"], trust_env=False))


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


def ask_json(prompt, *, system=None):
    """One call -> the JSON object the model answered. Refused by name when the file refuses, the
    call fails or the answer is not a JSON object. `from None` keeps the client's own exception -
    which may quote the key - out of every traceback."""
    cells = settings()
    key = cells["api_key"]
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    payload = {"model": cells["model"], "messages": messages}
    client = _client(cells)
    back = {"id": uuid.uuid4().hex[:12], "status": None}
    from internal_event_client import _redact_proxy
    # the URL the client posts to: its base_url always ends in "/" (the SDK adds it)
    _log({"sent": _now(), "id": back["id"], "url": str(client.base_url) + "chat/completions",
          "model": cells["model"], "headers": dict(client.default_headers), "payload": payload,
          "proxy": _redact_proxy(cells["proxy"]) if cells["proxy"] else None}, key)
    started = time.monotonic()
    try:
        raw = client.chat.completions.with_raw_response.create(**payload)
        back.update(status=raw.status_code, answer=_body(raw.text))
        content = raw.parse().choices[0].message.content
    except Exception as exc:                                       # noqa: BLE001
        back.update(status=back["status"] or getattr(exc, "status_code", None),
                    error="%s: %s" % (type(exc).__name__, exc))
        raise LlmRefused("the language model call failed: %s" % _masked(back["error"], key)) from None
    finally:
        _log({"received": _now(), **back, "ms": round((time.monotonic() - started) * 1000)}, key)
    return _object(content, key)
