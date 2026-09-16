"""[OUTBOX-4] Turning a collapsed outbox event back into rows.

WHAT A COLLAPSED EVENT IS. `database.stage_collapsed_event` writes ONE outbox row
naming the `row_ids` one flush touched, instead of N rows each carrying one row's
values. The event is a POINTER, not a SNAPSHOT.

WHY THE CONSUMER RE-READS RATHER THAN BEING HANDED VALUES (product owner, this
round): the outbox should carry only the trigger row_id and the table, and the
derivation should read the main table - THE WAY CHAIN REPLAY ALREADY DOES. This
is not a new derivation style, it is the one that already exists in three places:

  - `chain_replay._to_payloads` (:185) walks the trigger table's CURRENT contents
    and synthesizes `{"row_id", "data": {col: {"value": v}}}` for the real mapper;
  - `enrichment_backfill.run_backfill` builds the same shape the same way;
  - `mappers/dt_map_mapper`'s CORRECTION path re-reads ORM rows (`rows.extend(q.all())`)
    while its live trigger path eats the payload.

The live trigger path was the only consumer eating a payload. Making it read like
replay collapses two derivation implementations into one instead of adding a
third event format.

HOW THE TWO SHAPES COEXIST. The user-owned mappers in the gitignored
`server/mappers/` tree are a contract this round cannot edit:
`production_mapper.py:11` does `payload.get("data", {})` and `mappers/utils.py:15`
does `p.get("data", {})` then `cell_detail["value"]`. They keep getting EXACTLY
that. `expand_events` below synthesizes the same nested payload `stage_event`
would have written - same columns (shared `OUTBOX_PAYLOAD_EXCLUDED_COLUMNS`), same
`{"value", "is_overwrite", "updated_by"}` cell shape, same envelope keys - so no
mapper can tell the two apart by shape. What moved is only WHERE the values come
from: the row, not the event.

🔴 THE ONE SEMANTIC CHANGE, NAMED RATHER THAN DISCOVERED. A payload is a
point-in-time snapshot; a re-read is current state. They differ exactly when the
row changes between the event and its consumption:

  - ROW UPDATED TWICE QUICKLY. Both events now derive from the FINAL state
    instead of one deriving a value that is already superseded. The derived table
    ends in the same place either way, and it gets there without briefly holding
    a value the source no longer has. This is idempotent and it is a change: the
    chain no longer observes intermediate states of its trigger row.
  - ROW DELETED BEFORE CONSUMPTION. There is nothing to read. Today's per-row
    payload still carries the deleted row's values and derives from them.
    THE DECISION: derive nothing - which is what chain replay already does (it
    walks current contents, so a deleted row simply is not in the page) - but
    NEVER SILENTLY. `expand_events` counts every unresolved row_id, logs it at
    WARNING with the table, transaction and a sample of the ids, and returns the
    count to its caller. "The row was deleted before the chain ran" is a fact an
    operator can act on; a skipped row nobody counted is not.
"""
import logging
import time as _time

from sqlalchemy import bindparam as _bindparam, text as _sqltext

logger = logging.getLogger("Server")

from event_constants import (
    OUTBOX_COLLAPSE_CHUNK_ROWS,
    OUTBOX_PAYLOAD_EXCLUDED_COLUMNS,
    is_collapsed_payload,
)
from utils.payload_helper import get_payload_dict


def _data_columns(model) -> list:
    """The columns a payload carries for this table.

    Derived from the MODEL, not from a literal list, and filtered by the same
    shared frozenset the producer uses - so the expander can never rebuild a
    different column set than `stage_event` would have written. (Chain replay
    reaches the same set from `crud.TABLE_CONFIG`; the dynamic model is built
    from that config, so the two agree by construction.)
    """
    return [c.name for c in model.__table__.columns
            if c.name not in OUTBOX_PAYLOAD_EXCLUDED_COLUMNS]


