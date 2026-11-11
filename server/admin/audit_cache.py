"""The in-memory projection behind `GET /audit_logs/recent` - the newest transaction groups of `audit_batches` (a
cell's lines) and of the `audit_logs` rows that are no cell's change (`is_event`: a ledger or formula receipt, a
table-wide record - owner 11-11 ㄱ «audit_logs 는 셀 아닌 사건의 표로 남고, 이력 화면에 보인다»).

A group is a transaction (`group_of` - a replay's pages are one group). Per table it shows the kinds and the writers
as written, the newest time, the batches' count, and the rows it changed - counted from the table's lines
(`audit_history.changed_rows`), None for a relation without lines (`lines.has_lines`); and its events - how many,
their columns, the newest one (`_event_facts`).

    walk     newest first by (at, id) - the (at, id) index - in chunks, until `limit_groups` groups; a page after a
             cursor resumes below it and drops the groups with a batch at or above it (an earlier page named them);
             the batches and the events each walked so, the groups of both kept by their newest
             ⚠️ a cursor's (at, id) is one table's id: two records of two tables at the same instant tie by id
    behind   the walk and the merge of later batches run behind the reads, one at a time (`behind`, owner 11-09
             «읽기는 쓰기에 영향 안 받음»); a notification's `changed` reaches the list at once (`add_changed`) and
             the next merge reads its groups again whole, so a count is never added twice
    bounds   each statement `recent_statement_seconds` (PostgreSQL cancels it), each walk or merge
             `recent_walk_seconds`, a walk `recent_max_scan_rows` - past one: what was named, `truncated`, one line
"""
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import error_said
import event_constants
from admin import audit_history
from database import lines, models

logger = logging.getLogger("Server")

# Every knob is a DEFAULT that `audit_history_config.json` overrides - the file the row/cell history reads too.
RECENT_DEFAULTS = {
    "recent_max_scan_rows": 500_000,        # batches a walk reads at most before it says truncated
    "recent_scan_chunk_rows": 20_000,       # batches a statement reads; a merge's slice
    "recent_statement_seconds": 5,          # 🔴 owner 11-06 «STALL 303s P /audit_logs/recent»: never holds the server
    "recent_walk_seconds": 10,
}
#: A read starts the walk or the merge behind it when none runs and the last ended at least this long ago - well past
#: the screen's read-again after `updating` (timeline HISTORY_REREAD_MS, 2 s; Chrome look 11-09).
CATCH_UP_GAP_SECONDS = 10
#: Groups a notification keeps on the list (`add_changed`) - the route's default page.
LIVE_GROUPS = 100
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def is_event(column):
    """SQL: an `audit_logs` row is no cell's change - its column is a receipt's (`crud.receipt_log`: a ledger or formula
    batch) or "*" (a table-wide record: set_aside's skips, replay's full reset). The one seat that asks it.

    ⚠️ A row's table would say it alone once audit_logs holds no cell's line. Five writers still write one there -
    replay._write_resolved · _fold_units_page · crud.row_update_line, apply_row_update_internal · _merge_into_key_holder
    (the 11-14 count gate asks 0 of them, A · B). When they are gone, every audit_logs row is an event: this function
    goes and the walk reads the table (lead 11-11 ㄱ)."""
    from ledger.runtime_v2 import RECEIPT_COLUMN

    return column.in_((RECEIPT_COLUMN, "*"))


def _batches():
    """The cell lines' walk: (group label, time, id, which)."""
    b = lines.AuditBatch
    return b.transaction_id, b.at, b.id, b.at.isnot(None)


def _events():
    """The events' walk (`is_event`): (group label, time, id, which)."""
    e = models.AuditLog
    return e.transaction_id, e.timestamp, e.id, is_event(e.column_name)


def resolve_recent_settings(config: dict = None) -> dict:
    """Every knob, usable: a malformed one falls back to its default with a warning."""
    declared = config if isinstance(config, dict) else audit_history.load_config()
    resolved = dict(RECENT_DEFAULTS)
    for key, default in RECENT_DEFAULTS.items():
        if key not in declared:
            continue
        value = declared[key]
        # bool is a subclass of int - True must not silently become 1.
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            print(f"[AuditCache] '{key}' must be a positive integer "
                  f"(got {value!r}); using {default}.")
            continue
        resolved[key] = value
    return resolved


