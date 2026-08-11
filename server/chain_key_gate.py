"""A chain may not emit a row whose key columns are not filled. ONE gate, not seven.

WHY THIS MODULE EXISTS
----------------------
A mapper that cannot resolve an identity for a row used to emit the row anyway. The
write path then behaved exactly as designed and that was the problem: a blank key column
writes nothing (``818c9c0``), so the row landed with ``business_key_val`` NULL. Nothing
can address it - not a re-push, not an upsert, not an operator - so the next delivery of
the same data created ANOTHER one, and the table grew a population of unreachable rows
(measured 2026-08-11: ~170,000 in one table). One such row later made
``GET /api/maps/alignment/worklist`` answer 500 for an entire request (``c4a3159``).

Three of the four places that compose a unit key already guarded against this by hand -
``dt_alignment_metadata_mapper``, ``core_alignment_mapper``, ``dt_inventory_metadata_mapper``.
The fourth did not. **The fix is not to make it four.** ``server/mappers/*.py`` is
gitignored by design (only ``*.py.sample`` ships), so a guard written into a mapper does
not reach a deployment at all, and a mapper written next month starts with no guard.
This module is TRACKED and sits on the funnel every chain-emitted row already passes
through, so it deploys and it cannot be forgotten.

WHERE THE FUNNEL IS
-------------------
Two call sites, one gate:

  * ``chain_ingestion_worker.process_chain_transaction_group`` - the ``write_batches``
    loop. Every chain output converges there: per-row mapper returns, batch mapper
    returns, ``map_metadata_updates`` and the ``replace_map`` scoped batches.
  * ``chain_replay._apply_replay_batch`` - the same mapper contract, replayed. Leaving it
    out would recreate the three-of-four omission at a coarser grain.

WHY NOT IN ``crud.apply_batch_updates``
---------------------------------------
That IS the single funnel for every write, and a gate there would cover ingestion and the
grid too - which is exactly why it is the wrong place. ``818c9c0`` ruled that a keyless
row is a legitimate shape from manual grid work and NULL is its accepted spelling, and the
live database carries such rows today. Refusing them at the write path would be a POLICY
change for two paths that did not ask for one. The ruling this module implements is about
what a CHAIN may emit, so it is enforced where the chain emits.

WHY NOT IN ``chain_bindings``
-----------------------------
That module resolves a column NAME from declarations and is deliberately pure. This one
judges a ROW and keeps a process-lifetime counter so the refusal is answerable from
another process. Same family, different lifetime; folding a counter into the resolver
would make the resolver stateful for no gain.

CONSISTENT WITH ``818c9c0``, NOT A SECOND OPINION ON IT
-------------------------------------------------------
That commit ruled a blank key column **writes nothing at all**, because clearing a
derived key destroys it and the re-push cannot put it back. This gate never clears
anything and never writes: it declines to emit the row in the first place, which is the
same ruling applied one step earlier. A row that already exists is untouched - refusing an
UPDATE for it is impossible here, because an item that resolves onto an existing row
(``row_id`` or ``business_key_val``) is never refused.

REFUSING IS LOUD
----------------
A silent skip is the same defect as a bad write - today cost a full day because the drop
was invisible. Every refusal is counted by ``(table, column)`` for the life of the
process and digested into the chain worker's heartbeat note, which is the cross-process
channel ``/health`` already reads for ``crud.undeclared_column_drops()``. The same
escalating-log discipline is reused: announce on the 1st, 10th, 100th ... occurrence, so a
fixed deployment and a broken one do not produce identical logs.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


#: The one reason this gate refuses. Named rather than counted so it reads beside
#: `crud.DROP_UNDECLARED_COLUMN` / `DROP_SYSTEM_COLUMN` in the same vocabulary.
REFUSAL_UNKEYED_ROW = "unkeyed_row"

# Both caps exist for the reason `crud`'s drop report has them: every row detail here
# comes from a PAYLOAD, so a malformed source must not be able to grow the report
# without limit. COUNTS are never capped - only the named detail is.
MAX_REFUSAL_ROWS = 20
MAX_REFUSAL_COLUMNS = 64

_ANNOUNCE_AT = frozenset([1, 10, 100, 1000, 10000, 100000, 1000000])

# (table, column) -> count, for the life of this process. Bounded by the DECLARED key
# columns of the tables this process writes, so it needs no budget of its own.
_refusals: dict = {}
# table -> rows refused. A row missing three key columns is three column counts but one
# row, and the operator's question ("how many rows did I lose?") is this one.
_refused_rows: dict = {}


def refusals() -> dict:
    """Snapshot of refusals so far in THIS process: ``{(table, column): count}``.

    Public for the same reason `crud.undeclared_column_drops` is: the refusals happen in
    the chain worker and the question they raise has to be answerable from the web
    server, which is a different process. Returns a copy.
    """
    return dict(_refusals)


def refused_rows() -> dict:
    """Snapshot of refused ROW counts so far in this process: ``{table: count}``."""
    return dict(_refused_rows)


def reset_counters():
    """Drop the process counters. For tests only - nothing in production calls this."""
    _refusals.clear()
    _refused_rows.clear()


_NOTE_TOP_N = 5


def note():
    """Heartbeat digest, or ``None`` while nothing is being refused.

    ``None`` on a healthy worker is load-bearing: it keeps a clean deployment's heartbeat
    byte-identical to what it is today.
    """
    if not _refusals:
        return None
    top = sorted(_refusals.items(), key=lambda kv: -kv[1])[:_NOTE_TOP_N]
    parts = [f"{t}.{c}={n}" for (t, c), n in top]
    if len(_refusals) > len(top):
        parts.append(f"(+{len(_refusals) - len(top)} more)")
    return (f"chain unkeyed-row refusals: rows={sum(_refused_rows.values())} "
            f"blank key columns: " + ", ".join(parts))


def _record(table_name: str, rule_names, columns: dict, rows: int):
    """Count one batch's refusals and announce on the 1st, 10th, 100th ... of each."""
    _refused_rows[table_name] = _refused_rows.get(table_name, 0) + rows
    announce = []
    for col, n in columns.items():
        key = (table_name, col)
        before = _refusals.get(key, 0)
        total = before + n
        _refusals[key] = total
        # Crossing an announce threshold inside this batch, not landing exactly on one:
        # a 1,000-row batch would otherwise step over every threshold at once and say
        # nothing.
        if any(before < t <= total for t in _ANNOUNCE_AT):
            announce.append((col, total))
    return announce


