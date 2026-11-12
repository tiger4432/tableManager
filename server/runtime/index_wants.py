"""A slow grid read asks for an automatic index (총괄 ff7890892, 소유자 「쓰이는 칸만」).

The read only remembers and queues (`want`) - each (table, columns, why) once a process. After it has answered, one
thread here asks the database whether an index already serves it, whether the table already holds
`auto_index_per_table` automatic indexes, and whether the same ask is already waiting; if none, it writes one
INDEX_WANTED row - the outbox control event the scheduler's index line (`runtime.maintenance_line`) takes and builds
(`models.ensure_auto_indexes`). Nothing is written in the read's own path.

A slow reference view (소유자 10-14 «넓혀») - its display read or a candidate probe - asks through the same `want`: its
plan is read once a process on the same thread (`want_plan` - EXPLAIN, not run), and each table it scans whole through
a filter is wanted - an equal or IN column as a slow filter, a LIKE or ILIKE one as a slow search (the declared search
index's trigram). A read whose pattern was too short to judge does not use the view's once (총괄 10-14).

A slow grid page's keys statement (`read_keys`) is judged by its plan the same way (lead 11-10, owner «인덱스 표시
있는데»): a filter column's index can be there and the plan walk the sort's order instead, checking the filter row by
row - then (the equal-filtered columns, the sort's column, row_id) is wanted (`want_page_plan`).
"""
import contextlib
import contextvars
import json
import logging
import queue
import re
import threading
import time
import uuid
from error_said import told

logger = logging.getLogger("Server")

#: A refused ask is asked again by a slow read this long after (lead 11-10): a refusal - an index serves it, the table
#: is at its cap, the same ask waits - is undone by an index built or dropped, and once a process left the owner's slow
#: page unasked until a restart. Not a setting (owner «줄이려는데 왜 키워»); a written ask stays once a process.
ASK_AGAIN_SECONDS = 600

#: key -> when this process asked it; None once its ask was written (`_asked`) - never again
_ASKED = {}
#: (table, column) -> what the last ask on that column came to in this process (`last_word`)
_WORDS = {}
_QUEUE = queue.Queue()
_THREAD = [None]
_LOCK = threading.Lock()
#: The keys statement of the grid read running in this context (`reading`, `read_keys`)
_KEYS = contextvars.ContextVar("index_wants_keys", default=None)


def _first(key):
    """Has this process not asked `key` yet, or was it refused ASK_AGAIN_SECONDS ago - and the thread that takes the
    queue is up."""
    with _LOCK:
        asked = _ASKED.get(key, False)
        if asked is None or (asked is not False and time.monotonic() - asked < ASK_AGAIN_SECONDS):
            return False
        _ASKED[key] = time.monotonic()
        if _THREAD[0] is None:
            _THREAD[0] = threading.Thread(target=_asking, name="index-wants", daemon=True)
            _THREAD[0].start()
    return True


def _asked(key, table, columns, why, seconds, bind):
    """`ask` on the asking thread: a written ask is never asked again; one that broke is said as its columns' last word
    too (lead 11-11 ㄴ: `last_word` None means «queued, no answer yet» only)."""
    try:
        written = ask(table, columns, why, seconds, bind)
    except Exception as exc:                                        # noqa: BLE001 - the next ask goes on
        tell(table, columns, "an automatic index on %s (%s) was not asked: %s: %s"
             % (table, ", ".join(columns), type(exc).__name__, told(exc)), logging.ERROR)
        return
    if written:
        with _LOCK:
            _ASKED[key] = None


def want(table, columns, why, seconds, bind):
    """Queue the ask - unless this process wrote it, or refused it under ASK_AGAIN_SECONDS ago."""
    columns = list(columns)
    key = (table, tuple(columns), why)
    if _first(key):
        _QUEUE.put(("an automatic index on %s (%s) was not asked" % (table, ", ".join(columns)),
                    lambda: _asked(key, table, columns, why, seconds, bind)))


@contextlib.contextmanager
def reading():
    """A grid read: what its page keeps with `read_keys` -> the dict it is kept in."""
    kept = {}
    token = _KEYS.set(kept)
    try:
        yield kept
    finally:
        _KEYS.reset(token)


def read_keys(query, order):
    """The page's keys statement (an ORM query, not run here) and its ORDER BY - kept for a slow read's plan."""
    kept = _KEYS.get()
    if kept is not None:
        kept.update(query=query, order=order)