class AuditLogCache:
    """The newest groups, newest first; one process's, thread-safe."""

    def __init__(self):
        self.groups: List[Dict] = []
        self.is_loaded = False
        self._lock = threading.Lock()
        # One rebuild at a time, and not under `_lock` (총괄 10-22: a rebuild under it held every notification).
        self._build_lock = threading.Lock()
        self._batch_max_id = None           # every audit batch at or below this id is in the projection
        self._event_max_id = None           # every audit_logs row at or below this id is (`is_event`)
        self.truncated = False
        self.next_cursor: Optional[str] = None
        self.scanned_rows = 0
        self._behind: Optional[threading.Thread] = None
        self._behind_ended = float("-inf")

    def _discover(self, db: Session, limit_groups: int, settings: dict, start: Optional[str] = None):
        """The groups of a page. -> (groups, truncated, next_cursor, scanned, cut)"""
        floor = audit_history.decode_cursor(start) if start else None
        keys, more, scanned, cut = _walk(db, _batches(), floor, limit_groups, settings)
        named, more_events, read, cut_events = _walk(db, _events(), floor, limit_groups, settings)
        groups = sorted(_groups(db, list(dict.fromkeys(keys + named))), key=_group_newest, reverse=True)
        more = more or more_events or len(groups) > limit_groups
        groups = groups[:limit_groups]
        cursor = None
        if more and groups:
            cursor = audit_history.encode_cursor(*_group_newest(groups[-1]))
        return groups, more, cursor, scanned + read, cut or cut_events

    def page_from_cursor(self, db: Session, cursor: str, limit_groups: int = 100):
        """The groups AFTER `cursor`, as `(groups, truncated, next_cursor, scanned)` - the same walk, a one-shot answer
        that does not touch the projection (page 1 is what the panel and the live merges share)."""
        settings = resolve_recent_settings()
        with _bounded(db, settings):
            groups, truncated, nxt, scanned, _cut_at = self._discover(db, limit_groups, settings, start=cursor)
            return groups, truncated, nxt, scanned

    def load_initial(self, db: Session, limit_groups: int = 100, force: bool = False, refresh_above: int = None):
        """Build the projection. The walk runs outside `_lock` - only the swap is inside; one builder at a time.
        `refresh_above`: the batch id a caller saw before it asked for a rebuild - a builder already past it leaves."""
        def done():
            return self.is_loaded and (not force or (
                refresh_above is not None and (self._batch_max_id or 0) >= refresh_above))

        with self._lock:
            if done():
                return
            loaded = self.is_loaded
        if not self._build_lock.acquire(blocking=not loaded):
            return                              # another request builds; this one answers the projection there is
        try:
            with self._lock:
                if done():
                    return
            settings = resolve_recent_settings()
            with _bounded(db, settings):
                try:
                    # 🔴 Read BEFORE the walk: a batch committed during it stays above the watermark for the merge.
                    watermark, events_mark = _newest_ids(db)
                    groups, truncated, cursor, scanned, cut = self._discover(db, limit_groups, settings)
                except OperationalError as exc:
                    if not _cut(exc):
                        raise
                    logger.warning("[Audit] recent walk cut - the newest id or the groups' facts past "
                                   "recent_statement_seconds %d; not loaded, the next read walks again",
                                   settings["recent_statement_seconds"])
                    return
            if cut and not groups:
                return                          # nothing named: the next read walks again rather than show none
            with self._lock:
                self.groups = groups
                self.is_loaded = True
                self._batch_max_id, self._event_max_id = watermark, events_mark
                self.truncated = truncated
                self.next_cursor = cursor
                self.scanned_rows = scanned
        finally:
            self._build_lock.release()

    def behind(self, bind, limit_groups: int = 100) -> bool:
        """Start the walk or the merge behind the read on a session of its own on `bind` when none runs and the last
        ended `CATCH_UP_GAP_SECONDS` ago. -> whether one runs, or none has built the projection yet - the answer's
        `updating`: never «no history» for «not read yet»."""
        from sqlalchemy.orm import sessionmaker

        with self._lock:
            if (self._behind is None or not self._behind.is_alive()) and (
                    time.monotonic() - self._behind_ended >= CATCH_UP_GAP_SECONDS):
                self._behind = threading.Thread(target=self._catch_up, args=(sessionmaker(bind=bind), limit_groups),
                                                name="audit-recent", daemon=True)
                self._behind.start()
            return not self.is_loaded or (self._behind is not None and self._behind.is_alive())

    def _catch_up(self, session_factory, limit_groups: int):
        """The walk, then the merge; over the slow-request budget it says where its time went."""
        from runtime import request_timing

        db = session_factory()
        try:
            began = time.monotonic()
            self.load_initial(db, limit_groups)
            walked = time.monotonic()
            self.refresh_if_stale(db, limit_groups)
            ended, budget = time.monotonic(), request_timing.slow_request_ms()
            if budget is not None and (ended - began) * 1000 > budget:
                logger.warning("[Slow] recent history behind the reads - %.2f s (budget %d ms) · walk %.2f s · "
                               "merge %.2f s", ended - began, budget, walked - began, ended - walked)
        except Exception as exc:                                # noqa: BLE001 - the next read starts another
            logger.warning("[Audit] recent history not caught up - the next read tries again: %s",
                           error_said.told(exc))
        finally:
            db.close()
            with self._lock:
                self._behind_ended = time.monotonic()

    def refresh_if_stale(self, db: Session, limit_groups: int = 100) -> bool:
        """Merge the batches committed since the projection read them (other processes, and what a notification
        already showed) in id slices of `recent_scan_chunk_rows`, each moving the watermark; past
        `recent_walk_seconds` or a statement past its limit, the rest is the next read's. -> whether any came"""
        settings = resolve_recent_settings()
        merged, started, step, latest = False, time.monotonic(), "the newest id", None
        with _bounded(db, settings):
            try:
                latest = _newest_ids(db)
                while True:
                    with self._lock:
                        previous = (self._batch_max_id or 0, self._event_max_id or 0)
                        if not self.is_loaded or all(new <= old for new, old in zip(latest, previous)):
                            return merged
                    if time.monotonic() - started > settings["recent_walk_seconds"]:
                        step = "past recent_walk_seconds %d" % settings["recent_walk_seconds"]
                        break
                    step = "a slice"
                    one = self._merge(db, previous, tuple(min(new, old + settings["recent_scan_chunk_rows"])
                                                          for new, old in zip(latest, previous)), limit_groups)
                    if one is None:
                        return merged
                    merged = merged or one
            except OperationalError as exc:
                if not _cut(exc):
                    raise
                step = "%s past recent_statement_seconds %d" % (step, settings["recent_statement_seconds"])
        with self._lock:
            left = "?" if latest is None else "%d · %d" % (latest[0] - (self._batch_max_id or 0),
                                                         latest[1] - (self._event_max_id or 0))
        logger.warning("[Audit] recent merge cut at %d s - %s; %s batch · audit_logs id(s) left for the next read",
                       time.monotonic() - started, step, left)
        return merged

    def _merge(self, db: Session, previous: tuple, latest: tuple, limit_groups: int):
        """One slice `(previous, latest]` of the batches' ids and of audit_logs' (`_newest_ids`): its groups read again
        whole, each to the top, the watermarks to `latest`. -> whether it held batches or events, or None when another
        merge or a rebuild moved a watermark meanwhile."""
        keys = []
        for (label, _at, row_id, which), old, new in zip((_batches(), _events()), previous, latest):
            keys += [tid for (tid,) in db.query(label).filter(row_id > old, row_id <= new, which)]
        keys = list(dict.fromkeys(group_of(tid) for tid in keys))
        touched = sorted(_groups(db, keys), key=_group_newest, reverse=True)[:limit_groups]
        with self._lock:
            if (self._batch_max_id or 0, self._event_max_id or 0) != previous:
                return None
            for group in reversed(touched):           # the newest ends on top
                self._to_top(group, limit_groups)
            self._batch_max_id, self._event_max_id = latest
        return bool(keys)

    def add_changed(self, items):
        """A notification's `changed` ([{transaction_id, table_name, changed_rows, kind, written_by?}] - one write
        statement's share each) on the list at once: its group to the top, the share added to its table. An
        approximation until the next merge reads the group's batches again whole."""
        if not items:
            return
        with self._lock:
            if not self.is_loaded:
                return
            now = datetime.now(timezone.utc)
            for item in items:
                key = group_of(item.get("transaction_id"))
                group = next((g for g in self.groups if g["transaction_id"] == key),
                             {"transaction_id": key, "tables": {}, "changed": {}})
                name = item.get("table_name")
                one = group["tables"].setdefault(name, _fresh_table())
                _said(one, item.get("kind"), item.get("written_by"), now, one["id"])
                if item.get("changed_rows") is not None:
                    group["changed"][name] = (group["changed"].get(name) or 0) + int(item["changed_rows"])
                self._to_top(group, LIVE_GROUPS)

    def _to_top(self, group: dict, limit_groups: int):
        """`group` first - replacing the one of its key -, the list cut at `limit_groups` (under `_lock`)."""
        self.groups = [group] + [g for g in self.groups if g["transaction_id"] != group["transaction_id"]]
        if len(self.groups) > limit_groups:
            del self.groups[limit_groups:]
            # The list now ends earlier than the walk that built it: «there is more», and its position is gone.
            self.truncated, self.next_cursor = True, None


