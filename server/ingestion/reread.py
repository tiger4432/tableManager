# -*- coding: utf-8 -*-
"""Pick ingestion log rows and hand them to the watcher to read again - the one selection the
retry-failed route and the retroactive «Re-read files» share (총괄 fab40ed69 ② · 976defaac).

The reading is always the watcher's: a row marked PENDING_RETRY is claimed by `run_watcher`'s
poller and read by `retry_one` on the table's own handler - from where the file lies (its
archive, or the external path it was read from), with the parser as it is now, dedup skipped.
"""
from __future__ import annotations

import os

#: The state that puts a row in the watcher's hands.
REREAD_STATUS = "PENDING_RETRY"
#: A row the watcher has not finished: still waiting, or claimed and being read.
IN_HAND = ("PENDING_RETRY", "PENDING")
#: What a re-read takes when no state is named: a file whose reading ended. PENDING and
#: PENDING_RETRY are in the watcher's hands already.
DEFAULT_REREAD_STATUSES = ("SUCCESS", "FAILED", "SKIPPED")
#: Rows one mark commits.
MARK_PAGE = 1000


def select_logs(db, statuses, table=None, folder=None, since=None, until=None, log_id=None):
    """-> [(log, its path below `folder`, or None without a folder)] - oldest first. The folder
    is a boundary (`C:\\a\\A` never takes `C:\\a\\AB`), case and separators as the filesystem
    reads them: the external-root judgement, `_safe_relative_path`."""
    from database import crud, models
    from directory_watcher import _safe_relative_path

    model = models.FileIngestionLog
    query = db.query(model).filter(model.status.in_(list(statuses)))
    if log_id is not None:
        query = query.filter(model.id == log_id)
    if not crud.is_blank_value(table):
        query = query.filter(model.table_name == table)
    if since is not None:
        query = query.filter(model.created_at >= since)
    if until is not None:
        query = query.filter(model.created_at < until)
    logs = query.order_by(model.id.asc()).all()
    if crud.is_blank_value(folder):
        return [(log, None) for log in logs]
    picked = []
    for log in logs:
        rel = _safe_relative_path(log.filepath, folder) if log.filepath else None
        if rel is not None:
            picked.append((log, rel))
    return picked


def by_top_folder(picked):
    """{the first folder below the chosen one, or "." : rows} - what a preview shows."""
    out = {}
    for _log, rel in picked:
        head = rel.split("/", 1)[0] if rel and "/" in rel else "."
        out[head] = out.get(head, 0) + 1
    return dict(sorted(out.items()))


def one_per_file(picked):
    """The newest row of each (table, file) - a file read twice has two rows, and is read again once."""
    newest = {}
    for log, rel in picked:
        newest[(log.table_name, os.path.normcase(os.path.abspath(log.filepath or "")))] = (log, rel)
    return sorted(newest.values(), key=lambda pair: pair[0].id)


def split_missing(picked):
    """-> (rows whose file is where the row says, rows whose file is gone)."""
    present, missing = [], []
    for log, rel in picked:
        (present if log.filepath and os.path.exists(log.filepath) else missing).append((log, rel))
    return present, missing


def mark_for_reread(db, logs, page=MARK_PAGE):
    """Hand `logs` to the watcher: PENDING_RETRY, a page a commit. -> [(id, the state it had)]."""
    marked = []
    for start in range(0, len(logs), page):
        for log in logs[start:start + page]:
            marked.append((log.id, log.status))
            log.status = REREAD_STATUS
        db.commit()
    return marked


def still_in_hand(db, ids):
    """How many of `ids` the watcher has not finished."""
    from database import models

    model = models.FileIngestionLog
    return sum(db.query(model).filter(model.id.in_(ids[start:start + MARK_PAGE]),
                                      model.status.in_(IN_HAND)).count()
               for start in range(0, len(ids), MARK_PAGE))


def restore_unread(db, marked):
    """Give each row of `marked` the watcher has not claimed yet (still PENDING_RETRY) its state
    back. A row being read (PENDING) is left to finish. -> how many were restored."""
    from database import models

    model = models.FileIngestionLog
    restored = 0
    for start in range(0, len(marked), MARK_PAGE):
        chunk = dict(marked[start:start + MARK_PAGE])
        for log in db.query(model).filter(model.id.in_(list(chunk)), model.status == REREAD_STATUS):
            log.status = chunk[log.id]
            restored += 1
        db.commit()
    return restored


def watcher_running():
    """Whether the watcher's heartbeat is fresh - the poller that reads marked rows beats it."""
    from directory_watcher import HEARTBEAT_NAME
    from utils import heartbeat

    beat = heartbeat.read_all().get(HEARTBEAT_NAME)
    return bool(beat) and not beat.get("stale")
