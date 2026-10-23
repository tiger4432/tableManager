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
#: The source of the audit line a group writes when a set-aside landed on its rows while it ran
#: and it ran anyway - those rows are «ran», not «set aside» (총괄 54a53f894).
SKIP_TOO_LATE_SOURCE = "chain_queue_skip_too_late"
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
    """Chain events in scope, one at a time (`_scope_pages`)."""
    for kept, _read in _scope_pages(db, done, tables, rules, transactions, since, per_row_only, ids):
        yield from kept


def _scope_pages(db, done, tables=(), rules=(), transactions=(), since=None, per_row_only=False,
                 ids=(), size=None):
    """Chain events in scope - waiting ones (`done=False`) or ones set aside (`done=True`) - a page
    at a time: `(the page's events in scope with their payloads, the events it read)`, keyset by id,
    `size`'s answer (`keyset_scan.PageSize`) or CHUNK a page - a page reads before the next is asked
    for, so a run's first line does not wait on the whole queue (총괄 2ea5ee2a7 ①: 500,000 events
    15.27 s). Every criterion given narrows the set; `rules` asks the worker's own `fires`; `ids` is
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
    after = None
    while True:
        page = query if after is None else query.filter(DatabaseOutbox.id > after)
        read = page.order_by(DatabaseOutbox.id).limit(size.next() if size else CHUNK).all()
        if not read:
            return
        after, kept = read[-1].id, []
        for event in read:
            payload = get_payload_dict(event)
            if done and payload.get(event_constants.CANCEL_MARK) != OPERATOR:
                continue
            if per_row_only and event_constants.is_collapsed_payload(payload):
                continue
            if rules and not any(fires(rule, event) for rule in rules):
                continue
            kept.append((event, payload))
        yield kept, len(read)


def set_aside(db, tables=(), rules=(), transactions=(), since=None, per_row_only=False,
              apply=False, reason="set aside by an operator", checkpoint=None, ids=(), until=None):
    """-> `{"events", "rows", "by_table"}` for what is (dry run) or was (apply) set aside, a page at a
    time - a run that reports its pages sizes them (`keyset_scan.PageSize`); apply adds `marked` and
    `marked_by_table`: the events this call ended, which leaves out any the chain finished in between
    - and cuts the query of a group running one of them (`control.cancel_running_group`). `until` (a
    `time.monotonic()` instant) ends a dry run's reading there, and `cut` says so - the count's
    answer within the page cap (총괄 2ea5ee2a7 ②)."""
    import time
    from chain import control, keyset_scan

    out = {"events": 0, "rows": 0, "by_table": {}}
    if apply:
        out["marked"], out["marked_by_table"] = 0, {}
    size = keyset_scan.PageSize(CHUNK) if checkpoint is not None else None
    pages = _scope_pages(db, False, tables, rules, transactions, since, per_row_only, ids, size=size)
    for kept, _read in pages:
        page_ids = [event.id for event, _payload in kept]
        for event, payload in kept:
            out["rows"] += len(rows_of(payload))
            out["by_table"][event.table_name] = out["by_table"].get(event.table_name, 0) + 1
        out["events"] += len(page_ids)
        if apply and page_ids:
            from chain.ingestion_worker import _deleted_rows_of, _retract_deleted_rows
            deleted = _deleted_rows_of([event for event, _payload in kept])
            for table, marked in _mark(db, page_ids, reason).items():
                out["marked"] += marked
                out["marked_by_table"][table] = out["marked_by_table"].get(table, 0) + marked
            # a deletion set aside still happened - its rows' cells go as a run one's do (총괄 fa5417c28 3), in the
            # commit that marks it (총괄 09f58844f)
            _retract_deleted_rows(db, deleted)
            db.commit()
            # A group running one of them now is cut and rewinds without them - the rest of its
            # line runs on in the same slot (총괄 10-08: only stopping a WHOLE line stops its slot).
            control.cancel_running_group(db, ids=page_ids)
        # Between committed pages - the one place a stop is safe (a run's cancel).
        if checkpoint is not None and checkpoint(out["events"]):
            out["stopped_after"] = out["events"]
            break
        if until is not None and time.monotonic() >= until:
            if next(pages, None) is not None:              # a last page is not a cut one
                out["cut"] = True
            break
    return out


def set_aside_line(db, key, by, reason=None):
    """One chain queue line's waiting chain events set aside - a stop's second step, and again
    where a stopped run lands (총괄 e2b5b6f35). One audit line per table says who and how many it
    MARKED - none for a table it marked none of (총괄 10-09: a × that waited for a group's commit
    and found its row ended said 「1 skipped」). An index ask is set aside too; other events the chain
    does not own wait on for their worker. -> `{"waited", "marked", "kept", "ids"}`"""
    reason = reason or "skipped from the chain queue by %s" % by
    from database import crud
    from database.models import DatabaseOutbox as outbox

    waiting = (db.query(outbox.id, outbox.event_type)
               .filter(outbox.processed_chain == False,  # noqa: E712 - 부분 인덱스의 술어 철자
                       *event_constants.queue_line_rows(outbox, key)).all())
    chain_ids = [row.id for row in waiting if row.event_type in event_constants.CHAIN_OWNED_EVENT_TYPES]
    done = (set_aside(db, ids=chain_ids, apply=True, reason=reason)
            if chain_ids else {"marked": 0, "marked_by_table": {}})
    for table, events in sorted(done["marked_by_table"].items()):
        crud.create_audit_log(db, table, "*", "*", key, events, QUEUE_SKIP_SOURCE, by)
    # 🔴 AN INDEX ASK LEAVES TOO (owner 10-16: «60 min waiting, × does nothing»): the queue drew a × on it and kept
    #    it. Marked as a chain event is, so the index line never takes it; a slow read asks again.
    asks = [row.id for row in waiting if row.event_type == event_constants.EVENT_INDEX_WANTED]
    marked_asks = sum(_mark(db, asks, reason).values()) if asks else 0
    db.commit()
    return {"waited": len(waiting), "marked": done["marked"] + marked_asks,
            "kept": len(waiting) - len(chain_ids) - len(asks), "ids": chain_ids + asks}


def by_operator(outbox):
    """The SQL of 「set aside by an operator」 - the mark `_mark` writes."""
    return outbox.payload[event_constants.CANCEL_MARK].as_string() == OPERATOR


def line_already(db, key):
    """What became of a queue line that no longer waits: its rows set aside, ended, or none."""
    from database.models import DatabaseOutbox as outbox

    rows = db.query(outbox.id).filter(*event_constants.queue_line_rows(outbox, key))
    if rows.first() is None:
        return "gone"
    return "set_aside" if rows.filter(by_operator(outbox)).first() is not None else "processed"


def what_became_of(db, ids):
    """-> `(set aside, ran)` of the chain events `ids` as the table has them now - a ×'s answer,
    read once the slot running its line has ended (총괄 54a53f894: a group that commits after the
    mark ran its rows, and 「ran」 wins). One query. 「Ran」 is any ending but the operator's,
    a row the chain finished between the ×'s read and its mark included."""
    from sqlalchemy import case, func
    from database.models import DatabaseOutbox as outbox

    if not ids:
        return 0, 0
    aside, ended = (db.query(func.count(case((by_operator(outbox), 1))), func.count())
                    .filter(outbox.id.in_(list(ids)), outbox.processed_chain.is_(True)).one())
    return aside, ended - aside