def synthesize_payload(row_id, business_key, values: dict, envelope: dict) -> dict:
    """THE payload shape a chain mapper is handed. One author, every caller.

    🔴 [S-279, 판정 426] A MAPPER IS WRITTEN BY THE USER, AND IT WAS BEING CALLED WITH TWO
    DIFFERENT SHAPES. The live path handed seven keys and `replay._to_payloads` handed two
    (`row_id`, `data`), so a mapper reading `business_key` worked on the trigger path and
    returned nothing on a backfill - silently, because a missing key is `None` and not an
    error. 상설 ④ 「같은 기능에 두 경로」 one layer below the dispatcher 판정 420 unified: it is
    not the CALL that was split any more, it is the ARGUMENT.

    ⚠️ IT TAKES VALUES, NOT A ROW, ON PURPOSE. The two callers hold different things - the live
    path an ORM row, replay a keyset tuple - and a function that owned both 「what a payload
    looks like」 and 「how to read a row」 would have to grow a branch per caller, which is the
    shape being removed. Reading the row belongs to the caller; the shape belongs here.
    """
    return {
        "row_id": row_id,
        "business_key": business_key,
        "data": {
            col: {"value": value, "is_overwrite": False, "updated_by": "system"}
            for col, value in values.items()
        },
        "transaction_id": envelope.get("transaction_id"),
        "updated_by": envelope.get("updated_by"),
        "source_name": envelope.get("source_name"),
        "timestamp": envelope.get("timestamp"),
    }


def _synthesize_payload(row, columns, envelope) -> dict:
    """One ORM row -> the shape above. The live path's way of reading a row, and nothing else.

    `transaction_id` drives the worker's grouping and `source_name` drives the circular-loop
    filter, so an expanded payload is indistinguishable from a per-row one apart from its
    point in time.
    """
    return synthesize_payload(
        row.row_id,
        getattr(row, "business_key_val", None),
        {col: getattr(row, col, None) for col in columns},
        envelope)


def load_rows_by_ids(db, table_name: str, row_ids, chunk_size: int = OUTBOX_COLLAPSE_CHUNK_ROWS):
    """{row_id: ORM row} for the named ids, in `chunk_size` batches.

    [확장성] `row_id` is the primary key, so each chunk is an index lookup; the
    chunking keeps the IN list (and its query plan) stable at 10M-row scale.
    """
    from database.models import DYNAMIC_TABLES

    model = DYNAMIC_TABLES.get(table_name)
    found = {}
    if model is None or not row_ids:
        return model, found
    unique_ids = list(dict.fromkeys(row_ids))
    for i in range(0, len(unique_ids), chunk_size):
        id_chunk = unique_ids[i:i + chunk_size]
        for row in db.query(model).filter(model.row_id.in_(id_chunk)).all():
            found[row.row_id] = row
    if unique_ids and not found:
        _report_unreadable(db, model, table_name, unique_ids, chunk_size)
    return model, found