def want_page_plan(table, kept, filtered, seconds, bind):
    """A slow grid page whose keys statement was kept (`read_keys`) and that `filtered` columns narrow: its plan read
    on this thread once a shape (table, filtered columns, order) per ASK_AGAIN_SECONDS (`_page_plan_wants`). An order
    that is not the table's own columns (the entered order's place lookup) has no index to want."""
    from sqlalchemy import Column

    if not filtered or kept.get("query") is None or bind.dialect.name != "postgresql":
        return
    order = [getattr(clause, "element", clause) for clause in kept["order"]]
    order = [getattr(column, "name", None) if isinstance(column, Column) else None for column in order]
    if not _first(("page", table, tuple(filtered), tuple(order))):
        return
    if None in order:
        logger.info("[Indexes] %s took %.1f s - its order is not a column of it; no index is asked for it",
                    table, seconds)
        return
    compiled = kept["query"].statement.compile(dialect=bind.dialect, compile_kwargs={"render_postcompile": True})
    _QUEUE.put(("the plan of a %s page was not read" % table,
                lambda: _page_plan_wants(table, str(compiled), dict(compiled.params), filtered, order, seconds, bind)))


def want_plan(label, view, statement, params, seconds, bind):
    """A slow read (`statement`, any wrap) of the reference view whose query is `view`: its plan read once a process for
    that view, then `want` for each filter it scans a table whole through (`scanned_filters`)."""
    if bind.dialect.name == "postgresql" and _first(("plan", view)):
        _QUEUE.put(("the plan of reference view %s was not read" % label,
                    lambda: _plan_wants(label, view, statement, dict(params), seconds, bind)))


def _asking():
    while True:
        what, job = _QUEUE.get()
        try:
            job()
        except Exception as exc:                                    # noqa: BLE001 - the next ask goes on
            logger.error("[Indexes] %s: %s: %s", what, type(exc).__name__, told(exc))


def _plan_wants(label, view, statement, params, seconds, bind):
    from sqlalchemy import text

    from database import crud

    with bind.connect() as connection:
        plan = connection.execute(text("EXPLAIN (FORMAT JSON) " + statement), params).scalar()
    found = scanned_filters(json.loads(plan) if isinstance(plan, str) else plan)
    with _LOCK:                       # judged - once a process; judged nothing there - the next slow read looks
        if any(reason for _table, _column, _why, reason in found):
            _ASKED.pop(("plan", view), None)
        else:
            _ASKED[("plan", view)] = None
    if not found:
        logger.info("[Indexes] reference view %s took %.1f s - its plan scans no table whole through an equal, IN or "
                    "LIKE filter; no index asked", label, seconds)
    for table, column, why, reason in found:
        reason = reason or (None if table in crud.TABLE_CONFIG else "not a table the product declares")
        if reason:
            logger.info("[Indexes] reference view %s took %.1f s - %s (%s) not asked for a %s: %s",
                        label, seconds, table, column, why, reason)
        else:
            want(table, [column], why, seconds, bind)


def _page_plan_wants(table, statement, params, filtered, order, seconds, bind):
    from database import models

    raw = bind.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("EXPLAIN (FORMAT JSON) " + statement, params)
        plan = cursor.fetchone()[0]
        cursor.close()
    finally:
        raw.close()
    equal, by_row, sort = page_plan(json.loads(plan) if isinstance(plan, str) else plan, table)
    equal = [column for column in filtered if column in equal]
    if not equal or not (by_row or sort):
        logger.info("[Indexes] a %s page took %.1f s - its plan %s; no index over its filter and order asked", table,
                    seconds, "compares no filter column to one value" if not equal
                    else "reads %s by its index and leaves no sort" % ", ".join(equal))
        return
    want(table, equal + [column for column in order if column not in equal and column != "row_id"],
         models.AUTO_SLOW_SORT, seconds, bind)


def page_plan(plan, table):
    """(equal, by row, sorted) of a page's `plan` (EXPLAIN FORMAT JSON) over `table`: the columns its scans of the table
    compare to one value - an index condition or a filter -, those a scan checks row by row (a Filter: the rows came
    another way - the order's index, or the whole table), and whether a Sort is left."""
    equal, by_row, sort = [], [], False

    def walk(node):
        nonlocal sort
        sort = sort or node.get("Node Type") in ("Sort", "Incremental Sort")
        if node.get("Relation Name") == table:
            for key in ("Index Cond", "Recheck Cond", "Filter"):
                for column, op, rhs in _conditions(node.get(key)):
                    if op == "=" and _CONSTANT.match(rhs) and not rhs.startswith("ANY"):
                        equal.append(column)
                        if key == "Filter":
                            by_row.append(column)
        for child in node.get("Plans") or ():
            walk(child)

    for each in plan or ():
        walk(each.get("Plan") or {})
    return equal, by_row, sort


