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

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)
_SOURCES, _SOURCES_LOCK = {}, threading.Lock()      # the validated sources this process holds - see validated_sources

#: The state that puts a row in the watcher's hands.
REREAD_STATUS = "PENDING_RETRY"
#: What the retry door takes when no state is named - today's answer, failed files.
RETRY_STATUSES = ("FAILED",)
#: Rows one mark commits.
MARK_PAGE = 1000
#: Files one retry may hand over unless ingestion_settings.json says `reread_max_files` (총괄 10-11 ㄱ): the busiest
#: minute of this box's watcher - 25 SUCCESS rows (file_ingestion_logs by updated_at minute, median 2).
REREAD_MAX_FILES_KEY = "reread_max_files"
REREAD_MAX_FILES_DEFAULT = 25
#: Entries one walk of a folder may look at before it is refused (총괄 10-20 ④) - a re-read into a table picks files
#: from the disk, and a share of hundreds of thousands of files would make one preview heavy.
WALK_MAX_ENTRIES = 100_000
#: `status_before` of a row the re-read stood itself (a file the table has no row for, 총괄 10-20 ①): «cancel» deletes
#: it - there is no state to put back.
STOOD_BY_REREAD = "STOOD"
#: Why a file under the folder is not the table's (the preview names both apart).
OUTSIDE_SOURCES = "outside the table's source folders"
NOT_MATCHED = "not matched by the source's glob or filename"
BEING_READ = "being read now"


#: The table_config cells that do not change how a table's files are read (lead 10-20 ab951f09b): the schema screen,
#: search and the layer ranking. Every other cell - today's and tomorrow's - is part of the reading.
NOT_READING = ("display_columns", "search_columns", "source_priority")
#: Each table's last reading, kept across the watcher's restarts beside the scheduler's status file - so a plugin fixed
#: while the watcher was down still hands its table's failed files at the start (lead 10-20).
READING_STAMPS_FILENAME = "watcher_reading_stamps.json"


def max_files():
    """The declared cap, or the default when it is absent or not a positive whole number."""
    from ingestion.settings import read_ingestion_settings

    value = read_ingestion_settings().get(REREAD_MAX_FILES_KEY)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else REREAD_MAX_FILES_DEFAULT


def over_the_limit(count, limit):
    """The refusal sentence when `count` files exceed `limit`, else None."""
    return ("%d files - over the limit %d; narrow the folder or raise %s in ingestion_settings.json"
            % (count, limit, REREAD_MAX_FILES_KEY)) if count > limit else None


def folder_roots(folder):
    """What a stored path below `folder` starts with as `path_key` spells it - the folder and its real path, lower
    case, one separator, a boundary; the longer first."""
    other = "/" if os.sep == "\\" else "\\"
    return sorted({os.path.normcase(root).lower().replace(other, os.sep).rstrip(os.sep) + os.sep
                   for root in (os.path.abspath(folder), os.path.realpath(os.path.abspath(folder)))},
                  key=lambda root: (-len(root), root))


