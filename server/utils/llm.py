# -*- coding: utf-8 -*-
"""The one seat a mapper asks a language model through (총괄 b5b335f2e ①), reached as
`mapper_sdk.ask_json`. Where it calls, which model, the key and the time limit are environment
values - none of them is in code - and the key never reaches a log line or an error sentence.

    ASSY_LLM_BASE_URL   an OpenAI-compatible endpoint
    ASSY_LLM_MODEL      the model name
    ASSY_LLM_API_KEY    the key
    ASSY_LLM_TIMEOUT_S  seconds one call may take (default 60)

`openai` is imported inside the call, so an installation that never asks runs without it.
"""
import json
import os

BASE_URL_ENV = "ASSY_LLM_BASE_URL"
MODEL_ENV = "ASSY_LLM_MODEL"
KEY_ENV = "ASSY_LLM_API_KEY"
TIMEOUT_ENV = "ASSY_LLM_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 60.0


class LlmRefused(ValueError):
    """A call that gave no usable answer, said by name. Its sentence never carries the key."""


def model():
    """The model this installation names, or None."""
    return (os.environ.get(MODEL_ENV) or "").strip() or None


def _settings():
    values = {name: (os.environ.get(name) or "").strip()
              for name in (BASE_URL_ENV, MODEL_ENV, KEY_ENV, TIMEOUT_ENV)}
    missing = [name for name in (BASE_URL_ENV, MODEL_ENV, KEY_ENV) if not values[name]]
    if missing:
        raise LlmRefused("no language model is configured - set %s" % ", ".join(missing))
    try:
        timeout = float(values[TIMEOUT_ENV]) if values[TIMEOUT_ENV] else DEFAULT_TIMEOUT_S
    except ValueError:
        raise LlmRefused("%s is not a number of seconds: %r" % (TIMEOUT_ENV, values[TIMEOUT_ENV])) from None
    return values[BASE_URL_ENV], values[MODEL_ENV], values[KEY_ENV], timeout


def _client(base_url, key, timeout):
    """The OpenAI client. Tests replace this function; nothing else builds a client."""
    try:
        from openai import OpenAI
    except ImportError:
        raise LlmRefused("the openai package is not installed - pip install openai") from None
    return OpenAI(base_url=base_url, api_key=key, timeout=timeout)


def _masked(text, key):
    return str(text).replace(key, "***") if key else str(text)


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
    """One call -> the JSON object the model answered. Refused by name when nothing is
    configured, the call fails or the answer is not a JSON object. `from None` keeps the
    client's own exception - which may quote the key - out of every traceback."""
    base_url, name, key, timeout = _settings()
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    try:
        answer = _client(base_url, key, timeout).chat.completions.create(
            model=name, messages=messages)
        content = answer.choices[0].message.content
    except LlmRefused:
        raise
    except Exception as exc:                                       # noqa: BLE001
        raise LlmRefused("the language model call failed: %s: %s"
                         % (type(exc).__name__, _masked(exc, key))) from None
    return _object(content, key)