#: One condition of a scan's Filter as EXPLAIN prints it: [alias.]column, a cast, the operator, the rest.
#: The right side of an equal is one value a scan: a literal, a parameter, or another relation's column (a LATERAL's
#: key - `"*VALUES*".column2`) - not this scan's own column.
_CONDITION = re.compile(r'^\(?(?:(?:"(?:[^"]|"")+"|\w+)\.)?(?P<column>"(?:[^"]|"")+"|\w+)\)?(?:::[\w ]+(?:\[\])?)?'
                        r'\s+(?P<op>~~\*|~~|=)\s+(?P<rhs>.+)$', re.S)
_CONSTANT = re.compile(r"^(?:ANY \()?(?:'|-?\d|\$\d)")
_OUTER = re.compile(r'^\(?(?P<alias>"(?:[^"]|"")+"|\w+)\.')
_LITERAL = re.compile(r"^'((?:[^']|'')*)'")
#: A trigram index reads three characters in a row - a pattern with fewer between its wildcards is not narrowed.
TRIGRAM_LETTERS = 3


def scanned_filters(plan) -> list:
    """[(table, column, why, reason or None)] - each column a Seq Scan of `plan` (EXPLAIN FORMAT JSON) filters on, ANDed
    (an OR filter is left whole): equal or IN -> `AUTO_SLOW_FILTER`, LIKE or ILIKE -> `AUTO_SLOW_SEARCH`. A reason is a
    judgment not reached: a pattern a trigram index cannot narrow."""
    from database import models

    found = []

    def walk(node):
        if node.get("Node Type") == "Seq Scan" and node.get("Filter") and node.get("Relation Name"):
            for column, op, rhs in _conditions(node["Filter"]):
                outer = _OUTER.match(rhs)
                if op == "=":
                    if _CONSTANT.match(rhs) or (outer and outer["alias"].strip('"') != node.get("Alias")):
                        found.append((node["Relation Name"], column, models.AUTO_SLOW_FILTER, None))
                    continue
                literal = _LITERAL.match(rhs)
                pattern = literal.group(1).replace("''", "'") if literal else None
                short = pattern is not None and max(
                    (len(run) for run in re.split(r"(?<!\\)[%_]", pattern)), default=0) < TRIGRAM_LETTERS
                found.append((node["Relation Name"], column, models.AUTO_SLOW_SEARCH,
                              "the pattern '%s' has under %d characters between its wildcards - a trigram index "
                              "cannot narrow it" % (pattern, TRIGRAM_LETTERS) if short else None))
        for child in node.get("Plans") or ():
            walk(child)

    for each in plan or ():
        walk(each.get("Plan") or {})
    out = []
    for item in found:
        if item not in out:
            out.append(item)
    return out


def _conditions(expression):
    """(column, operator, right side) of each ANDed term of `expression` that compares one column (`_CONDITION`)."""
    for term in _terms(expression or ""):
        match = _CONDITION.match(term.strip())
        if match:
            column = match["column"]
            yield (column[1:-1].replace('""', '"') if column.startswith('"') else column), match["op"], \
                match["rhs"].strip()


