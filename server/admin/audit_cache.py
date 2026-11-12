"""The in-memory projection behind `GET /audit_logs/recent` - the newest transaction groups of `audit_batches`
(cell-source overhaul «감사 로그», owner 11-10 ㄱ: every audit record is a batch; audit_logs retires).

A group is a transaction (`group_of` - a replay's pages are one group). Per table it shows the kinds and the writers
as written, the newest time, the batches' count, and the rows it changed - counted from the table's lines
(`audit_history.changed_rows`), None for a relation without lines (`lines.has_lines`).

    walk     newest first by (at, id) - the (at, id) index - in chunks, until `limit_groups` groups; a page after a
             cursor resumes below it and drops the groups with a batch at or above it (an earlier page named them)
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

import db_waits
import error_said
import event_constants
from admin import audit_history
from runtime import behind
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
#: The one key of the recent history's work behind the reads (`runtime.behind`).
RECENT = "recent"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


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
        self.truncated = False
        self.next_cursor: Optional[str] = None
        self.scanned_rows = 0
        # the walk or the merge behind the reads (`runtime.behind`) - a restart's leaves nothing due
        if getattr(self, "_behind", None) is not None:
            self._behind.forget()
        self._behind = behind.Behind("audit-recent", lambda: CATCH_UP_GAP_SECONDS,
                                     "[Audit] the %s history was not caught up")

    def _discover(self, db: Session, limit_groups: int, settings: dict, start: Optional[str] = None):
        """The groups of a page. -> (groups, truncated, next_cursor, scanned, cut)"""
        floor = audit_history.decode_cursor(start) if start else None
        keys, more, scanned, cut = _batch_walk(db, floor, limit_groups, settings)
        facts = _batch_facts(db, keys)
        changed = _changed(db, facts)
        groups = [{"transaction_id": key, "tables": facts.get(key, {}), "changed": changed.get(key, {})}
                  for key in keys]
        cursor = None
        if more and keys:
            at, batch_id = _newest(facts.get(keys[-1], {}))
            cursor = audit_history.encode_cursor(at, batch_id)
        return groups, more, cursor, scanned, cut

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
                    watermark = db.query(func.max(lines.AuditBatch.id)).scalar() or 0
                    groups, truncated, cursor, scanned, cut = self._discover(db, limit_groups, settings)
                except OperationalError as exc:
                    if not db_waits.cancelled(exc):
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
                self._batch_max_id = watermark
                self.truncated = truncated
                self.next_cursor = cursor
                self.scanned_rows = scanned
        finally:
            self._build_lock.release()

    def behind(self, bind, limit_groups: int = 100) -> bool:
        """The walk and the merge behind the read (owner 11-09 «읽기는 쓰기에 영향 안 받음»): the route answers the
        projection it holds, and its worker (`runtime.behind`) builds it (`load_initial`) or merges what other processes
        wrote (`refresh_if_stale`) on a session of its own on `bind` - a read asks for one, run once the last ended
        `CATCH_UP_GAP_SECONDS` ago or more. -> whether one runs now or goes next, or none has built the projection yet
        (a walk cut before naming a group) - the answer's `updating`: never «no history» for «not read yet»."""
        from sqlalchemy.orm import sessionmaker

        factory = sessionmaker(bind=bind)
        self._behind.ask(RECENT, lambda: self._catch_up(factory, limit_groups), again=lambda kept: True)
        return not self.is_loaded or self._behind.busy(RECENT)

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

    def refresh_if_stale(self, db: Session, limit_groups: int = 100) -> bool:
        """Merge the batches committed since the projection read them (other processes, and what a notification
        already showed) in id slices of `recent_scan_chunk_rows`, each moving the watermark; past
        `recent_walk_seconds` or a statement past its limit, the rest is the next read's. -> whether any came"""
        settings = resolve_recent_settings()
        merged, started, step, latest = False, time.monotonic(), "the newest id", None
        with _bounded(db, settings):
            try:
                latest = db.query(func.max(lines.AuditBatch.id)).scalar() or 0
                while True:
                    with self._lock:
                        if not self.is_loaded or latest <= (self._batch_max_id or 0):
                            return merged
                        previous = self._batch_max_id or 0
                    if time.monotonic() - started > settings["recent_walk_seconds"]:
                        step = "past recent_walk_seconds %d" % settings["recent_walk_seconds"]
                        break
                    step = "a slice"
                    one = self._merge(db, previous, min(latest, previous + settings["recent_scan_chunk_rows"]),
                                      limit_groups)
                    if one is None:
                        return merged
                    merged = merged or one
            except OperationalError as exc:
                if not db_waits.cancelled(exc):
                    raise
                step = "%s past recent_statement_seconds %d" % (step, settings["recent_statement_seconds"])
        with self._lock:
            left = "?" if latest is None else latest - (self._batch_max_id or 0)
        logger.warning("[Audit] recent merge cut at %d s - %s; %s id(s) left for the next read",
                       time.monotonic() - started, step, left)
        return merged

    def _merge(self, db: Session, previous: int, latest: int, limit_groups: int):
        """One slice `(previous, latest]`: its groups read again whole, each to the top, the watermark to `latest`.
        -> whether it held batches, or None when another merge or a rebuild moved the watermark meanwhile."""
        b = lines.AuditBatch
        keys = list({group_of(tid) for (tid,) in db.query(b.transaction_id).filter(b.id > previous, b.id <= latest)})
        facts = _batch_facts(db, keys)
        changed = _changed(db, facts)
        touched = sorted(keys, key=lambda key: _newest(facts.get(key, {})), reverse=True)[:limit_groups]
        with self._lock:
            if (self._batch_max_id or 0) != previous:
                return None
            for key in reversed(touched):           # the newest ends on top
                self._to_top({"transaction_id": key, "tables": facts.get(key, {}), "changed": changed.get(key, {})},
                             limit_groups)
            self._batch_max_id = latest
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


