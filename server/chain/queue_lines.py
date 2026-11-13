"""The chain queue's LINES - the waiting rows by their line key (`event_constants.queue_line_key`), ranked by each
line's first id. `waiting_lines` finds them - `GET /admin/chain/queue` lists them and the slot dispatcher gives lines
from them (총괄 19f6a9277 - «배정자는 행이 아니라 줄을 본다»: a window of the first 200 ROWS held only a big replay's
rows, and the line behind it was never seen); `line_counts` counts the lines the screen draws.

🔴 THE WORK FOLLOWS THE LINES, NOT THE WAITING ROWS (owner 11-13, D's R4 split): a grouping of every waiting row took
0.86 s at 403k rows and 3.8-9.9 s at 1.6-1.9M - 41 stalls. `waiting_lines` walks `idx_outbox_line` one key at a time
(a skip scan) and reads each key's first row; `line_counts` reads at most COUNTED_TO + 1 rows of a line.
"""
from types import SimpleNamespace

import event_constants

#: Rows of one drawn line `line_counts` reads - past it a line says `counted_to` (lead 11-13). The slot window
#: (`chain.slots.WINDOW_ROWS`): a retried row is in a window a slot took off the line's head, and a retroactive run's
#: control row is its line's head, so both are read exactly through it. 1,000 took 1.29 s at 1.6M waiting rows with
#: all 200 drawn lines past it, 200 0.37 s (box board 11-13)
COUNTED_TO = 200

_KEY = "coalesce(run_id, transaction_id)"           # idx_outbox_line's expression - the line key of a row with one
_WAITING = "processed_chain = false"                # the partial indexes' predicate, spelled as they are


def waiting_lines(db, cap, chain_only=False):
    """-> the first `cap` waiting lines - live lines before a retroactive run's (소유자 10-15), each by its first id -
    as `SimpleNamespace(key, run, first_id, created_at, lines_total)`; `run` and `created_at` its first row's.
    `chain_only` the chain worker's rows only (`event_constants.chain_waiting`) - the slot dispatcher's; the queue
    screen lists control rows too (a waiting retroactive run, its ×). 총괄 11-07, B: open index requests held both
    slots for 40 min. A row with no run and no transaction is a line of its own (`queue_line_key`, 총괄 b3a4334db)."""
    from sqlalchemy import bindparam, select, text

    from database import models

    controls = " AND o.event_type NOT IN :controls" if chain_only else ""
    params = {"controls": sorted(event_constants.CONTROL_EVENT_TYPES)} if chain_only else {}

    def statement(sql):
        made = text(sql)
        return made.bindparams(bindparam("controls", expanding=True)) if chain_only else made

    # each key once, from the index (a skip scan), with its first row - a key whose rows are all control rows has none
    keyed = db.execute(statement(
        "WITH RECURSIVE k(key) AS ("
        " SELECT min(%(key)s) FROM database_outbox WHERE %(waiting)s"
        " UNION ALL SELECT (SELECT min(%(o_key)s) FROM database_outbox o WHERE o.%(waiting)s AND %(o_key)s > k.key)"
        " FROM k WHERE k.key IS NOT NULL)"
        " SELECT k.key, (SELECT min(o.id) FROM database_outbox o WHERE o.%(waiting)s AND %(o_key)s = k.key%(controls)s)"
        " FROM k WHERE k.key IS NOT NULL" % {"key": _KEY, "o_key": "coalesce(o.run_id, o.transaction_id)",
                                             "waiting": _WAITING, "controls": controls}), params).all()
    firsts = {key: first for key, first in keyed if first is not None}
    keyed_firsts = len(firsts)
    # the rows with no line key - each a line: the first `cap` of them, and how many
    alone = "FROM database_outbox o WHERE o.%s AND %s IS NULL%s" % (
        _WAITING, "coalesce(o.run_id, o.transaction_id)", controls)
    firsts.update(("%s%s" % (event_constants.QUEUE_ROW_KEY_PREFIX, first), first) for (first,) in db.execute(
        statement("SELECT o.id %s ORDER BY coalesce(o.run_id, o.transaction_id), o.id LIMIT %d" % (alone, int(cap))),
        params).all())
    outbox = models.DatabaseOutbox
    rows = {r.id: r for r in db.execute(select(outbox.id, outbox.run_id, outbox.created_at)
                                        .where(outbox.id.in_(sorted(firsts.values())))).all()} if firsts else {}
    lines = [(key, rows[first].run_id, first, rows[first].created_at) for key, first in firsts.items()]
    total = keyed_firsts + db.execute(statement("SELECT count(*) " + alone), params).scalar()
    lines.sort(key=lambda line: (line[1] is not None, line[2]))
    return [SimpleNamespace(key=key, run=run, first_id=first, created_at=at, lines_total=total)
            for key, run, first, at in lines[:cap]]