def screen(table_name: str, items, rule_names=(), transaction_id=None):
    """Split `items` into (kept, report). Refused items carry no resolvable identity.

    `items` are `schemas.GeneralUpdateItem`s - the gate runs AFTER the batch is built, so
    every shape a mapper may return (dict or model) has already been normalised by one
    validator instead of by this function.

    Returns the surviving list and a report dict whose shape is stable whether or not
    anything was refused, so a caller may read `refused_rows` without testing for the
    key. The report is deliberately the same vocabulary as `crud`'s `drop_report`:
    by column, by row, with the caller's own business key, counts uncapped and detail
    capped, and the report states what it withheld.
    """
    from database import crud

    report = {
        "table": table_name,
        "reason": REFUSAL_UNKEYED_ROW,
        "rules": sorted({r for r in (rule_names or ()) if r}),
        "transaction_id": transaction_id,
        "refused_rows": 0,
        "by_column": {},
        "columns_omitted": 0,
        "rows": [],
        "rows_omitted": 0,
    }

    kept = []
    by_column = report["by_column"]
    for index, item in enumerate(items or ()):
        unfilled = crud.unfilled_key_columns(table_name, item)
        if not unfilled:
            kept.append(item)
            continue

        report["refused_rows"] += 1
        for col in unfilled:
            if col in by_column:
                by_column[col] += 1
            elif len(by_column) < MAX_REFUSAL_COLUMNS:
                by_column[col] = 1
            else:
                report["columns_omitted"] += 1
        if len(report["rows"]) < MAX_REFUSAL_ROWS:
            report["rows"].append({
                "index": index,
                "business_key_val": item.business_key_val,
                "updated_by": item.updated_by,
                "unfilled": list(unfilled),
            })

    report["rows_omitted"] = max(0, report["refused_rows"] - len(report["rows"]))

    if report["refused_rows"]:
        announce = _record(table_name, report["rules"], by_column,
                           report["refused_rows"])
        if announce:
            logger.warning(
                "[ChainKeyGate] Table: '%s' | TX: %s | rule(s): %s | REFUSED %d of %d "
                "row(s): the chain produced no value for their key column(s) %s, so the "
                "row would have been written with no business key and nothing could ever "
                "address it. Nothing was written for them. Fix the mapper or the source "
                "data. Refused so far in this process: %s.",
                table_name, transaction_id, ", ".join(report["rules"]) or "<unknown>",
                report["refused_rows"], len(items or ()),
                sorted(by_column), ", ".join(f"{c}={n}" for c, n in announce))
        else:
            logger.info(
                "[ChainKeyGate] Table: '%s' | TX: %s | refused %d unkeyed row(s) "
                "(key column(s) %s). Announcing at each power of ten; totals are in the "
                "heartbeat note.",
                table_name, transaction_id, report["refused_rows"], sorted(by_column))

    return kept, report