def _report_unreadable(db, model, table_name, unique_ids, chunk_size):
    """One line of VALUES for the moment a named set of rows reads back as nothing (S-158).

    🔴 THE INSTRUMENT EXISTS BECAUSE THREE EXPLANATIONS WERE MEASURED AND ALL THREE DIED
    (판정 266). The session is not shared with the drain (`SessionLocal` is a plain
    `sessionmaker`), the isolation level is `read committed`, and a direct probe showed the
    rows visible at the same instant their outbox event became visible. So this stops
    guessing and records what THE DATABASE ANSWERED at the one moment it goes wrong.

    ⚠️ THE STATEMENT IS RENDERED FROM THE PRODUCT'S OWN QUERY, never retyped. A hand-written
    lookalike would answer a question about the hand-written one - and the live candidate is
    that the ids reach the bind with a different TYPE than the rows carry, which is exactly
    what a retyped query would hide.

    ⚠️ COSTS NOTHING ON THE HAPPY PATH. It runs only when a non-empty id list found zero
    rows, which is the case that is currently losing data; everything in it is contained, so
    a probe that cannot answer degrades to a value saying so rather than raising inside the
    read it is describing.
    """
    facts = {}
    try:
        probe = db.query(model).filter(model.row_id.in_(unique_ids[:chunk_size]))
        facts["sql"] = " ".join(str(probe).split())
    except Exception as exc:                                        # pragma: no cover
        facts["sql"] = "<unrenderable: %s>" % type(exc).__name__
    facts["ids"] = len(unique_ids)
    facts["id_types"] = sorted({type(v).__name__ for v in unique_ids})
    facts["sample_id"] = repr(unique_ids[0])
    facts["row_id_col"] = "%s" % getattr(model.row_id.type, "__class__", type(None)).__name__

    physical = getattr(getattr(model, "__table__", None), "name", table_name)
    ids_as_text = [str(v) for v in unique_ids]

    def _recount(session, label):
        try:
            session.execute(_sqltext("SELECT 1"))
            value = session.execute(
                _sqltext("SELECT count(*) FROM \"%s\" WHERE row_id IN :ids" % physical)
                .bindparams(_bindparam("ids", expanding=True)), {"ids": ids_as_text}).scalar()
            facts[label] = value
        except Exception as exc:
            facts[label] = "ERR:%s" % type(exc).__name__

    _recount(db, "same_session_now")
    for label, sql in (("txid", "SELECT txid_current()"),
                       ("snapshot", "SELECT pg_current_snapshot()")):
        try:
            facts[label] = str(db.execute(_sqltext(sql)).scalar())
        except Exception as exc:
            facts[label] = "ERR:%s" % type(exc).__name__

    _time.sleep(0.1)
    _recount(db, "same_session_after_100ms")
    # 🔴 THE ONE MEASUREMENT THAT DECIDES IT (S-160). On the normal path the outbox event
    # and its rows share an `xmin` - one transaction, so seeing one without the other is
    # impossible and the "event commits before its rows" seam does not exist there.
    # Taken HERE, once the rows are readable, the writer's xid can be compared with the
    # snapshot recorded above: an xid at or beyond that snapshot's xmax says the write had
    # simply not committed when we looked, and anything else says it had.
    try:
        facts["writer_xid"] = [str(r[0]) for r in db.execute(
            _sqltext("SELECT DISTINCT xmin::text FROM \"%s\" WHERE row_id IN :ids" % physical)
            .bindparams(_bindparam("ids", expanding=True)), {"ids": ids_as_text}).fetchall()]
    except Exception as exc:
        facts["writer_xid"] = "ERR:%s" % type(exc).__name__
    try:
        from database.database import SessionLocal
        fresh = SessionLocal()
        try:
            _recount(fresh, "fresh_session")
        finally:
            fresh.close()
    except Exception as exc:                                        # pragma: no cover
        facts["fresh_session"] = "ERR:%s" % type(exc).__name__

    logger.warning(
        "[OUTBOX-4/PROBE] '%s' named %d row(s) and read back ZERO. "
        "id_types=%s sample=%s row_id_col=%s | same_session_now=%s "
        "same_session_after_100ms=%s fresh_session=%s | txid=%s snapshot=%s "
        "writer_xid=%s | SQL: %s",
        table_name, facts["ids"], facts["id_types"], facts["sample_id"], facts["row_id_col"],
        facts.get("same_session_now"), facts.get("same_session_after_100ms"),
        facts.get("fresh_session"), facts.get("txid"), facts.get("snapshot"),
        facts.get("writer_xid"), facts["sql"])


def event_key(event) -> str:
    """The key `expand_events` returns its results under.

    🔴 `event_uuid`, NOT `id(event)`. Python object identity is only stable while
    the caller holds a reference to the very same objects, so a caller that passed
    a generator, or re-filtered its list into new objects, would look up a key that
    is not there - and the lookup site's `.get(key, ())` FAILS OPEN to "this event
    names no rows", i.e. derives nothing, silently. `event_uuid` is NOT NULL on
    `database_outbox` and unique per event, so the key survives any re-shaping of
    the caller's list.
    """
    return event.event_uuid