def _cut(exc) -> bool:
    """Whether `exc` is PostgreSQL cancelling a statement past its `statement_timeout`."""
    import db_waits
    return getattr(getattr(exc, "orig", None), "pgcode", None) == db_waits.QUERY_CANCELED


@contextmanager
def _bounded(db: Session, settings):
    """The walk's or the merge's statements in a transaction of their own under `recent_statement_seconds`
    (`database.context.read_limit` - SET LOCAL at the transaction's begin), ended after so the limit goes with it.
    Nothing here writes, so both ends are rollbacks."""
    from database.context import read_limit

    db.rollback()
    try:
        with read_limit(settings["recent_statement_seconds"]):
            yield
    finally:
        db.rollback()


def group_of(transaction_id) -> str:
    """The history group an audit label belongs to - the one answer the walk, the merges and the detail route ask.
    A label's part after `GROUP_PART` is one commit of its group (a replay page, 총괄 ㄴ 10-21), so a run is one
    line with its pages inside. No label is the one pseudo-group `no_tid`."""
    if not transaction_id:
        return "no_tid"
    return transaction_id.split(event_constants.GROUP_PART, 1)[0]


def in_group(column, key):
    """The rows of history group `key`, as a filter - `group_of` read backwards."""
    if key == "no_tid":
        return sa.or_(column.is_(None), column == "")
    return sa.or_(column == key, column.startswith(key + event_constants.GROUP_PART, autoescape=True))


