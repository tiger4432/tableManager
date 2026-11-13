# -*- coding: utf-8 -*-
"""Many images as one zip, streamed (owner 11-12 ㄴ): one folder per group as the caller names it, each image read by
`image_sources.resolve` - GET /api/image's reader, so the same refusals and the same reach - originals only, stored
as they are (no recompression). A ref the reader refuses is left out and said in `_not_included.txt`. Nothing is
spooled to disk: the zip is written into the response as it goes."""
import io
import mimetypes
import os
import re
import time
import zipfile

import image_sources
from error_said import told

#: images one request may hold - refused before any read. The bound is time and download size (lead 11-13): on the
#: box (2cf9ef63f, 11-13) 2,000 took 14 s at its 327 B images and 35 s at 1 MB each (2 GB out); server RSS +1~8 MB,
#: no DB connection held, grid page reads unchanged beside it
MAX_IMAGES = 2000
#: the gallery's word for a blank group (client2/src/gallery.js `empty`)
BLANK = "(Empty)"
NOT_INCLUDED = "_not_included.txt"
CHUNK = 1024 * 1024
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)), *("LPT%d" % i for i in range(1, 10))}


class TooMany(ValueError):
    """More images than one zip holds - said before any read."""


def safe_part(text) -> str:
    """One folder or file name Windows takes: illegal characters to «_», no trailing dot or space, a reserved device
    name prefixed; blank - the gallery's «(Empty)»."""
    part = _ILLEGAL.sub("_", str(text if text is not None else "")).strip().rstrip(". ")
    if not part:
        return BLANK
    return "_" + part if part.split(".")[0].upper() in _RESERVED else part


def check(folders) -> int:
    """-> how many images the request names; TooMany past MAX_IMAGES."""
    n = sum(len(f.get("refs") or []) for f in folders)
    if n > MAX_IMAGES:
        raise TooMany("%d images asked; one zip holds at most %d - pick fewer groups or rows" % (n, MAX_IMAGES))
    return n


def _file_name(ref, name, answer) -> str:
    base = name or re.split(r"[\\/]", str(ref).split(":", 1)[-1].rstrip("\\/"))[-1]
    stem, ext = os.path.splitext(safe_part(base))
    if not ext:
        media = mimetypes.guess_type(answer[1])[0] if answer[0] == "file" else answer[2]
        ext = (mimetypes.guess_extension(media or "") or "").replace(".jpe", ".jpg")
    return stem + ext


def _unique(name, used) -> str:
    stem, ext = os.path.splitext(name)
    k, out = 1, name
    while out.lower() in used:
        k += 1
        out = "%s (%d)%s" % (stem, k, ext)
    used.add(out.lower())
    return out


class _Sink(io.RawIOBase):
    """What zipfile writes, held until the stream takes it - unseekable, so zipfile writes data descriptors."""

    def __init__(self):
        self._parts = []

    def writable(self):
        return True

    def write(self, data):
        self._parts.append(bytes(data))
        return len(data)

    def take(self) -> bytes:
        out = b"".join(self._parts)
        self._parts.clear()
        return out


def stream(folders, resolve=None):
    """Yield the zip's bytes: each folder's images under its safe path, then `_not_included.txt` when a ref was left
    out (its folder, the ref, the reader's sentence)."""
    resolve = resolve or image_sources.resolve
    sink, left_out, used = _Sink(), [], {}
    stamp = time.localtime()[:6]
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as zf:
        for folder in folders:
            parts = [safe_part(p) for p in (folder.get("path") or [])]
            here = "/".join(parts)
            for item in folder.get("refs") or []:
                ref = item.get("ref")
                try:
                    answer = resolve(ref)
                    name = _unique(_file_name(ref, item.get("name"), answer), used.setdefault(here, set()))
                    info = zipfile.ZipInfo((here + "/" if here else "") + name, date_time=stamp)
                    info.compress_type = zipfile.ZIP_STORED
                    with zf.open(info, "w") as out:
                        if answer[0] == "file":
                            with open(answer[1], "rb") as src:
                                for chunk in iter(lambda: src.read(CHUNK), b""):
                                    out.write(chunk)
                                    yield sink.take()
                        else:
                            out.write(answer[1])
                except (image_sources.ImageRefused, OSError) as refused:
                    left_out.append("%s\t%s\t%s" % (here or "/", ref, told(refused).strip()))
                    continue
                yield sink.take()
        if left_out:
            zf.writestr(NOT_INCLUDED, "folder\tref\twhy\r\n" + "\r\n".join(left_out) + "\r\n")
    yield sink.take()