def _mark(db, ids, reason):
    """`mark_cancelled` on the rows of `ids` STILL WAITING - set-based on PostgreSQL (a flooded
    queue is 660,000 rows - loading them to edit a dict would be its own outage) and per object
    elsewhere. A row the chain finished in between keeps its own ending: marking it would make a
    run row read as set aside, and `rerun_set_aside` would run it again (소유자 10-08).
    -> `{table: marked}`."""
    from collections import Counter
    from sqlalchemy import func, update
    from database.models import DatabaseOutbox

    waiting = (DatabaseOutbox.id.in_(ids), DatabaseOutbox.processed_chain.is_(False))
    if db.get_bind().dialect.name == "postgresql":
        # 🔴 LOCKED IN ID ORDER FIRST (총괄 10-09) - the order a group's success path locks its rows
        #    in, so the two never wait on each other in a circle. A row a group holds is waited for,
        #    then, ended by it, no longer waiting: it keeps the group's ending.
        db.query(DatabaseOutbox.id).filter(*waiting).order_by(DatabaseOutbox.id).with_for_update().all()
        return dict(Counter(table for (table,) in db.execute(
            update(DatabaseOutbox).where(*waiting).values(
                **event_constants.cancelled_columns(),
                payload=DatabaseOutbox.payload.op("||")(func.jsonb_build_object(
                    event_constants.CANCEL_MARK, OPERATOR,
                    event_constants.CANCEL_REASON, reason)))
            .returning(DatabaseOutbox.table_name)
            .execution_options(synchronize_session=False))))
    events = db.query(DatabaseOutbox).filter(*waiting).all()
    for event in events:
        event_constants.mark_cancelled(event, OPERATOR, reason)
    return dict(Counter(event.table_name for event in events))


def changes_set_aside(db, tables=(), rules=(), transactions=()):
    """-> `{table: {row id: (its last set-aside event's type, what it held before the first of them)}}` - each row the
    set-aside events in scope named. What it held is per column the old value of the first event that carried one
    (`event_constants.OLD_VALUES_KEY`: an edit the columns it changed, a deletion every column; an event staged before
    they were kept carries none) - `{}` when none did."""
    out = {}
    for event, payload in _in_scope(db, True, tables, rules, transactions):
        rows, old = rows_of(payload), payload.get(event_constants.OLD_VALUES_KEY)
        olds = old if isinstance(old, list) else [old]
        table = out.setdefault(event.table_name, {})
        for i, row_id in enumerate(rows):
            had = olds[i] if i < len(olds) and isinstance(olds[i], dict) else {}
            table[row_id] = (event.event_type, {**had, **table.get(row_id, (None, {}))[1]})
    return out


def rows_set_aside(db, tables=(), rules=(), transactions=()):
    """-> `{table: [row ids]}` - every row the set-aside events in scope named."""
    out = {}
    for event, payload in _in_scope(db, True, tables, rules, transactions):
        out.setdefault(event.table_name, set()).update(rows_of(payload))
    return {table: sorted(ids) for table, ids in out.items()}