def _aware(at: datetime) -> datetime:
    """A batch time comparable with another - SQLite hands a timezone column back without its zone, stored as UTC."""
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at


def _newest(tables: dict):
    """A group's newest batch position `(at, id)` over its tables, `(_EPOCH, 0)` with none."""
    return max(((_aware(one["at"] or _EPOCH), one["id"]) for one in tables.values()), default=(_EPOCH, 0))


def _group_newest(group: dict):
    """A group's newest position `(at, id)` - its batches' or its newest event's."""
    events = group.get("events")
    return max(_newest(group["tables"]), (_aware(events["at"]), events["id"]) if events else (_EPOCH, 0))


def _groups(db: Session, keys) -> List[dict]:
    """The groups `keys` as the projection holds them: their batches' facts, rows changed and events."""
    facts = _batch_facts(db, keys)
    changed = _changed(db, facts)
    events = _event_facts(db, keys)
    return [{"transaction_id": key, "tables": facts.get(key, {}), "changed": changed.get(key, {}),
             "events": events.get(key)} for key in keys]


def _newest_ids(db: Session) -> tuple:
    """(the newest audit batch id, the newest audit_logs id) - the watermarks a merge reads above."""
    return (db.query(func.max(lines.AuditBatch.id)).scalar() or 0,
            db.query(func.max(models.AuditLog.id)).scalar() or 0)


def _fresh_table() -> dict:
    return {"kinds": [], "written_by": [], "at": None, "id": 0, "records": 0}


def _said(one: dict, kind, who, at, batch_id):
    """One batch of a table into its facts - kinds and writers in the order first written, the newest time."""
    one["records"] += 1
    for listed, word in ((one["kinds"], kind), (one["written_by"], who)):
        if word and word not in listed:
            listed.append(word)
    one["at"], one["id"] = at, batch_id