def _fresh_table() -> dict:
    return {"kinds": [], "written_by": [], "at": None, "id": 0, "records": 0}


def _said(one: dict, kind, who, at, batch_id):
    """One batch of a table into its facts - kinds and writers in the order first written, the newest time."""
    one["records"] += 1
    for listed, word in ((one["kinds"], kind), (one["written_by"], who)):
        if word and word not in listed:
            listed.append(word)
    one["at"], one["id"] = at, batch_id


def _batch_walk(db: Session, floor, limit_groups: int, settings: dict):
    """The newest `limit_groups` groups the batches name, newest first by (at, id), below `floor` (a page's cursor)
    and without the groups seen at or above it. -> (keys, there are more, batches read, cut or None)"""
    b = lines.AuditBatch
    keys, skipped, position, scanned, started = [], set(), floor, 0, time.monotonic()
    step = "a chunk"
    try:
        while scanned < settings["recent_max_scan_rows"]:
            if time.monotonic() - started > settings["recent_walk_seconds"]:
                return _said_cut(keys, scanned, started, "past recent_walk_seconds %d" % settings["recent_walk_seconds"])
            want = min(settings["recent_scan_chunk_rows"], settings["recent_max_scan_rows"] - scanned)
            q = db.query(b.transaction_id, b.at, b.id).filter(b.at.isnot(None))
            if position is not None:
                q = q.filter(sa.tuple_(b.at, b.id) < sa.tuple_(*position))
            step = "a chunk"
            rows = q.order_by(b.at.desc(), b.id.desc()).limit(want).all()
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
    """Of the groups `keys`, those with a batch at or above `floor` - named by an earlier page. One statement."""
    b = lines.AuditBatch
    return {group_of(tid) for (tid,) in db.query(b.transaction_id).filter(
        sa.tuple_(b.at, b.id) >= sa.tuple_(*floor), sa.or_(*[in_group(b.transaction_id, key) for key in keys]))
        .distinct()}


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