def expand_events(db, events) -> dict:
    """{event.event_uuid: [per-row payload, ...]} for a batch of outbox events.

    Per-row events pass straight through as `[their own payload]`, so a caller
    can use this unconditionally and a batch with no collapsed event in it issues
    no query at all. Collapsed events are materialized by re-reading the rows
    they name, ONE query per (table, 1000 ids) for the WHOLE batch rather than
    per event - a group of 20 chunks covering 20,000 rows costs 20 indexed
    lookups, against the 20,000 JSONB payloads it replaces.
    """
    result = {}
    ids_by_table = {}
    collapsed = []

    for ev in events:
        payload = get_payload_dict(ev)
        if is_collapsed_payload(payload):
            collapsed.append((ev, payload))
            ids_by_table.setdefault(ev.table_name, []).extend(payload.get("row_ids") or ())
        else:
            result[event_key(ev)] = [payload]

    if not collapsed:
        return result

    loaded = {}
    for table_name, row_ids in ids_by_table.items():
        model, found = load_rows_by_ids(db, table_name, row_ids)
        if model is None:
            logger.error(
                "[OUTBOX-4] collapsed event names table '%s', which has no dynamic model "
                "in this process - %d row(s) cannot be expanded and derive NOTHING. "
                "(A table present in table_config but not yet loaded here: the process "
                "needs its config reload.)", table_name, len(set(row_ids)))
        loaded[table_name] = (model, found)

    for ev, payload in collapsed:
        model, found = loaded.get(ev.table_name, (None, {}))
        columns = _data_columns(model) if model is not None else []
        row_ids = payload.get("row_ids") or []
        payloads = []
        missing = []
        for rid in row_ids:
            row = found.get(rid)
            if row is None:
                missing.append(rid)
                continue
            payloads.append(_synthesize_payload(row, columns, payload))
        if missing:
            # Named outcome, never a silent skip - see the module docstring.
            logger.warning(
                "[OUTBOX-4] %d of %d row(s) named by outbox event %s on '%s' "
                "(tx %s) no longer exist and derive NOTHING (deleted between the "
                "write and the chain run). Sample: %s",
                len(missing), len(row_ids), getattr(ev, "event_uuid", "?"),
                ev.table_name, payload.get("transaction_id"), missing[:5])
        result[event_key(ev)] = payloads

    return result


#: 🔴 HOW FAR A CHUNK MAY KEEP SPLITTING (S-173). A 1,000-row chunk reaches a single
#: row in ten halvings, so twelve is room to spare and a runaway is refused by name rather
#: than discovered as a queue. The depth lives in the CHILD'S OWN PAYLOAD
#: (`reexpanded_from.depth`), so an operator reading one event can see how far it has been
#: narrowed without reconstructing the chain.
MAX_REEXPANSION_DEPTH = 12


