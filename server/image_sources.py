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
`resolve` is the one seat that asks a source's kind; it reads and never writes. `keep` is the one writer: a
picture pasted or dropped on a grid image cell, kept under the source that declares `receive`, and `sweep`
deletes what no image cell has held for its `keep_days` (owner 11-05).
"""
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import threading
from collections import OrderedDict

import paths
from error_said import told

logger = logging.getLogger("Server")

CONFIG_PATH = paths.config_path("image_sources.json")
#: The column type word a cell holds an image reference under - the server's one spelling of it (the walk says a
#: value read from such a column is one, 총괄 2d6a0fd58).
COLUMN_TYPE = "image"
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
#: [총괄 1084b4bfd] The sizes a thumbnail may be asked at (`px`, its longer side): below 16 a picture is a dot the
#: screen draws without one; above 1,024 the original is the cheaper answer.
PX_MIN, PX_MAX = 16, 1024
#: The thumbnails one server process keeps, by bytes - in memory, newest kept, the oldest let go: a board of a few
#: hundred cells at 64 px is a few MB, so 64 MB holds every size a screen asks in a day without a disk to clean.
THUMB_CACHE_BYTES = 64 * 1024 * 1024
_THUMBS = OrderedDict()
_THUMBS_LOCK = threading.Lock()
_SAID_NO_PILLOW = []


class ImageRefused(Exception):
    """Why a reference cannot be read, with the HTTP status that says it."""

    def __init__(self, status, sentence):
        super().__init__(sentence)
        self.status = status


def load_sources(path=None):
    """The declared sources; no file declares none - held until the file changes (`config_watcher.held`). One that
    stops reading keeps the sources read before; with none read before it raises, as it did."""
    from database import config_watcher

    path = path or CONFIG_PATH
    return config_watcher.held(config_watcher.names_of([path]), ("image_sources", path), lambda: _read_sources(path))


def _read_sources(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


#: What a full path may name and be read as it is - an image file, never another kind of file.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def resolve(ref, sources=None, _hops=0):
    """-> ("file", path) | ("bytes", data, media type)."""
    text = str(ref or "").strip()
    if _ADDRESS.match(text):
        return _fetch("%r" % text, text)
    if text[:2] in ("\\\\", "//"):
        # a share path as a table may hold it - every backslash doubled, or written with /: one spelling, \\server\share\..
        # (소유자 10-24 «이미지 공유폴더고 \\\\ 이렇게 되어있음»)
        text = "\\\\" + re.sub(r"[\\/]+", lambda m: "\\", text.lstrip("\\/"))
    if os.path.isabs(text) or text.startswith("\\\\"):
        # 소유자 10-24 «이미지 경로를 절대 경로로 했더니 인식을 못하네»: a full path is read from the folder source whose
        # root holds it - the folders a report may read stay the ones image_sources.json declares
        sources = load_sources() if sources is None else sources
        from parsers.directory_watcher import _safe_relative_path

        for name, source in sorted(sources.items()):
            root = str((source or {}).get("root") or "") if isinstance(source, dict) else ""
            # an entry that is not a source (a comment line, a string) is skipped (owner 10-24 «str object no attr get»)
            if isinstance(source, dict) and source.get("kind") == "folder" and root and _safe_relative_path(text, root) is not None:
                return _folder(name, source, text)
        if os.path.splitext(text)[1].lower() in IMAGE_SUFFIXES:
            # 소유자 10-24 «이미지 절대경로 여전히 안되고»: an image file named by its full path is read as it is
            if os.path.isfile(text):
                return ("file", os.path.realpath(text))
            raise ImageRefused(404, "no file %r - this server cannot see it (a share it is not logged on to, or a path "
                                    "of another machine)" % text)
        raise ImageRefused(404, "%r is under no folder source of image_sources.json - add one whose root holds it "
                                '(e.g. {"<name>": {"kind": "folder", "root": "%s"}})'
                           % (text, os.path.dirname(text).replace("\\", "/")))
    name, colon, rest = text.partition(":")
    if not (colon and name and rest):
        raise ImageRefused(400, "%r is neither an http(s) address nor <source>:<path or key>" % text)
    sources = load_sources() if sources is None else sources
    source = sources.get(name)
    folder_path = rest.strip()
    if (folder_path[:2] in ("\\\\", "//") or os.path.isabs(folder_path)) and \
            (not isinstance(source, dict) or source.get("kind") == "folder"):
        # 소유자 10-24 «절대경로 안 먹는다고 · satpatches 아래에 이미지가 없대잖아»: <source>:<a full path> is that full
        # path - read as a bare full path is (the share spellings folded), not joined under the source's root
        return resolve(folder_path, sources, _hops)
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


def shrink(answer, px):
    """`resolve`'s answer with its longer side at `px` - the ratio kept, never made larger - as ("bytes", data,
    media type); a JPEG stays one, anything else comes back PNG. Kept by (the original as it is now, px): a file by its
    path and stamp, read bytes by their hash - a changed original is another key. What Pillow cannot read, and every
    answer when Pillow is not installed (said once), comes back as it was."""
    if answer[0] == "file":
        status = os.stat(answer[1])
        key = ("file", answer[1], status.st_mtime_ns, status.st_size, px)
    else:
        key = ("bytes", hashlib.sha1(answer[1]).hexdigest(), px)
    with _THUMBS_LOCK:
        held = _THUMBS.get(key)
        if held is not None:
            _THUMBS.move_to_end(key)
            return held
    try:
        from PIL import Image
    except ImportError:
        if not _SAID_NO_PILLOW:
            _SAID_NO_PILLOW.append(True)
            logger.warning("[Image] Pillow is not installed - px is ignored and the original is sent "
                           "(RUN.md: pip install Pillow)")
        return answer
    try:
        if answer[0] == "file":
            with open(answer[1], "rb") as handle:
                data = handle.read()
        else:
            data = answer[1]
        image = Image.open(io.BytesIO(data))
        if max(image.size) <= px:
            return answer
        jpeg = image.format == "JPEG"
        image.thumbnail((px, px))
        out = io.BytesIO()
        if jpeg:
            image.convert("RGB").save(out, "JPEG", quality=85)
        else:
            image.save(out, "PNG")
    except Exception as exc:                                    # noqa: BLE001 - the original still answers
        logger.info("[Image] %s is sent as it is - it did not shrink: %s: %s", key[1], type(exc).__name__, told(exc), exc_info=exc)
        return answer
    thumb = ("bytes", out.getvalue(), "image/jpeg" if jpeg else "image/png")
    with _THUMBS_LOCK:
        _THUMBS[key] = thumb
        while sum(len(each[1]) for each in _THUMBS.values()) > THUMB_CACHE_BYTES and len(_THUMBS) > 1:
            _THUMBS.popitem(last=False)
    return thumb


def _folder(name, source, rest):
    from parsers.directory_watcher import _safe_relative_path

    root = str(source.get("root") or "")
    path = os.path.join(root, rest)
    if not root or _safe_relative_path(path, root) is None:
        raise ImageRefused(400, "%r is outside the root of image source %r" % (rest, name))
    if not os.path.isfile(path):
        if isinstance(source.get(RECEIVE), dict) and RECEIVED_NAME.match(rest.strip()):
            try:
                keep_days = receive_settings(name, source)[1]
            except ImageRefused:
                keep_days = None                               # the sweep deletes nothing then - not its sentence
            if keep_days:
                raise ImageRefused(404, "picture removed - it was unreferenced for %s days (image_sources.json "
                                        "%s.%s.keep_days)" % (keep_days, name, RECEIVE))
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


# ── Receiving pictures (owner 11-05 ㄱ): a grid image cell's paste or drop is kept under the folder source that declares
#    `receive`, by a name the server makes, and its reference handed back - the client writes it as any edit. ──

#: The cell that makes a folder source the one that receives: {"max_mb": <MB>, "keep_days": <days; absent = never
#: deleted>}. One source may carry it.
RECEIVE = "receive"
#: What `keep` names a file, relative to the root - the sweep touches nothing else.
RECEIVED_NAME = re.compile(r"^[^/\\]+/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.(png|jpg|gif|bmp|webp|tif)$")
#: A received name at the end of a cell's value, whatever names its source or its root: `referenced` compares by it,
#: so a renamed receiving source or a full path still holds its picture (lead 11-05 ①).
_RECEIVED_TAIL = re.compile(r"([^/\\:]+/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.(?:png|jpg|gif|bmp|webp|tif))$")
#: The values shaped like one, found in one read of a column: <anything><day><one separator><32 chars>.<anything>
_RECEIVED_LIKE = "%____-__-___" + "_" * 32 + ".%"
#: {relative path: the day it was first seen unreferenced} - in the receiving root, beside what it is about.
UNREFERENCED_FILE = ".assy_unreferenced.json"
#: Head bytes -> (suffix, media type): the one «is this a picture» judge; Pillow stays optional.
_HEADS = ((b"\x89PNG\r\n\x1a\n", "png", "image/png"), (b"\xff\xd8\xff", "jpg", "image/jpeg"),
          (b"GIF87a", "gif", "image/gif"), (b"GIF89a", "gif", "image/gif"), (b"BM", "bmp", "image/bmp"),
          (b"II*\x00", "tif", "image/tiff"), (b"MM\x00*", "tif", "image/tiff"))


def receiver(sources=None):
    """(name, source) of the folder source that receives pictures, or ImageRefused 409 - none, or more than one."""
    sources = load_sources() if sources is None else sources
    named = sorted(name for name, source in sources.items()
                   if isinstance(source, dict) and source.get("kind") == "folder" and isinstance(source.get(RECEIVE), dict))
    if not named:
        raise ImageRefused(409, 'no image source receives pictures - add "receive": {"max_mb": 10} to one folder '
                                "source in image_sources.json")
    if len(named) > 1:
        raise ImageRefused(409, 'image sources %s both receive pictures - keep "receive" on one' % ", ".join(named))
    return named[0], sources[named[0]]


def receive_settings(name, source):
    """(the largest picture in bytes, keep days or None) the receiving source declares, or ImageRefused 409 naming the
    cell: max_mb a number above 0; keep_days whole days of 1 or more (0 could delete a picture between its paste and
    the cell's write) or absent - never deleted."""
    receive = source[RECEIVE]
    max_mb, keep_days = receive.get("max_mb"), receive.get("keep_days")
    if isinstance(max_mb, bool) or not isinstance(max_mb, (int, float)) or not max_mb > 0:
        raise ImageRefused(409, "image_sources.json %s.receive.max_mb is %s - write the largest picture it takes in MB, "
                                "e.g. 10" % (name, "not declared" if max_mb is None else repr(max_mb)))
    if keep_days is not None and (isinstance(keep_days, bool) or not isinstance(keep_days, int) or keep_days < 1):
        raise ImageRefused(409, "image_sources.json %s.receive.keep_days is %r - write whole days, 1 or more, or leave "
                                "it out to keep every received picture" % (name, keep_days))
    return int(max_mb * 1024 * 1024), keep_days


def check_size(name, source, size):
    """ImageRefused 413 when `size` bytes is more than the receiving source takes - the one size judge."""
    limit = receive_settings(name, source)[0]
    if size > limit:
        raise ImageRefused(413, "the picture is %.1f MB (%s bytes); at most %s MB (%s bytes) - make it smaller or raise "
                                "receive.max_mb of %s" % (size / 1024 / 1024, format(size, ","),
                                                          source[RECEIVE].get("max_mb"), format(limit, ","), name))


def picture_kind(head: bytes):
    """(suffix, media type) of a picture by its first bytes, or None."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    return next(((suffix, media) for magic, suffix, media in _HEADS if head.startswith(magic)), None)


def keep(table, data: bytes, sources=None, today=None) -> dict:
    """Keep one received picture under the receiving source: <root>/<table>/<day>/<32 hex>.<suffix>, written whole
    (a temporary name, then replaced). -> {"ref", "bytes", "media_type"}; ImageRefused 409 / 413 / 415."""
    import datetime
    import uuid

    name, source = receiver(sources)
    check_size(name, source, len(data))
    kind = picture_kind(data[:16])
    if kind is None:
        raise ImageRefused(415, "that file is not a png, jpeg, gif, bmp, webp or tiff picture")
    relative = "%s/%s/%s.%s" % (table, (today or datetime.date.today()).isoformat(), uuid.uuid4().hex, kind[0])
    path = os.path.join(str(source["root"]), *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "wb") as fh:
        fh.write(data)
    os.replace(path + ".part", path)
    return {"ref": "%s:%s" % (name, relative), "bytes": len(data), "media_type": kind[1]}


def image_columns(table_config=None):
    """[(table, column)] of every column whose declared type is `image`."""
    if table_config is None:
        from database import crud
        table_config = crud.TABLE_CONFIG
    return [(table, column) for table, info in sorted((table_config or {}).items()) if isinstance(info, dict)
            for column, kind in sorted((info.get("column_types") or {}).items()) if kind == COLUMN_TYPE]


def referenced(db, relatives, columns=None):
    """(the received names some image column's current value ends with, ["table.column" it could not read]) - each
    column read once for the values shaped like a received name and compared here by that name, not by the source
    before it: a renamed receiving source or a full path still holds its picture (lead 11-05 ①). The cost is the
    table, not the number of files (an IN per 1,000 refs read the table once per batch). A column the catalogue calls
    image but this process has no model of is named, never passed over (④). One query for every dialect."""
    from sqlalchemy import select

    from database import models

    relatives, found, unread = set(relatives), set(), []
    for table, column in (image_columns() if columns is None else columns):
        model = models.DYNAMIC_TABLES.get(table)
        if model is None or column not in model.__table__.c:
            unread.append("%s.%s" % (table, column))
            continue
        cell = model.__table__.c[column]
        for (value,) in db.execute(select(cell).where(cell.like(_RECEIVED_LIKE)).distinct()):
            match = _RECEIVED_TAIL.search(str(value or "").strip().replace("\\", "/"))
            if match and match.group(1) in relatives:
                found.add(match.group(1))
        db.rollback()
    return found, unread


def received_files(root):
    """{relative path: full path} of the files `keep` made under `root` - its name, not a link itself, and in no folder
    that leads out of the root."""
    from parsers.directory_watcher import _safe_relative_path

    real_root, out = os.path.realpath(root), {}
    for here, dirs, names in os.walk(root):
        if _safe_relative_path(os.path.realpath(here), real_root) is None:
            dirs[:] = []                                       # a folder that leads out of the root: nothing under it
            continue
        for name in names:
            full = os.path.join(here, name)
            relative = os.path.relpath(full, root).replace("\\", "/")
            if RECEIVED_NAME.match(relative) and not os.path.islink(full):
                out[relative] = full
    return out


def _read_marks(path, files, today):
    """The state file's {relative: day} for the files listed now; one that is not that shape is said and counted afresh
    (deleting later, never sooner)."""
    import datetime

    try:
        with open(path, encoding="utf-8") as fh:
            marks = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("[Images] %s is unreadable (%s) - counting afresh from %s", path, told(exc), today)
        return {}
    if not isinstance(marks, dict):
        logger.warning("[Images] %s is not a {path: day} object - counting afresh from %s", path, today)
        return {}
    out = {}
    for relative, day in marks.items():
        try:
            if relative in files:
                out[relative] = datetime.date.fromisoformat(str(day)).isoformat()
        except ValueError:
            pass                                               # that file counted afresh
    return out


def sweep(db, today=None, sources=None, columns=None) -> dict:
    """Delete the received pictures no image column's current value has held for `receive.keep_days` days, counted
    from the day a sweep first saw one unreferenced (UNREFERENCED_FILE); held again, it is taken off. Files made after
    the listing are not this pass's. Nothing is deleted when keep_days is absent (said), when a receive cell is not
    one it takes, or when an image column could not be read (said). -> {"listed", "unreferenced", "deleted",
    "freed_bytes"} or {"refused"} / {"unread"}"""
    import datetime

    today = today or datetime.date.today()
    try:
        name, source = receiver(sources)
    except ImageRefused:
        return {}
    try:
        keep_days = receive_settings(name, source)[1]
    except ImageRefused as refused:
        logger.warning("[Images] not swept - %s", refused)
        return {"refused": str(refused)}
    root = str(source.get("root") or "")
    files = received_files(root) if root and os.path.isdir(root) else {}
    held, unread = referenced(db, files, columns)
    if unread:
        logger.warning("[Images] not swept - image column(s) %s could not be read (no model in this process); nothing "
                       "deleted - tried again at the next sweep", ", ".join(unread))
        return {"unread": unread}
    marks_path = os.path.join(root, UNREFERENCED_FILE)
    marks = _read_marks(marks_path, files, today.isoformat())
    unreferenced = [relative for relative in sorted(files) if relative not in held]
    for relative in held:
        marks.pop(relative, None)
    for relative in unreferenced:
        marks.setdefault(relative, today.isoformat())
    gone = [relative for relative in unreferenced if keep_days is not None
            and (today - datetime.date.fromisoformat(marks[relative])).days >= keep_days]
    if keep_days is None:
        if unreferenced:
            logger.info("[Images] keep_days not declared - kept %d unreferenced received file(s), %.1f MB (%s.%s)",
                        len(unreferenced), sum(os.path.getsize(files[r]) for r in unreferenced) / 1024 / 1024,
                        name, RECEIVE)
    elif gone:
        logger.info("[Images] sweeping: %d file(s), %.1f MB unreferenced for >= %s days (%s)",
                    len(gone), sum(os.path.getsize(files[r]) for r in gone) / 1024 / 1024, keep_days, name)
    deleted, freed = 0, 0
    for relative in gone:
        try:
            size = os.path.getsize(files[relative])
            os.remove(files[relative])
            marks.pop(relative, None)
            deleted, freed = deleted + 1, freed + size
        except OSError as exc:
            logger.warning("[Images] could not delete %s: %s - tried again at the next sweep", relative, told(exc))
    with open(marks_path + ".part", "w", encoding="utf-8") as fh:
        json.dump(marks, fh, ensure_ascii=False, sort_keys=True)
    os.replace(marks_path + ".part", marks_path)
    return {"listed": len(files), "unreferenced": len(unreferenced), "deleted": deleted, "freed_bytes": freed}
