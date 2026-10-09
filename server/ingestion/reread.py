# -*- coding: utf-8 -*-
"""Pick ingestion log rows and hand them to the watcher to read again - the selection of the one
door that does it, POST /admin/file-ingestion/retry-failed (총괄 fab40ed69 ② · a4d135a06): failed
files, or with `statuses` files that went in - a re-read with today's parser.

The reading is always the watcher's: a row marked PENDING_RETRY is claimed by `run_watcher`'s
poller and read by `retry_one` on the table's own handler - from where the file lies (its
archive, or the external path it was read from), with the parser as it is now, dedup skipped.
⚰️ The retroactive «Re-read files» (976defaac) is retired: it put a run, the operations gate and a
wait page by page on top of this mark, and did not run in production (총괄 a4d135a06).
"""
from __future__ import annotations

import os

#: The state that puts a row in the watcher's hands.
REREAD_STATUS = "PENDING_RETRY"
#: What the retry door takes when no state is named - today's answer, failed files.
RETRY_STATUSES = ("FAILED",)
#: Rows one mark commits.
MARK_PAGE = 1000


def states_of(text):
    """The `statuses` a request names (comma-separated) - `RETRY_STATUSES` when it names none; a
    word that is no ingestion state is refused by name (ValueError)."""
    from database import crud
    from ingestion.file_ingestion_status import FILE_INGESTION_STATUS_VOCABULARY

    states = tuple(dict.fromkeys(s.strip() for s in str(text or "").split(",") if not crud.is_blank_value(s)))
    unknown = [s for s in states if s not in FILE_INGESTION_STATUS_VOCABULARY]
    if unknown:
        raise ValueError(f"statuses {unknown} are not ingestion states - "
                         f"{', '.join(FILE_INGESTION_STATUS_VOCABULARY)}")
    return states or RETRY_STATUSES


def times_of(since, until):
    """`since` · `until` (ingested at or after · before) as datetimes, None when blank; a value
    that is no date or time is refused by name (ValueError)."""
    from datetime import datetime

    from database import crud

    out = []
    for name, value in (("since", since), ("until", until)):
        if crud.is_blank_value(value):
            out.append(None)
            continue
        try:
            out.append(datetime.fromisoformat(str(value).strip()))
        except ValueError:
            raise ValueError(f"{name} is not a date or a time: {value!r} - write YYYY-MM-DD "
                             f"or YYYY-MM-DD HH:MM") from None
    return tuple(out)


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