def reexpand_collapsed_event(db, event, payload, error_reason: str = None) -> int:
    """Halve a repeatedly-failing collapsed event; write per-row events only at the leaf.

    🔴 WHY THIS EXISTS (lead PM ruling, this round). Collapsing makes the retry
    quarantine coarser: today one poison row is quarantined alone, collapsed it
    would take its whole chunk. The ruling refused that as a false choice -
    COARSE ON THE HAPPY PATH, FINE ON THE FAILURE PATH. So the chunk is retried
    AS a chunk while `retry_count < 3` (a transient failure - a dead connection,
    a lock - recovers without ever paying per-row cost), and at the quarantine
    boundary, INSTEAD of being quarantined whole, it re-expands here.

    🔴 WHY EACH RE-EXPANDED EVENT GETS ITS OWN transaction_id. The worker's unit
    of failure is the TRANSACTION GROUP, not the event: one poison row fails the
    mapper for every event grouped with it. Re-expanding under the original
    transaction_id would put all 1,000 rows back in ONE group, they would fail
    together again, and the re-expansion would have bought nothing. Distinct ids
    make each row its own group, so 999 succeed and the poison row is quarantined
    ALONE - which is exactly the granularity the collapse was accused of losing.

    🔴 AND IT HALVES RATHER THAN EXPLODING (S-173). The first shape of this
    function wrote ONE EVENT PER ROW, and the cost of that is not theoretical: a
    production queue reached ~660,000 pending per-row events, which at a group's
    plumbing cost is DAYS of work to find rows that would take about two hours
    collapsed. Splitting in two finds the same poison row in about ten rounds and
    about twenty events, and the 999 innocent rows travel as a handful of CHUNKS
    instead of as 999 groups. Same end state -- the bad row alone, named -- at a
    logarithmic price instead of a linear one.

    ⚠️ A SPLIT READS NOTHING. Per-row expansion had to load every row to synthesize
    its payload; a half is the parent's envelope with half the `row_ids`, so the
    database is not touched until a leaf of ONE row is reached.

    RE-EXPANSION STILL TERMINATES, and now it needs two reasons rather than one:
      * a half of ONE row is written as a per-row `data` event, and those carry no
        `row_ids`, so `is_collapsed_payload` is False and they can never split again;
      * every child records `reexpanded_from.depth`, and `MAX_REEXPANSION_DEPTH`
        refuses BY NAME above it, falling back to the whole-chunk quarantine that
        was the behaviour before any of this existed.
    The first is what actually ends it; the second is what makes a bug in the first
    stop loudly instead of filling a queue.

    THE COST IS PAID ONLY WHERE SOMETHING BROKE. The happy path never reaches this
    function.

    Returns the number of retry events written (0 = caller quarantines as before).
    """
    from database.models import DatabaseOutbox
    import uuid

    row_ids = payload.get("row_ids") or []
    if not row_ids:
        return 0

    # 🔴 IDEMPOTENCE. `POST /admin/outbox/retry-failed` resets a FAILED parent to
    # PENDING, and without this guard every click would re-expand the same chunk
    # again - multiplying outbox rows by 1,000 per press, from a UI button, which is
    # precisely the growth this round exists to remove. A parent that already has
    # children refuses to make more; the operator's retry reaches them through their
    # `<tx>#row#` transaction ids (they were written PENDING and are drained
    # normally, or are themselves FAILED and retryable individually).
    prior = (payload.get("error_log") or {}).get("reexpanded_into")
    if prior:
        logger.warning(
            "[OUTBOX-4] collapsed event %s was already re-expanded into %s per-row "
            "event(s); refusing to re-expand again. Retry the children by their "
            "'%s#row#' transaction ids instead.",
            event.event_uuid, prior, payload.get("transaction_id"))
        return 0

    lineage = payload.get("reexpanded_from") or {}
    depth = lineage.get("depth") or 0
    # The tx id every child of this chunk shares, so an operator can still find the whole
    # family by prefix however deep the split has gone.
    root_tx = lineage.get("root_transaction_id") or payload.get("transaction_id")
    path = lineage.get("path") or ""

    if depth >= MAX_REEXPANSION_DEPTH:
        # ⛔ REFUSED BY NAME, NOT SILENTLY. Reaching here means the leaf rule stopped
        # ending the recursion, which is a defect in this function -- and a defect that
        # fills a queue is exactly what this round removed. The caller quarantines the
        # chunk whole, which is the honest end state.
        logger.error(
            "[OUTBOX-4] collapsed event %s on '%s' has already been narrowed %d times "
            "(cap %d) and still names %d row(s); refusing to split further and leaving "
            "it to whole-chunk quarantine.",
            event.event_uuid, event.table_name, depth, MAX_REEXPANSION_DEPTH,
            len(row_ids))
        return 0

    if len(row_ids) > 1:
        return _split_collapsed_event(
            db, event, payload, row_ids, error_reason,
            depth=depth, root_tx=root_tx, path=path)

    model, found = load_rows_by_ids(db, event.table_name, row_ids)
    if model is None:
        return 0
    columns = _data_columns(model)
    base_tx = payload.get("transaction_id")

    # 🔴 BUILD EVERY CHILD BEFORE ADDING ANY OF THEM. `db.add` in the loop meant that
    # a failure partway through left the already-added children in the session, where
    # the caller's `db.commit()` (which runs regardless, to persist the quarantine)
    # would write them - producing a FAILED parent whose error_log claims a plain
    # whole-chunk quarantine PLUS a few hundred orphan PENDING children, while the
    # log line said "falling back to whole-chunk quarantine". All-or-nothing removes
    # the half state instead of documenting it.
    children = []
    for rid in row_ids:
        row = found.get(rid)
        if row is None:
            continue  # counted by expand_events' warning on the failing pass
        per_row = _synthesize_payload(row, columns, payload)
        # Own group per row - see the docstring. Derived from the original id so
        # an operator can still find every child of a failed chunk by prefix.
        per_row["transaction_id"] = f"{base_tx}#row#{rid}"
        per_row["reexpanded_from"] = {
            "event_uuid": event.event_uuid,
            "row_count": len(row_ids),
            "reason": error_reason or "collapsed chunk failed 3 times",
            "depth": depth + 1,
            "root_transaction_id": root_tx,
            "path": path,
        }
        children.append(DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            event_type=event.event_type,
            table_name=event.table_name,
            payload=per_row,
            status="PENDING",
        ))

    try:
        for child in children:
            db.add(child)
    except Exception:
        # Same all-or-nothing rule for the add itself: nothing half-added survives
        # into the caller's quarantine commit.
        for child in children:
            try:
                db.expunge(child)
            except Exception:
                pass
        raise
    written = len(children)

    if written:
        logger.warning(
            "[OUTBOX-4] collapsed event %s on '%s' (%d row(s), tx %s, narrowed %d "
            "time(s)) failed its attempts; wrote %d per-row retry event(s) -- this is "
            "the LEAF of the narrowing, so the failure is now down to the row itself.",
            event.event_uuid, event.table_name, len(row_ids), base_tx, depth, written)
    return written


