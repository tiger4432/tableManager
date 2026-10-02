# -*- coding: utf-8 -*-
"""Image references — one grammar, declared sources, one read (lead 785b2ef54 · 20e1c09df).

A cell holds text: an http(s) address as written, or `<source name>:<path or key>`. The column
says it is one by its type word `image` (stored as text). `config/image_sources.json` names the
sources, one file:

    {"<name>": {"kind": "folder", "root": "<directory>"},
     "<name>": {"kind": "db", "query": "SELECT <column> FROM <table> WHERE <key column> = :key",
                "connection": {"dialect": "postgresql", "host": "..", "port": 5432,
                               "database": "..", "user": "..", "password_env": "<ENV VAR NAME>"}},
     "<name>": {"kind": "url", "base": "https://../"}}

No secret lives in the file: a db source names the environment variable that holds its password.
Every image is read by the server - an http(s) cell and a url source are fetched and sent on,
never handed to the browser (총괄 f087403fe); `_fetch` holds the guards that makes safe.
`resolve` is the one seat that asks a source's kind; it reads and never writes.
"""
import json
import mimetypes
import os
import re

import paths

CONFIG_PATH = paths.config_path("image_sources.json")
KINDS = ("folder", "db", "url")
#: The one parameter a db source's query binds.
KEY = "key"
#: [총괄 191912ce2] How long a browser may keep an answer before asking again - the main grid's
#: preview revisits the same cells. A replaced image can show its old picture this long.
CACHE_SECONDS = 3600
CACHE_CONTROL = "private, max-age=%d" % CACHE_SECONDS
#: [총괄 f087403fe] The largest answer a fetch reads; past it the fetch stops and refuses.
MAX_BYTES = 20 * 1024 * 1024
_ADDRESS = re.compile(r"^https?://", re.IGNORECASE)
_ENGINES = {}


class ImageRefused(Exception):
    """Why a reference cannot be read, with the HTTP status that says it."""

    def __init__(self, status, sentence):
        super().__init__(sentence)
        self.status = status


def load_sources(path=None):
    """The declared sources; no file declares none."""
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve(ref, sources=None, _hops=0):
    """-> ("file", path) | ("bytes", data, media type)."""
    text = str(ref or "").strip()
    if _ADDRESS.match(text):
        return _fetch("%r" % text, text)
    name, colon, rest = text.partition(":")
    if not (colon and name and rest):
        raise ImageRefused(400, "%r is neither an http(s) address nor <source>:<path or key>" % text)
    sources = load_sources() if sources is None else sources
    source = sources.get(name)
    if not isinstance(source, dict):
        raise ImageRefused(404, "image source %r is not declared in image_sources.json" % name)
    kind = source.get("kind")
    if kind == "folder":
        return _folder(name, source, rest)
    if kind == "db":
        return _db(name, source, rest, sources, _hops)
    if kind == "url":
        return _url(name, source, rest)
    raise ImageRefused(500, "image source %r has kind %r; a source is one of %s"
                       % (name, kind, ", ".join(KINDS)))


def _folder(name, source, rest):
    from parsers.directory_watcher import _safe_relative_path

    root = str(source.get("root") or "")
    path = os.path.join(root, rest)
    if not root or _safe_relative_path(path, root) is None:
        raise ImageRefused(400, "%r is outside the root of image source %r" % (rest, name))
    if not os.path.isfile(path):
        raise ImageRefused(404, "no file %r in image source %r" % (rest, name))
    return ("file", os.path.realpath(path))


def _engine(name, connection):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    password_env = connection.get("password_env")
    if password_env and password_env not in os.environ:
        raise ImageRefused(500, "image source %r reads its password from %s, which is not set"
                           % (name, password_env))
    url = URL.create(connection.get("dialect") or "postgresql",
                     username=connection.get("user"),
                     password=os.environ.get(password_env) if password_env else None,
                     host=connection.get("host"), port=connection.get("port"),
                     database=connection.get("database"))
    cached = _ENGINES.get(name)
    if cached is None or cached[0] != url:
        cached = (url, create_engine(url, pool_pre_ping=True))
        _ENGINES[name] = cached
    return cached[1]


def _db(name, source, rest, sources, hops):
    from sqlalchemy import text

    query = text(str(source.get("query") or ""))
    if set(query._bindparams) != {KEY}:
        raise ImageRefused(500, "image source %r: its query must bind :%s and nothing else"
                           % (name, KEY))
    from sqlalchemy.exc import SQLAlchemyError

    engine = _engine(name, source.get("connection") or {})
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection = connection.execution_options(postgresql_readonly=True)
            row = connection.execute(query, {KEY: rest}).first()
            connection.rollback()
    except SQLAlchemyError as error:
        raise ImageRefused(502, "image source %r could not be read: %s"
                           % (name, str(error).strip().splitlines()[0])) from error
    value = row[0] if row is not None else None
    if value is None:
        raise ImageRefused(404, "no image for key %r in image source %r" % (rest, name))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return ("bytes", bytes(value), mimetypes.guess_type(rest)[0] or "application/octet-stream")
    if hops:
        raise ImageRefused(500, "image source %r answered %r with another reference twice"
                           % (name, rest))
    return resolve(value, sources, hops + 1)


def _url(name, source, rest):
    from urllib.parse import urlsplit

    base = str(source.get("base") or "")
    address = base + rest
    # [총괄 e96551d02] The value is a path under the base, never a new host: joined to a base
    # without a trailing «/», `@evil.com/a.png` would make evil.com the host.
    try:
        here, there = urlsplit(base), urlsplit(address)
        same = ((here.scheme.lower(), here.hostname, here.port)
                == (there.scheme.lower(), there.hostname, there.port))
    except ValueError:                      # a port that is not a number
        same = False
    if not same:
        raise ImageRefused(400, "%r leaves the host of image source %r" % (rest, name))
    return _fetch("image source %r for %r" % (name, rest), address)


def _fetch(label, address):
    """The one fetch and its three guards (총괄 f087403fe) - the server reads any address an
    http(s) cell names, so what comes back must be an image, no larger than MAX_BYTES (stopped
    while it streams), and not a redirect, which is not followed."""
    import requests

    try:
        answer = requests.get(address, timeout=10, allow_redirects=False, stream=True)
    except requests.RequestException as error:
        raise ImageRefused(502, "%s could not be fetched: %s"
                           % (label, str(error).strip().splitlines()[0])) from error
    with answer:
        if 300 <= answer.status_code < 400:
            raise ImageRefused(502, "%s answered a redirect (%d) - not followed"
                               % (label, answer.status_code))
        if answer.status_code != 200:
            raise ImageRefused(502, "%s answered %d" % (label, answer.status_code))
        media = (answer.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not media.startswith("image/"):
            raise ImageRefused(502, "%s answered %r, not an image" % (label, media or "no type"))
        data = bytearray()
        for chunk in answer.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ImageRefused(502, "%s is larger than %d bytes - not read further"
                                   % (label, MAX_BYTES))
    return ("bytes", bytes(data), media)
