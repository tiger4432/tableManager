"""[OUTBOX-4] Turning a collapsed outbox event back into rows.

WHAT A COLLAPSED EVENT IS. `database.stage_collapsed_event` writes ONE outbox row
naming the `row_ids` one flush touched, instead of N rows each carrying one row's
values. The event is a POINTER, not a SNAPSHOT.

WHY THE CONSUMER RE-READS RATHER THAN BEING HANDED VALUES (product owner, this
round): the outbox should carry only the trigger row_id and the table, and the
derivation should read the main table - THE WAY CHAIN REPLAY ALREADY DOES. This
is not a new derivation style, it is the one that already exists in three places:

  - `chain_replay._to_payloads` walked the trigger table's CURRENT contents and
    synthesized `{"row_id", "data": {col: {"value": v}}}` for the real mapper. ⚰️ It is
    retired: replay hands its rows to THIS expansion now, so the second implementation of
    the shape became a caller of the first;
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
    CHAIN_DEPTH_KEY,
    ONLY_RULE_KEY,
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
    payload = {
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
    # 🔴 [2026-09-22] 사건이 «들고 다니는» 키들. 위 일곱은 이 함수가 «짓는» 모양이고,
    #    이 둘은 이 함수가 «나르는» 값이라 성질이 다르다 — 그래서 아래에 따로 선다.
    #
    #    확장(`expand_events`)은 «같은 사건이 모양만 바뀌는» 것이므로 둘 다 따라가야 한다.
    #    따라가지 않으면 실측(2026-09-22)대로 이렇게 된다:
    #      chain_depth    봉투에 3 을 넣고 돌려도 반환에 «없어서» chain_depth_of 가 None 을
    #                     읽고, 그 독스트링이 None 을 「체인 밖」이라 정의한다
    #                     -> 재확장된 행에 «홉 상한이 안 걸린다»
    #      only_rule      「규칙 X 만」이 사라져 그 표의 «모든» 규칙이 깨어난다
    #                     -> 리플레이가 막으려던 것의 «정반대»이고 똑같이 조용하다
    #
    # ⛔ 없으면 «키를 안 쓴다». `None` 을 쓰면 안 된다 — 두 읽는 쪽 모두 「키 없음」과
    #    「값이 None」을 다른 상태로 읽지 않게 되어, 부재가 «선언»으로 굳는다.
    for key in (CHAIN_DEPTH_KEY, ONLY_RULE_KEY):
        if key in envelope:
            payload[key] = envelope[key]
    return payload


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


def is_split_leaf(payload) -> bool:
    """A one-row child of a split group: it carries its row's values, not a row id list.

    ⚠️ ONLY EVENTS WRITTEN BEFORE THE SPLIT RETIRED (총괄 c9ee06b34) - nothing splits now, but
    a queue may still hold them, and the retry route reads them with this.
    """
    payload = payload or {}
    return bool(payload.get("reexpanded_from")) and "row_id" in payload \
        and "row_ids" not in payload


def refreshed_leaf_payload(db, table_name: str, payload):
    """A split leaf's payload rebuilt from its row as it is NOW (총괄 756c54d68 ⑤).

    The split froze the row's values into the leaf when its group failed, so a retry after
    the operator fixed the row replayed the old value and failed again - and 「fix the data,
    retry」 is the operator's way back. Rebuilt the way the split built it (the leaf is its
    own envelope); `None` when the row is gone. Halves need none of this: they carry row ids
    and the worker reads those rows when it runs them.
    """
    from database.models import DYNAMIC_TABLES

    model = DYNAMIC_TABLES.get(table_name)
    row = (db.query(model).filter(model.row_id == payload.get("row_id")).first()
           if model is not None else None)
    if row is None:
        return None
    fresh = _synthesize_payload(row, _data_columns(model), payload)
    for key in ("reexpanded_from", "error_log"):
        if key in payload:
            fresh[key] = payload[key]
    return fresh


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


# ⚰️ [총괄 c9ee06b34, 소유자 09-29 「체인 에러나면 쪼개는게 빼자 그냥」] `reexpand_collapsed_event`,
#   `_split_collapsed_event` and `MAX_REEXPANSION_DEPTH` STOOD HERE. A chunk that failed its
#   attempts was halved into two new events, each half failed and was halved again, down to
#   one row - so one failing chunk wrote about 2N new events, and an error on EVERY row
#   walked every half to the end. That is how one replayed join line spread the chain in
#   production. A failed chunk now goes FAILED whole and writes nothing new; the worker's
#   quarantine names the rules, tables, rows and reason instead (`_failure_record`).
#   The symptom this leaves, kept as the intended answer: one poison row takes its chunk
#   FAILED with it (`test_a_failed_chunk_goes_failed_whole::test_one_poison_row_takes_its_chunk_failed_with_it`).