def _split_collapsed_event(db, event, payload, row_ids, error_reason,
                           *, depth: int, root_tx, path: str) -> int:
    """Two collapsed halves instead of N per-row events (S-173).

    🔴 EACH HALF IS ITS OWN TRANSACTION GROUP, for the reason the per-row shape needed
    distinct ids: the worker's unit of failure is the GROUP, so two halves sharing one id
    would be regrouped, fail together, and buy nothing. The id keeps the ROOT chunk's
    prefix and appends the path taken, so `a`, `ab`, `abb` reads as 「first half, then its
    second half, then that one's second half」 and one prefix search still finds the
    whole family.

    ⚠️ THE HALVES ARE STILL COLLAPSED, and that is the point: the innocent half is one
    chunk that succeeds on its first attempt, not five hundred groups that each pay a
    group's plumbing cost.
    """
    from database.models import DatabaseOutbox
    import uuid

    middle = len(row_ids) // 2
    halves = (row_ids[:middle], row_ids[middle:])
    children = []
    for side, half in zip("ab", halves):
        if not half:
            continue
        child_path = f"{path}{side}"
        child = dict(payload)
        child["row_ids"] = list(half)
        child["transaction_id"] = f"{root_tx}#half#{child_path}"
        # ⛔ THE PARENT'S VERDICT DOES NOT TRAVEL. `error_log` is why the PARENT stopped;
        # carrying it onto a child would make a fresh event look like one that has already
        # failed, and `reexpand_collapsed_event`'s idempotence guard reads exactly that key.
        child.pop("error_log", None)
        child["reexpanded_from"] = {
            "event_uuid": event.event_uuid,
            "row_count": len(row_ids),
            "reason": error_reason or "collapsed chunk failed its attempts",
            "depth": depth + 1,
            "root_transaction_id": root_tx,
            "path": child_path,
        }
        children.append(DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            event_type=event.event_type,
            table_name=event.table_name,
            payload=child,
            status="PENDING",
        ))

    # Same all-or-nothing add as the leaf below it, and for the same reason: a half-added
    # split leaves orphan PENDING children beside a parent whose log says it quarantined.
    try:
        for child in children:
            db.add(child)
    except Exception:
        for child in children:
            try:
                db.expunge(child)
            except Exception:
                pass
        raise

    if children:
        logger.warning(
            "[OUTBOX-4] collapsed event %s on '%s' (%d rows, tx %s) failed its attempts; "
            "split into %d half/halves of %s row(s) at depth %d, so the poison row is "
            "found by halving instead of by writing one event per row.",
            event.event_uuid, event.table_name, len(row_ids),
            payload.get("transaction_id"), len(children),
            " and ".join(str(len(h)) for h in halves if h), depth + 1)
    return len(children)
