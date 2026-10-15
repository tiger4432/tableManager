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
"""
import json
import logging
import queue
import re
import threading
import uuid

logger = logging.getLogger("Server")

_ASKED = set()
_QUEUE = queue.Queue()
_THREAD = [None]
_LOCK = threading.Lock()


def _first(key):
    """Has this process not seen `key` yet - and the thread that takes the queue is up."""
    with _LOCK:
        if key in _ASKED:
            return False
        _ASKED.add(key)
        if _THREAD[0] is None:
            _THREAD[0] = threading.Thread(target=_asking, name="index-wants", daemon=True)
            _THREAD[0].start()
    return True


def want(table, columns, why, seconds, bind):
    """Queue the ask - the first time this process sees it."""
    columns = list(columns)
    if _first((table, tuple(columns), why)):
        _QUEUE.put(("an automatic index on %s (%s) was not asked" % (table, ", ".join(columns)),
                    lambda: ask(table, columns, why, seconds, bind)))


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
            logger.error("[Indexes] %s: %s: %s", what, type(exc).__name__, exc)


def _plan_wants(label, view, statement, params, seconds, bind):
    from sqlalchemy import text

    from database import crud

    with bind.connect() as connection:
        plan = connection.execute(text("EXPLAIN (FORMAT JSON) " + statement), params).scalar()
    found = scanned_filters(json.loads(plan) if isinstance(plan, str) else plan)
    if any(reason for _table, _column, _why, reason in found):     # judged nothing there - the next slow read looks
        with _LOCK:
            _ASKED.discard(("plan", view))
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
            for term in _terms(node["Filter"]):
                match = _CONDITION.match(term.strip())
                if not match:
                    continue
                column = match["column"]
                column = column[1:-1].replace('""', '"') if column.startswith('"') else column
                rhs = match["rhs"].strip()
                outer = _OUTER.match(rhs)
                if match["op"] == "=":
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
    """One INDEX_WANTED row, unless an index serves it, the table is at its cap, or the same ask waits. -> written."""
    from sqlalchemy.orm import Session

    import event_constants
    from database import models
    from parsers.directory_watcher import auto_index_per_table

    if bind.dialect.name != "postgresql":
        return False
    db = Session(bind=bind)
    try:
        if why == models.AUTO_SLOW_SEARCH and not models.has_trigram(db.connection()):
            logger.info("[Indexes] an automatic index on %s (%s) is not asked for a %s: %s",
                        table, ", ".join(columns), why, models.PG_TRGM_MISSING)
            return False
        held = models.catalogue_indexes(db.connection().connection.dbapi_connection, table)
        served = [index["name"] for index in held if models.auto_index_serves(index, columns, why)]
        if served:
            logger.info("[Indexes] %s (%s) took %.1f s - not asked for a %s: %s already serves it",
                        table, ", ".join(columns), seconds, why, served[0])
            return False
        if sum(1 for index in held if index["name"].startswith(models.AUTO_INDEX_PREFIX)) >= auto_index_per_table():
            logger.info("[Indexes] %s (%s) took %.1f s - not asked for a %s: %s holds auto_index_per_table (%d) "
                        "automatic indexes", table, ", ".join(columns), seconds, why, table, auto_index_per_table())
            return False
        waiting = (db.query(models.DatabaseOutbox.payload)
                   .filter(models.DatabaseOutbox.event_type == event_constants.EVENT_INDEX_WANTED,
                           models.DatabaseOutbox.table_name == table,
                           models.DatabaseOutbox.processed_chain.is_(False)).all())
        if any((json.loads(row.payload or "{}").get("columns"), json.loads(row.payload or "{}").get("why"))
               == (columns, why) for row in waiting):
            logger.info("[Indexes] %s (%s) took %.1f s - the same %s ask is already waiting",
                        table, ", ".join(columns), seconds, why)
            return False
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()), table_name=table, event_type=event_constants.EVENT_INDEX_WANTED,
            payload=json.dumps({"table": table, "columns": columns, "why": why, "seconds": round(seconds, 3)}),
            processed_chain=False))
        db.commit()
    finally:
        db.close()
    logger.info("[Indexes] asked for an automatic index on %s (%s) - %s, the read took %.1f s",
                table, ", ".join(columns), why, seconds)
    return True


def taken(db):
    """The INDEX_WANTED rows not taken yet (`processed_chain` false - the scheduler's index line takes them): [(row, (table, columns, why))] - a row it cannot read is
    taken with nothing (its line says so)."""
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
