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


def _synthesize_payload(row, columns, envelope) -> dict:
    """One ORM row -> the payload shape `stage_event` would have staged.

    Same construction as `chain_replay._to_payloads`, extended with the envelope
    keys the live path carries (`transaction_id` drives the worker's grouping,
    `source_name` drives the circular-loop filter), so an expanded payload is
    indistinguishable from a per-row one apart from its point in time.
    """
    return {
        "row_id": row.row_id,
        "business_key": getattr(row, "business_key_val", None),
        "data": {
            col: {"value": getattr(row, col, None),
                  "is_overwrite": False,
                  "updated_by": "system"}
            for col in columns
        },
        "transaction_id": envelope.get("transaction_id"),
        "updated_by": envelope.get("updated_by"),
        "source_name": envelope.get("source_name"),
        "timestamp": envelope.get("timestamp"),
    }


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


def reexpand_collapsed_event(db, event, payload, error_reason: str = None) -> int:
    """Replace a repeatedly-failing collapsed event with per-row retry events.

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

    RE-EXPANSION TERMINATES BY CONSTRUCTION. The events written here carry `data`
    and no `row_ids`, so `is_collapsed_payload` is False for them and they can
    never re-expand again. There is no second round.

    THE COST IS PAID ONLY WHERE SOMETHING BROKE: one chunk's worth of per-row
    outbox rows, and one mapper run + one commit per row for that chunk. The
    happy path never reaches this function.

    Returns the number of per-row events written (0 = caller quarantines as before).
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
            "[OUTBOX-4] collapsed event %s on '%s' (%d rows, tx %s) failed 3 times; "
            "re-expanded into %d per-row retry event(s) so the failure can be "
            "narrowed to the row that actually breaks instead of quarantining the "
            "whole chunk.",
            event.event_uuid, event.table_name, len(row_ids), base_tx, written)
    return written
