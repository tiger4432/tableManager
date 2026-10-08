"""Set queued chain events aside, and run them again - the emergency stop's second half
(총괄 3840af307 ㄴ · 2dbbfd1e5).

⛔ NOTHING IS DELETED. An event set aside is FINISHED with `cancelled_by` and a reason in its
payload (`event_constants.mark_cancelled`, the seat `scripts/outbox_triage` already used) - a
1,000-row collapsed event as well as a per-row one. Running it again is a REPLAY of the rows
those events named (`chain_replay` with `row_ids`, no `cascade` - 소유자 09-27), not a second
replay door.

One body for the three callers: the retroactive operations `set_aside` / `rerun_set_aside`
and `outbox_triage --cancel` / `--replay-cancelled`.
"""
import event_constants
from utils.payload_helper import get_payload_dict

#: Who a set-aside says did it - the operator, from a screen or a script.
OPERATOR = "operator"
#: The source of the audit line a chain queue × writes - who, which line, how many events.
QUEUE_SKIP_SOURCE = "chain_queue_skip"
CHUNK = 1000


def rows_of(payload):
    """The row ids an event names - a collapsed event's list, a per-row event's one row."""
    if event_constants.is_collapsed_payload(payload):
        return [r for r in (payload.get("row_ids") or ()) if r]
    return [payload["row_id"]] if payload.get("row_id") else []


def _rules_named(names):
    if not names:
        return []
    from chain import replay
    by_name = {r.get("name"): r for r in replay.load_rules()}
    return [by_name[n] for n in names if n in by_name]


def _in_scope(db, done, tables=(), rules=(), transactions=(), since=None, per_row_only=False,
              ids=()):
    """Chain events in scope - waiting ones (`done=False`) or ones set aside (`done=True`).
    Every criterion given narrows the set; `rules` asks the worker's own `fires`; `ids` is
    one chain queue line's rows (its ×, 소유자 10-08)."""
    from database.models import DatabaseOutbox
    from chain.ingestion_worker import fires

    query = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.processed_chain.is_(done),
        DatabaseOutbox.event_type.in_(sorted(event_constants.CHAIN_OWNED_EVENT_TYPES)))
    # 🔴 THE KEYS ARE ASKED IN SQL (소유자 10-08 「빼 두기가 5분 넘게」). Read whole and sieved
    #    here, a transaction's events cost the whole waiting queue; `idx_outbox_txid` answers
    #    them by the transaction.
    if ids:
        query = query.filter(DatabaseOutbox.id.in_(list(ids)))
    if transactions:
        query = query.filter(DatabaseOutbox.payload["transaction_id"].as_string().in_(list(transactions)))
    if tables:
        query = query.filter(DatabaseOutbox.table_name.in_(list(tables)))
    if since:
        query = query.filter(DatabaseOutbox.created_at >= since)
    rules = _rules_named(rules) if rules and isinstance(next(iter(rules)), str) else rules
    for event in query.order_by(DatabaseOutbox.id).yield_per(CHUNK):
        payload = get_payload_dict(event)
        if done and payload.get(event_constants.CANCEL_MARK) != OPERATOR:
            continue
        if per_row_only and event_constants.is_collapsed_payload(payload):
            continue
        if rules and not any(fires(rule, event) for rule in rules):
            continue
        yield event, payload


def set_aside(db, tables=(), rules=(), transactions=(), since=None, per_row_only=False,
              apply=False, reason="set aside by an operator", checkpoint=None, ids=()):
    """-> `{"events", "rows", "by_table"}` for what is (dry run) or was (apply) set aside -
    apply adds `marked`: the events this call ended, which leaves out any the chain finished
    in between."""
    found = [(event.id, event.table_name, len(rows_of(payload)))
             for event, payload in _in_scope(db, False, tables, rules, transactions, since,
                                             per_row_only, ids)]
    by_table = {}
    for _id, table, rows in found:
        by_table[table] = by_table.get(table, 0) + 1
    out = {"events": len(found), "rows": sum(r for _i, _t, r in found), "by_table": by_table}
    if not apply or not found:
        return dict(out, marked=0) if apply else out
    found_ids = [i for i, _t, _r in found]
    out["marked"] = 0
    for start in range(0, len(found_ids), CHUNK):
        # Between committed chunks - the one place a stop is safe (a run's cancel).
        if checkpoint is not None and checkpoint(start):
            out["stopped_after"] = start
            break
        out["marked"] += _mark(db, found_ids[start:start + CHUNK], reason)
        db.commit()
    return out


def _mark(db, ids, reason):
    """`mark_cancelled` on the rows of `ids` STILL WAITING - set-based on PostgreSQL (a flooded
    queue is 660,000 rows - loading them to edit a dict would be its own outage) and per object
    elsewhere. A row the chain finished in between keeps its own ending: marking it would make a
    run row read as set aside, and `rerun_set_aside` would run it again (소유자 10-08). -> marked."""
    from sqlalchemy import func, update
    from database.models import DatabaseOutbox

    waiting = (DatabaseOutbox.id.in_(ids), DatabaseOutbox.processed_chain.is_(False))
    if db.get_bind().dialect.name == "postgresql":
        return db.execute(
            update(DatabaseOutbox).where(*waiting).values(
                **event_constants.processed_columns("SUCCESS"),
                payload=DatabaseOutbox.payload.op("||")(func.jsonb_build_object(
                    event_constants.CANCEL_MARK, OPERATOR,
                    event_constants.CANCEL_REASON, reason)))
            .execution_options(synchronize_session=False)).rowcount
    events = db.query(DatabaseOutbox).filter(*waiting).all()
    for event in events:
        event_constants.mark_cancelled(event, OPERATOR, reason)
    return len(events)


def rows_set_aside(db, tables=(), rules=(), transactions=()):
    """-> `{table: [row ids]}` - every row the set-aside events in scope named."""
    out = {}
    for event, payload in _in_scope(db, True, tables, rules, transactions):
        out.setdefault(event.table_name, set()).update(rows_of(payload))
    return {table: sorted(ids) for table, ids in out.items()}