def line_counts(db, lines, counted_to=COUNTED_TO):
    """-> {line key: SimpleNamespace(events, rows, counted_to, pairs, max_retry, retrying, retroactive, last_failure)}
    of `lines` (`waiting_lines`), off each line's first `counted_to` + 1 waiting rows (`queue_line_rows`, its index) in
    ONE statement, grouped there: `counted_to` None when the line has no more rows, else `events` and `rows` are those
    of its first `counted_to`. `pairs` its (table, event type) groups; `retrying` whether a row waits to be tried
    again - an attempt charged, or a deadlock with a save that charged none; `retroactive` [(outbox id, payload)] of
    its retroactive control rows; `last_failure` its newest retrying row's {LAST_FAILURE, LAST_FAILURE_STAGE}, or None."""
    from sqlalchemy import and_, case, func, literal, null, or_, select, union_all

    from database import models

    if not lines:
        return {}
    outbox = models.DatabaseOutbox
    parts = [select(literal(line.key).label("key"), outbox.id, outbox.table_name, outbox.event_type, outbox.row_count,
                    outbox.retry_count, outbox.status, outbox.payload)
             .where(outbox.processed_chain == False,  # noqa: E712 - 부분 인덱스의 술어 철자
                    *event_constants.queue_line_rows(outbox, line.key))
             .order_by(outbox.id).limit(counted_to + 1).subquery()
             for line in lines]
    read = union_all(*(select(part, func.row_number().over(order_by=part.c.id).label("n")) for part in parts)).cte("u")
    counted, retro = read.c.n <= counted_to, read.c.event_type == event_constants.EVENT_RETROACTIVE_RUN
    retrying = read.c.status == "RETRYING"
    grouped = select(read.c.key, read.c.table_name, read.c.event_type, func.count(case((counted, 1))).label("events"),
                     func.sum(case((counted, func.coalesce(read.c.row_count, 1)), else_=0)).label("rows"),
                     func.max(case((counted, read.c.retry_count), else_=0)).label("max_retry"),
                     func.max(case((and_(counted, retrying), 1), else_=0)).label("retrying"),
                     func.max(read.c.n).label("last"), null().label("id"), null().label("control"),
                     null().label("said"), null().label("stage")
                     ).group_by(read.c.key, read.c.table_name, read.c.event_type)
    whole = select(read.c.key, read.c.table_name, read.c.event_type, null().label("events"), null().label("rows"),
                   null().label("max_retry"), null().label("retrying"), null().label("last"), read.c.id,
                   case((retro, read.c.payload)).label("control"),
                   case((retrying, read.c.payload[event_constants.LAST_FAILURE].as_string())).label("said"),
                   case((retrying, read.c.payload[event_constants.LAST_FAILURE_STAGE].as_string())).label("stage")
                   ).where(counted, or_(retro, retrying))
    said = {line.key: SimpleNamespace(events=0, rows=0, counted_to=None, pairs=[], max_retry=0, retrying=False,
                                      retroactive=[], last_failure=None) for line in lines}
    # the rows read whole first: a union's columns take the first select's types (the payload's, on sqlite)
    for row in db.execute(union_all(whole, grouped).order_by("key", "id")):
        line = said[row.key]
        if row.id is not None:                                  # a row read whole, in id order
            if row.control is not None:
                line.retroactive.append((row.id, row.control))
            if row.said is not None or row.stage is not None:
                line.last_failure = {event_constants.LAST_FAILURE: row.said,
                                     event_constants.LAST_FAILURE_STAGE: row.stage}
            continue
        if row.last > counted_to:
            line.counted_to = counted_to
        if not row.events:                                      # a group of the row past the count only
            continue
        line.events += row.events
        line.rows += row.rows or 0
        line.pairs.append((row.table_name, row.event_type))
        line.max_retry = max(line.max_retry, row.max_retry or 0)
        line.retrying = line.retrying or bool(row.retrying)
    for line in said.values():
        line.pairs.sort(key=lambda pair: (pair[0] or "", pair[1] or ""))      # by table, then kind - as listed
    return said


def waiting_by(db, column):
    """-> [(value, events, oldest created_at, retried)] of the waiting rows grouped by one outbox column - the queue's
    kinds (`event_type`) and the system catalogue's tables (`table_name`). Waiting rows only (`idx_outbox_unprocessed`)."""
    from sqlalchemy import func as _f
    from database import models

    outbox = models.DatabaseOutbox
    return (db.query(column, _f.count(), _f.min(outbox.created_at), _f.count().filter(outbox.retry_count > 0))
            .filter(outbox.processed_chain == False)  # noqa: E712 - 부분 인덱스의 술어 철자
            .group_by(column).order_by(column).all())