def _under_folder(column, folder):
    """SQL: the stored path starts with one of `folder_roots`. A superset of `_safe_relative_path`'s answer, which
    still decides each row read."""
    from sqlalchemy import or_

    from database.models import path_key

    stored = path_key(column)
    return or_(*[stored.like(root.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%", escape="!")
                 for root in folder_roots(folder)])


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


def logs_query(db, statuses=None, table=None, folder=None, since=None, until=None, log_id=None, name=None):
    """The file log rows a re-read or a search names - one filter for both (총괄 e390600d6). `statuses` None: any;
    `folder` as `_under_folder` reads it; `name` a part of the file name, any case."""
    from sqlalchemy import func

    from database import crud, models

    model = models.FileIngestionLog
    query = db.query(model)
    if statuses is not None:
        query = query.filter(model.status.in_(list(statuses)))
    if log_id is not None:
        query = query.filter(model.id == log_id)
    if not crud.is_blank_value(table):
        query = query.filter(model.table_name == table)
    if since is not None:
        query = query.filter(model.created_at >= since)
    if until is not None:
        query = query.filter(model.created_at < until)
    if not crud.is_blank_value(folder):
        query = query.filter(_under_folder(model.filepath, folder))   # not the whole table into memory (총괄 10-11)
    if not crud.is_blank_value(name):
        part = str(name).strip().lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        query = query.filter(func.lower(model.filename).like("%" + part + "%", escape="!"))
    return query


def folder_of(filepath):
    """The folder a logged file sits in - each row's folder (총괄 e390600d6)."""
    return os.path.dirname(filepath) if filepath else None


def folder_key(filepath, spelled, roots):
    """The search's folder group (총괄 10-20) -> (key, label): below a chosen folder the first folder (`top_folder`)
    of what follows the root it was picked by - `spelled` is the path as `path_key` spells it, `roots` the folder's
    `folder_roots`; the label is the stored path's own spelling at that place. Without a folder (no roots), the file's
    own folder for both."""
    for root in roots:
        if spelled and spelled.startswith(root):
            key = top_folder(spelled[len(root):].replace(os.sep, "/"))
            same_place = len(filepath) == len(spelled)              # lower() kept every letter's place
            return key, top_folder(filepath[len(root):].replace("\\", "/")) if same_place else key
    return folder_of(filepath), folder_of(filepath)


def select_logs(db, statuses, table=None, folder=None, since=None, until=None, log_id=None):
    """-> [(log, its path below `folder`, or None without a folder)] - oldest first. The folder
    is a boundary (`C:\\a\\A` never takes `C:\\a\\AB`), case and separators as the filesystem
    reads them: the external-root judgement, `_safe_relative_path`."""
    from database import crud, models
    from directory_watcher import _safe_relative_path, one_sweep

    model = models.FileIngestionLog
    logs = logs_query(db, statuses, table, folder, since, until, log_id).order_by(model.id.asc()).all()
    if crud.is_blank_value(folder):
        return [(log, None) for log in logs]
    picked = []
    with one_sweep():
        for log in logs:
            rel = _safe_relative_path(log.filepath, folder) if log.filepath else None
            if rel is not None:
                picked.append((log, rel))
    return picked


def reading_of(table, entry, sources, scripts_dir):
    """What decides how `table`'s files are read, as {part: stamp} - its table_config entry without `NOT_READING`, its
    external sources (`table_name` is the table) and each plugin file in its scripts folder (mtime_ns, size)."""
    import hashlib
    import json

    def digest(value):
        return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

    parts = {"table_config": digest({k: v for k, v in (entry or {}).items() if k not in NOT_READING}),
             "external source": digest(sorted((s for s in sources or () if isinstance(s, dict)
                                               and s.get("table_name") == table), key=digest))}
    try:
        names = sorted(n for n in os.listdir(scripts_dir) if n.endswith(".py") and n != "__init__.py")
    except OSError:
        names = []
    for name in names:
        try:
            stat = os.stat(os.path.join(scripts_dir, name))
        except OSError:
            continue
        parts["scripts\\" + name] = [stat.st_mtime_ns, stat.st_size]
    return parts


def hand_on_a_changed_reading(db, table, before, now):
    """The table's failed files handed to the watcher again (`mark_for_reread`, the retry door's mark) when its reading
    changed - up to `max_files()`; past it, one line and nothing handed. -> the line said, or None."""
    changed = sorted(part for part in set(before) | set(now) if before.get(part) != now.get(part))
    if not changed:
        return None
    logs = [log for log, _rel in select_logs(db, RETRY_STATUSES, table=table)]
    if not logs:
        return None
    what, limit = ", ".join(changed), max_files()
    if len(logs) > limit:
        line = ("[Watcher] %s: its reading changed (%s) - %d failed files wait - Retry failed by folder (over %s %d)"
                % (table, what, len(logs), REREAD_MAX_FILES_KEY, limit))
        logger.warning(line)
        return line
    mark_for_reread(db, logs)
    line = "[Watcher] %s: its reading changed (%s) - %d failed file(s) handed again" % (table, what, len(logs))
    logger.info(line)
    return line


def load_reading_stamps():
    """{table: reading} as last kept, {} when there is none or it cannot be read."""
    import json

    import paths

    try:
        with open(paths.config_path(READING_STAMPS_FILENAME), encoding="utf-8") as handle:
            kept = json.load(handle)
        return kept if isinstance(kept, dict) else {}
    except (OSError, ValueError):
        return {}


def keep_reading_stamps(stamps):
    """Write {table: reading} whole (a temporary file, then a replace)."""
    import json

    import paths

    path = paths.config_path(READING_STAMPS_FILENAME)
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(stamps, handle, ensure_ascii=False, sort_keys=True)
    os.replace(path + ".tmp", path)


class RereadRefused(ValueError):
    """A re-read the door will not hand over - the sentence says why and what to do."""


def validated_sources():
    """(table_config, every external source as `validate_external_source_specs` - the watcher's registration - answers)
    held by this process: validated again only when table_config.json or ingestion_settings.json changes stamp, or
    after a reload (`forget_sources`). Judging a source resolves its root, and one unreachable share root cost every
    preview 21 s (총괄 10-20, 소유자 「시작할 때 안 읽는 거는」); the API's start fills it."""
    import paths
    from directory_watcher import (INGESTION_SETTINGS_PATH, load_global_table_config, load_ingestion_settings,
                                   validate_external_source_specs)
    from ledger.setup import file_stamp

    stamp = (file_stamp(paths.config_path("table_config.json")), file_stamp(INGESTION_SETTINGS_PATH))
    with _SOURCES_LOCK:
        if _SOURCES.get("stamp") != stamp:
            config = load_global_table_config()
            specs, _errors = validate_external_source_specs(load_ingestion_settings(), config, paths.WORKSPACE_DIR)
            _SOURCES.update(stamp=stamp, config=config, specs=specs)
        return _SOURCES["config"], _SOURCES["specs"]


def forget_sources():
    """A reload's seat: the next preview validates the sources again."""
    with _SOURCES_LOCK:
        _SOURCES.clear()


def table_sources(table):
    """(the table's raws folder, its external sources) as the watcher registers them (`raws_root_for` ·
    `_register_external_sources`) - the handler that will read the files holds exactly these."""
    import paths
    from directory_watcher import resolve_workspace_root

    config, specs = validated_sources()
    raws = os.path.abspath(os.path.join(resolve_workspace_root(paths.WORKSPACE_DIR, table, config), "raws"))
    return raws, [spec for spec in specs if spec["table_name"] == table]


def select_files(db, table, folder, limit=None):
    """The files on the disk under `folder` that `table` takes - a re-read into a table (총괄 10-20, 소유자 「어드민 파일
    리트라이는 돌았던 테이블로만 도네」): by the disk, not by the log, so a file no row of the table names is picked too.
    Taken = under the table's raws, or taken by one of its external sources (`directory_watcher.source_taking`, the
    handler's own judgement). -> {"picked": [(the table's newest row for the file or None, its path below the folder,
    the file)], "not_taken": {why: count}, "not_taken_files": [first names], "walked": files looked at}.
    More than `limit` files under the folder is refused (RereadRefused) before anything is judged."""
    from directory_watcher import _safe_relative_path, one_sweep, source_taking

    limit = WALK_MAX_ENTRIES if limit is None else limit
    began = clock = time.perf_counter()
    took = {}

    def stage(name):
        nonlocal clock
        now = time.perf_counter()
        took[name], clock = round(now - clock, 3), now

    files, folders = [], 0
    for top, _dirs, names in os.walk(folder):
        folders += 1
        for name in names:
            files.append(os.path.join(top, name))
            if len(files) > limit:
                raise RereadRefused("more than %d files under %s - narrow the folder" % (limit, folder))
    stage("walk")
    raws, specs = table_sources(table)
    stage("sources")
    rows = _newest_rows_of(db, table, files)
    stage("lookup")
    picked, not_taken, names = [], {}, []
    with one_sweep():
        for path in sorted(files):
            why = None
            if _safe_relative_path(path, raws) is None and source_taking(specs, path) is None:
                why = NOT_MATCHED if any(_safe_relative_path(path, spec["root"]) is not None for spec in specs) \
                    else OUTSIDE_SOURCES
            log = rows.get(os.path.normcase(os.path.abspath(path)))
            if why is None and log is not None and log.status == "PENDING":
                why = BEING_READ
            if why is not None:
                not_taken[why] = not_taken.get(why, 0) + 1
                names.append(os.path.basename(path))
                continue
            picked.append((log, _safe_relative_path(path, folder), path))
    stage("judge")
    took["total"] = round(time.perf_counter() - began, 3)
    logger.info("[Reread] preview of %s for %s: %d file(s) in %d folder(s), %d picked - %.1f s (walk %.1f · sources "
                "%.1f · lookup %.1f · judge %.1f)", folder, table, len(files), folders, len(picked), took["total"],
                took["walk"], took["sources"], took["lookup"], took["judge"])
    return {"picked": picked, "not_taken": dict(sorted(not_taken.items())), "not_taken_files": names[:5],
            "walked": len(files), "folders": folders, "took": took}


def _newest_rows_of(db, table, files):
    """{a path as the filesystem compares it: the table's newest row for it} for the rows named as `files` are - looked up
    by name (`ix_file_ingestion_logs_filename`), the caller matching the path: a path filter on the table's whole
    history read every row of it (총괄 f5280f794)."""
    from database import models
    from ingestion.file_ingestion_status import FILE_INGESTION_STATUS_VOCABULARY

    model = models.FileIngestionLog
    names = sorted({os.path.basename(path) for path in files})
    rows = {}
    for start in range(0, len(names), MARK_PAGE):
        for log in (db.query(model).filter(model.table_name == table, model.filename.in_(names[start:start + MARK_PAGE]),
                                           model.status.in_(list(FILE_INGESTION_STATUS_VOCABULARY)))
                    .order_by(model.id.asc())):
            rows[os.path.normcase(os.path.abspath(log.filepath or ""))] = log   # oldest first: the newest stays
    return rows


def stand_rows(db, table, picked, folder=None):
    """A row for each picked file the table has none for - PENDING_RETRY at once, its mark saying the re-read stood it
    (`STOOD_BY_REREAD` - «cancel» deletes it). -> (the table's rows the picked files had, the rows stood)."""
    from database import models

    logs = [log for log, _rel, _path in picked if log is not None]
    stood = []
    for _log, _rel, path in (item for item in picked if item[0] is None):
        row = models.FileIngestionLog(filename=os.path.basename(path), filepath=path, table_name=table,
                                      status=REREAD_STATUS)
        db.add(row)
        stood.append(row)
    db.flush()
    for row in stood:
        db.add(models.FileRereadMark(log_id=row.id, status_before=STOOD_BY_REREAD, folder=folder))
    db.commit()
    return logs, stood


def top_folder(rel):
    """The first folder of a path below the chosen folder, "." for a file right in it."""
    return rel.split("/", 1)[0] if rel and "/" in rel else "."


def by_top_folder(picked):
    """{the first folder below the chosen one, or "." : rows} - what a preview shows."""
    out = {}
    for _log, rel in picked:
        head = top_folder(rel)
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


def mark_for_reread(db, logs, page=MARK_PAGE, folder=None):
    """Hand `logs` to the watcher: PENDING_RETRY, a page a commit, each row's state before it kept in
    `file_reread_marks` (a row already waiting keeps the state it had first). -> [(id, the state it had)]."""
    from database import models

    marked = []
    for start in range(0, len(logs), page):
        for log in logs[start:start + page]:
            marked.append((log.id, log.status))
            if log.status != REREAD_STATUS or db.get(models.FileRereadMark, log.id) is None:
                db.merge(models.FileRereadMark(log_id=log.id, status_before=log.status, folder=folder))
            log.status = REREAD_STATUS
        db.commit()
    return marked


def cancel_reread(db, folder=None, apply=False):
    """Put the rows still waiting under `folder` (every waiting row without one) back to the state they had before
    the re-read handed them over; a row the watcher has claimed is no longer waiting and is not touched, and a waiting
    row with no mark is left and counted; a row the re-read stood itself (`STOOD_BY_REREAD`) is deleted - it had no
    state. -> {"count" (put back), "removed" (stood rows deleted), "by_state", "unmarked"}."""
    from database import models

    waiting = [log for log, _rel in select_logs(db, (REREAD_STATUS,), folder=folder)]
    marks = {mark.log_id: mark for mark in db.query(models.FileRereadMark).filter(
        models.FileRereadMark.log_id.in_([log.id for log in waiting]))} if waiting else {}
    back = [(log, marks[log.id].status_before) for log in waiting if log.id in marks]
    by_state = {}
    for _log, state in back:
        if state != STOOD_BY_REREAD:
            by_state[state] = by_state.get(state, 0) + 1
    if apply:
        for start in range(0, len(back), MARK_PAGE):
            for log, state in back[start:start + MARK_PAGE]:
                if state == STOOD_BY_REREAD:
                    db.delete(log)
                else:
                    log.status = state
                db.delete(marks[log.id])
            db.commit()
    removed = sum(1 for _log, state in back if state == STOOD_BY_REREAD)
    return {"count": len(back) - removed, "removed": removed, "by_state": dict(sorted(by_state.items())),
            "unmarked": len(waiting) - len(back)}