def _walk(db: Session, source, floor, limit_groups: int, settings: dict):
    """The newest `limit_groups` groups `source` (`_batches` | `_events`) names, newest first by (at, id), below `floor`
    (a page's cursor) and without the groups seen at or above it. -> (keys, there are more, records read, cut or None)"""
    label, at, row_id, which = source
    keys, skipped, position, scanned, started = [], set(), floor, 0, time.monotonic()
    step = "a chunk"
    try:
        while scanned < settings["recent_max_scan_rows"]:
            if time.monotonic() - started > settings["recent_walk_seconds"]:
                return _said_cut(keys, scanned, started, "past recent_walk_seconds %d" % settings["recent_walk_seconds"])
            want = min(settings["recent_scan_chunk_rows"], settings["recent_max_scan_rows"] - scanned)
            q = db.query(label, at, row_id).filter(which)
            if position is not None:
                q = q.filter(sa.tuple_(at, row_id) < sa.tuple_(*position))
            step = "a chunk"
            rows = q.order_by(at.desc(), row_id.desc()).limit(want).all()
            met = [key for key in dict.fromkeys(group_of(tid) for tid, _at, _id in rows)
                   if key not in keys and key not in skipped]
            if floor is not None and met:
                step = "the groups an earlier page named"
                seen = _seen_at_or_above(db, floor, met)
                skipped |= seen
                met = [key for key in met if key not in seen]
            for key in met:
                if len(keys) == limit_groups:
                    return keys, True, scanned + len(rows), None
                keys.append(key)
            scanned += len(rows)
            if len(rows) < want:
                return keys, False, scanned, None
            position = (rows[-1][1], rows[-1][2])
        return keys, True, scanned, None
    except OperationalError as exc:
        if not _cut(exc):
            raise
        db.rollback()
        return _said_cut(keys, scanned, started, "%s past recent_statement_seconds %d" % (
            step, settings["recent_statement_seconds"]))


def _said_cut(keys, scanned, started, why):
    logger.warning("[Audit] recent walk cut at %d s - %s; answered %d group(s), truncated",
                   time.monotonic() - started, why, len(keys))
    return keys, True, scanned, why


def _seen_at_or_above(db: Session, floor, keys) -> set:
    """Of the groups `keys`, those with a batch or an event at or above `floor` - named by an earlier page. One
    statement each."""
    seen = set()
    for label, at, row_id, which in (_batches(), _events()):
        seen |= {group_of(tid) for (tid,) in db.query(label).filter(
            which, sa.tuple_(at, row_id) >= sa.tuple_(*floor), sa.or_(*[in_group(label, key) for key in keys]))
            .distinct()}
    return seen


def _batch_facts(db: Session, keys) -> Dict[str, dict]:
    """{group: {table: {"kinds", "written_by", "at", "id", "records"}}} - every batch of the groups `keys`. One
    statement."""
    if not keys:
        return {}
    b = lines.AuditBatch
    facts = {}
    for tid, name, who, kind, at, batch_id in db.query(
            b.transaction_id, b.table_name, b.written_by, b.work_kind, b.at, b.id).filter(
            sa.or_(*[in_group(b.transaction_id, key) for key in keys])).order_by(b.at.asc(), b.id.asc()):
        _said(facts.setdefault(group_of(tid), {}).setdefault(name, _fresh_table()), kind, who, at, batch_id)
    return facts


def _event_facts(db: Session, keys) -> Dict[str, dict]:
    """{group: {"count", "columns", "log", "at", "id"}} - the events of the groups `keys` (`is_event`): how many, their
    columns in the order first written, the newest as a log row. One statement."""
    if not keys:
        return {}
    e = models.AuditLog
    facts = {}
    for log in db.query(e).filter(is_event(e.column_name), sa.or_(*[in_group(e.transaction_id, key) for key in keys])
                                  ).order_by(e.timestamp.asc(), e.id.asc()):
        one = facts.setdefault(group_of(log.transaction_id), {"count": 0, "columns": []})
        one["count"] += 1
        if log.column_name not in one["columns"]:
            one["columns"].append(log.column_name)
        one.update(log=log_row(log), at=log.timestamp, id=log.id)
    return facts


def log_row(log) -> dict:
    """An audit_logs row as the panel's `logs` carry it (`schemas.AuditLogResponse`)."""
    return {name: getattr(log, name) for name in ("id", "table_name", "row_id", "column_name", "new_value",
                                                  "source_name", "updated_by", "transaction_id", "business_key",
                                                  "timestamp")}


def _changed(db: Session, facts) -> Dict[str, dict]:
    """{group: {table: rows changed}} - counted from each table's lines; None for a relation without lines."""
    lined = {}
    out = {}
    for key, tables in facts.items():
        for name in tables:
            if name not in lined:
                lined[name] = lines.has_lines(db, name)
            out.setdefault(key, {})[name] = audit_history.changed_rows(db, name, key) if lined[name] else None
    return out


audit_cache = AuditLogCache()
