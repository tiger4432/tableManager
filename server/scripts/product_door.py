"""The product door, in one place: the HTTP endpoints a tool must write through.

🔴 WHY A MODULE AND NOT A COPY PER SCRIPT. Three tools now write rows this way (the row
generator and the two `load_*` seeds), and 「같은 기능인데 두 경로가 있어서도 안 됨」 is a
standing rule with a measured history in this repository: two request builders for one
route drifted until one of them stopped sending three arguments. A second caller is the
moment the template is extracted, not the moment a third is written.

🔴 WHY TOOLS GO THROUGH THE DOOR AT ALL (S-78, ruling 176). A statement issued straight at
the table does not pass the session, so `before_flush` stages no outbox event: the write
has no envelope, no `write⁻¹`, and it breaks `read = fold(E)` because the fold cannot see
it. The door is also the shape production runs, so a tool that uses it exercises the path
being measured rather than a private one.

WHAT THE DOOR REQUIRES, each learned by measurement rather than assumed:

  business key   Supplied per row. A table whose key is composite over columns the caller
                 does not send would otherwise leave every row's identity blank, and
                 `crud._update_row_business_key` records what follows - blank-keyed rows
                 in one batch collide WITH EACH OTHER, the IntegrityError recovery cannot
                 resolve rows that were never committed, and the batch is refused.
  no `effort`    `EffortReport` says an automatic path must not send one: absent means
                 "not measured", and a zero dilutes the human-effort average that is this
                 product's first core value. Every caller here is such a path.
  no `row_id`    The engine mints it (`crud._get_or_create_row`), and ruling 150 refuses a
                 supplied id that is not a uuid7. A tool that mints its own is doing the
                 engine's job; sending the business key is enough to resolve or create.
  batch size     Ruling 170 caps a request at `MAX_ROWS_PER_REQUEST`. Not a tuning knob -
                 it is the size production runs, so a larger one measures nothing real.
"""
from __future__ import annotations

import datetime
import json
import time

PUT_ROWS = "/tables/{table}/data/updates"
DELETE_ROWS = "/tables/{table}/rows/batch_delete"
MAX_ROWS_PER_REQUEST = 1000
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 120.0


class DoorRefusal(Exception):
    """A refusal that names what is wrong, rather than sending something wrong."""


def opener():
    """A urllib opener with proxies disabled FOR THIS OPENER ONLY.

    🔴 NOT the `NO_PROXY` environment variable, which disables the proxy registry
    process-wide and has broken unrelated lookups on this machine before. It matters at
    all because a corporate proxy will accept `127.0.0.1` and answer for it, which reads
    as "the server is down".
    """
    import urllib.request

    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def jsonable(value):
    """Values the door's JSON body can carry. Instants go out as ISO-8601 with offset."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return value


def row_item(business_key, values, *, source_name, updated_by=None):
    """One `GeneralUpdateItem`. `row_id` is deliberately absent - see the module docstring."""
    if business_key is None or str(business_key).strip() == "":
        raise DoorRefusal(
            "every row needs a business key: a blank one makes all rows in the batch the "
            "same identity, and the batch is then refused after its retries")
    return {
        "business_key_val": business_key,
        "updates": {name: jsonable(value) for name, value in values.items()},
        "source_name": source_name,
        "updated_by": updated_by or source_name,
    }


def put_rows(table, items, *, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT,
             log=print):
    """Send `items` through the door in requests of at most `MAX_ROWS_PER_REQUEST`.

    `items` may be any iterable, so a caller with ten million rows does not build a list.
    Timing is reported per REQUEST because that is how the gate is stated, and an average
    would hide the one slow request that is the finding.
    """
    import urllib.request

    url = base_url.rstrip("/") + PUT_ROWS.format(table=table)
    send = opener()
    buffer, sent, seconds = [], 0, []

    def _flush():
        if not buffer:
            return
        body = json.dumps({"updates": buffer, "silent": False}).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="PUT", headers={"Content-Type": "application/json"})
        started = time.monotonic()
        with send.open(request, timeout=timeout) as response:
            answer = json.loads(response.read().decode("utf-8") or "{}")
        seconds.append(time.monotonic() - started)
        log("  put %5d rows  %6.2fs%s" % (
            len(buffer), seconds[-1],
            "  effort_error=%s" % answer["effort_error"]
            if answer.get("effort_error") else ""))
        buffer.clear()

    for item in items:
        buffer.append(item)
        sent += 1
        if len(buffer) >= MAX_ROWS_PER_REQUEST:
            _flush()
    _flush()
    return {"rows": sent, "requests": len(seconds),
            "seconds_total": round(sum(seconds), 2),
            "seconds_max": round(max(seconds), 2) if seconds else 0.0}


def delete_rows(table, row_ids, *, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT,
                user_name="system", log=print):
    """Delete by row id through the door, in batches.

    🔴 THE DOOR DELETES BY ID, NOT BY PREDICATE (`RowDeleteBatch` is `{row_ids, user_name}`).
    A caller holding a `WHERE` clause must resolve it to ids FIRST and then send them, and
    that is not a workaround: an event names the rows it is about, so a predicate that
    nobody expanded would produce an event nobody can resolve.
    """
    import urllib.request

    url = base_url.rstrip("/") + DELETE_ROWS.format(table=table)
    send = opener()
    ids = [str(item) for item in row_ids]
    done, seconds = 0, []
    for start in range(0, len(ids), MAX_ROWS_PER_REQUEST):
        chunk = ids[start:start + MAX_ROWS_PER_REQUEST]
        body = json.dumps({"row_ids": chunk, "user_name": user_name}).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST", headers={"Content-Type": "application/json"})
        started = time.monotonic()
        with send.open(request, timeout=timeout) as response:
            response.read()
        seconds.append(time.monotonic() - started)
        done += len(chunk)
        log("  deleted %5d rows  %6.2fs" % (len(chunk), seconds[-1]))
    return {"rows": done, "requests": len(seconds),
            "seconds_total": round(sum(seconds), 2)}