def _terms(expression):
    """`expression`'s ANDed terms, unwrapped - none when it ORs at its top."""
    expression = expression.strip()
    while _wrapped(expression):
        expression = expression[1:-1].strip()
    parts, depth, quote, start, i = [], 0, None, 0, 0
    while i < len(expression):
        ch = expression[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expression.startswith(" OR ", i):
            return []
        elif depth == 0 and expression.startswith(" AND ", i):
            parts.append(expression[start:i])
            start = i = i + 5
            continue
        i += 1
    parts.append(expression[start:])
    return parts if len(parts) == 1 else [term for part in parts for term in _terms(part)]


def _wrapped(expression):
    """Does the parenthesis `expression` opens with close at its very end."""
    if not expression.startswith("("):
        return False
    depth, quote = 0, None
    for i, ch in enumerate(expression):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(expression) - 1
    return False


def ask(table, columns, why, seconds, bind):
    """One INDEX_WANTED row, unless an index serves it, the table is at its cap, or the same ask waits. -> written.
    `seconds` the slow read's time - None for a walk's scan, asked before it reads."""
    from sqlalchemy.orm import Session

    import event_constants
    from database import models
    from parsers.directory_watcher import auto_index_per_table

    if bind.dialect.name != "postgresql":
        return False
    took = "" if seconds is None else " took %.1f s" % seconds
    db = Session(bind=bind)
    try:
        if why == models.AUTO_SLOW_SEARCH and not models.has_trigram(db.connection()):
            tell(table, columns, "an automatic index on %s (%s) is not asked for a %s: %s"
                 % (table, ", ".join(columns), why, models.PG_TRGM_MISSING))
            return False
        held = models.catalogue_indexes(db.connection().connection.dbapi_connection, table)
        served = [index["name"] for index in held if models.auto_index_serves(index, columns, why)]
        if served:
            tell(table, columns, "%s (%s)%s - not asked for a %s: %s already serves it"
                 % (table, ", ".join(columns), took, why, served[0]))
            return False
        if sum(1 for index in held if index["name"].startswith(models.AUTO_INDEX_PREFIX)) >= auto_index_per_table():
            tell(table, columns, "%s (%s)%s - not asked for a %s: %s holds auto_index_per_table (%d) automatic "
                 "indexes" % (table, ", ".join(columns), took, why, table, auto_index_per_table()))
            return False
        waiting = (db.query(models.DatabaseOutbox.payload)
                   .filter(models.DatabaseOutbox.event_type == event_constants.EVENT_INDEX_WANTED,
                           models.DatabaseOutbox.table_name == table,
                           models.DatabaseOutbox.processed_chain.is_(False)).all())
        if any((json.loads(row.payload or "{}").get("columns"), json.loads(row.payload or "{}").get("why"))
               == (columns, why) for row in waiting):
            tell(table, columns, "%s (%s)%s - the same %s ask is already waiting"
                 % (table, ", ".join(columns), took, why))
            return False
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()), table_name=table, event_type=event_constants.EVENT_INDEX_WANTED,
            payload=json.dumps({"table": table, "columns": columns, "why": why,
                                "seconds": None if seconds is None else round(seconds, 3)}),
            processed_chain=False))
        db.commit()
    finally:
        db.close()
    tell(table, columns, "asked for an automatic index on %s (%s) - %s%s" % (
        table, ", ".join(columns), why, "" if seconds is None else ", the read took %.1f s" % seconds))
    return True


def tell(table, columns, said, level=logging.INFO):
    """An ask's outcome on the log, and each of its columns' last word in this process (`last_word`) - and a walk's word
    on a key column it does not ask (`trace_router._engine_reading`)."""
    logger.log(level, "[Indexes] %s", said)
    with _LOCK:
        for column in columns:
            _WORDS[(table, column)] = said


def last_word(table, column):
    """What the last ask on `table`'s `column` came to in this process - None when none was asked here."""
    return _WORDS.get((table, column))


def index_name(table, columns, why):
    """The name of the index an ask wants - a key's unique index, or an automatic one."""
    from database import models
    from migrations import add_business_key_unique_index as uq

    return uq.unique_index_name(table) if why == models.KEY_UNIQUE else models.auto_index_name(table, columns, why)


def taken(db):
    """The INDEX_WANTED rows still open (`processed_chain` false): [(row, (table, columns, why))], oldest first - a row
    it cannot read comes with nothing (its line says so). The scheduler's index line closes each by what happened to
    its index (`runtime.maintenance_line`, 총괄 11-07 ㄱ): built or already there, or ruled out; one put off stays open
    and is taken again - so a scheduler started again takes it from here."""
    import event_constants
    from database import models

    rows = (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type == event_constants.EVENT_INDEX_WANTED,
                    models.DatabaseOutbox.processed_chain.is_(False))
            .order_by(models.DatabaseOutbox.id.asc()).all())
    out = []
    for row in rows:
        try:
            asked = json.loads(row.payload or "{}")
            out.append((row, (str(asked["table"]), [str(c) for c in asked["columns"]], str(asked["why"]))))
        except (TypeError, ValueError, KeyError) as exc:
            logger.error("[Indexes] INDEX_WANTED %s is not read: %s: %s", row.id, type(exc).__name__, exc)
            out.append((row, None))
    return out
