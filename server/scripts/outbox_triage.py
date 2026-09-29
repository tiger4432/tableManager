# -*- coding: utf-8 -*-
"""Triage a flooded outbox: see what is queued, skip per-row events, re-fire them collapsed.

🔴 WHY THIS EXISTS (S-172). A quarantined 1,000-row chunk USED TO re-expand into per-row
events so the poison row could be found (retired, 총괄 c9ee06b34 - a queue may still hold them). That is right when ONE chunk fails and ruinous when
many do: production reached ~660,000 per-row pending events, and at the plumbing cost of a
group (~1.7 s) that queue is DAYS of work for rows that would take ~2 hours collapsed.
The owner cannot issue SQL, so the remedy has to be a command rather than a statement.

⛔ NOTHING IS DELETED, EVER. `--cancel` marks events processed with `cancelled_by` and a
reason written into the payload, so the row's history says an operator skipped it and why.
`--replay-cancelled` then re-fires exactly those rows through the ordinary replay path, so
the data arrives by the same road as always - just 1,000 at a time instead of one.

⚠️ DRY RUN IS THE DEFAULT. Every mode prints what it WOULD do and changes nothing until
`--apply`, which is the shape every operator script in this tree uses.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text                                          # noqa: E402

from admin import retroactive                                        # noqa: E402
from database.database import SessionLocal                           # noqa: E402


def _has_key_sql(db, column: str, key: str) -> str:
    """`payload ? 'k'` is the natural spelling and it is UNUSABLE here.

    ⚠️ On psycopg2 the JSONB `?` operator collides with the driver's own parameter
    placeholder, and on SQLite - which the suite runs - it does not exist at all. So the
    predicate is written per dialect: `jsonb_exists` says the same thing to PostgreSQL
    without the clash, and `json_extract` lets the tests exercise this logic rather than
    skipping it and certifying nothing.
    """
    if db.get_bind().dialect.name == "postgresql":
        return "jsonb_exists(%s::jsonb, '%s')" % (column, key)
    return "json_extract(%s, '$.%s') IS NOT NULL" % (column, key)


def _cause(payload: dict) -> str:
    """Where a pending event came from - the three that matter are told apart by shape."""
    if not isinstance(payload, dict):
        return "unknown"
    if payload.get("reexpanded_from"):
        return "quarantine re-expansion"
    tx = str(payload.get("transaction_id") or "")
    if "#row#" in tx:
        return "quarantine re-expansion"
    if tx.startswith("replay_") or payload.get("replay_run_id"):
        return "replay"
    return "original"


def count(db, table=None):
    rows = db.execute(text(("""
        SELECT table_name,
               %s AS collapsed,""" % _has_key_sql(db, "payload", "row_ids")) + """
               coalesce(payload->>'reexpanded_from','') <> '' AS reexpanded,
               coalesce(payload->>'transaction_id','')  AS tx,
               count(*)
          FROM database_outbox
         WHERE processed_chain = false
           AND (:t IS NULL OR table_name = :t)
         GROUP BY 1,2,3,4"""), {"t": table}).fetchall()
    buckets = {}
    for table_name, collapsed, reexpanded, tx, n in rows:
        shape = "collapsed" if collapsed else "per-row"
        cause = _cause({"reexpanded_from": reexpanded or None, "transaction_id": tx})
        buckets[(table_name, shape, cause)] = buckets.get((table_name, shape, cause), 0) + n
    if not buckets:
        print("pending outbox events: none")
        return buckets
    print("pending outbox events")
    for key in sorted(buckets, key=lambda k: -buckets[k]):
        print("   %-24s %-10s %-24s %d" % (key[0], key[1], key[2], buckets[key]))
    print("   %s total" % sum(buckets.values()))
    return buckets


def cancel(db, table, since=None, apply=False, reason="collapsed replay (S-172)"):
    """Mark per-row pending events as handled-by-operator. Never deletes.
    The body is `chain.set_aside`'s - the emergency stop's set-aside is the same act, widened
    to collapsed events and to a rule or transaction scope (총괄 2dbbfd1e5)."""
    from chain import set_aside

    found = set_aside.set_aside(db, tables=[table], since=since, per_row_only=True,
                                apply=apply, reason=reason)
    n = found["events"]
    print("per-row pending events on %s%s: %d" % (table, " since %s" % since if since else "", n))
    if not apply:
        print("   dry run - nothing changed. Re-run with --apply to skip them.")
        return n
    print("   skipped %d event(s) - NOT deleted; each payload now says who and why." % n)
    return n


def finish_stranded(db, apply=False):
    """Rows the scheduler finished without a status before c28ab7ad9 (총괄 8a1f32f99):
    `processed_chain = true` and `PENDING`. They read 「done · unexpected_status:PENDING」 and
    the notice sweep, which takes SUCCESS rows, never took them - so they stayed undelivered
    until the 7-day purge. `--apply` marks them SUCCESS through `mark_processed`.

    ⚠️ The time written is WHEN THIS RAN - when they really finished was never recorded.
    """
    import event_constants
    from sqlalchemy import func
    from database.models import DatabaseOutbox

    where = (DatabaseOutbox.processed_chain == True,                   # noqa: E712
             DatabaseOutbox.status == "PENDING")
    by_type = (db.query(DatabaseOutbox.event_type, func.count(), func.min(DatabaseOutbox.created_at),
                        func.max(DatabaseOutbox.created_at))
               .filter(*where).group_by(DatabaseOutbox.event_type).all())
    n = sum(row[1] for row in by_type)
    print("finished but PENDING: %d" % n)
    for event_type, count_, first, last in by_type:
        print("   %-18s %6d   %s .. %s" % (event_type, count_, first, last))
    if not apply:
        print("   dry run - nothing changed. Re-run with --apply to mark them SUCCESS.")
        return n
    for event in db.query(DatabaseOutbox).filter(*where).all():
        event_constants.mark_processed(event, "SUCCESS")
    db.commit()
    print("   marked %d row(s) SUCCESS - the notice sweep takes them next." % n)
    return n


def replay_cancelled(db, table, apply=False, chunk=1000):
    """Re-fire the rows the events set aside on `table` named - through the registry's
    `rerun_set_aside`, which replays them once and cascades nothing (소유자 09-27)."""
    from chain import set_aside

    ids = set_aside.rows_set_aside(db, tables=[table]).get(table, [])
    print("rows named by events set aside on %s: %d" % (table, len(ids)))
    if not ids:
        return 0
    if not apply:
        print("   dry run - nothing replayed. Re-run with --apply.")
        return len(ids)
    retroactive.run_here("rerun_set_aside", {"tables": table}, log=lambda *a, **k: None)
    print("   replayed through rerun_set_aside")
    return len(ids)


def set_aside_scope(db, args):
    """--set-aside / --rerun-set-aside: the registry's operations, the button's gate and record."""
    params = {k: v for k, v in (("tables", args.tables), ("rules", args.rules),
                                ("transactions", args.transactions)) if v}
    op = "set_aside" if args.set_aside else "rerun_set_aside"
    if op == "set_aside":
        params["reason"] = args.reason
    if not args.apply:
        print(retroactive.count(db, op, params))
        print("   dry run - nothing changed. Re-run with --apply.")
        return 0
    print(retroactive.run_here(op, params, log=print)["result"])
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--count", action="store_true", help="what is queued, by shape and cause")
    p.add_argument("--cancel", action="store_true", help="skip per-row pending events")
    p.add_argument("--replay-cancelled", action="store_true",
                   help="re-fire the cancelled rows as collapsed groups")
    p.add_argument("--finish-stranded", action="store_true",
                   help="mark rows left processed-but-PENDING as SUCCESS")
    p.add_argument("--set-aside", action="store_true",
                   help="set waiting chain events aside (collapsed ones too) - the emergency "
                        "stop; needs --tables, --rules or --transactions and --reason")
    p.add_argument("--rerun-set-aside", action="store_true",
                   help="replay the rows events set aside named - each rule once, nothing "
                        "downstream")
    p.add_argument("--tables", help="comma-separated tables (with --set-aside / --rerun-set-aside)")
    p.add_argument("--rules", help="comma-separated chain rules")
    p.add_argument("--transactions", help="comma-separated transaction ids")
    p.add_argument("--reason", help="why - written into each event set aside")
    p.add_argument("--table")
    p.add_argument("--per-row", action="store_true",
                   help="required with --cancel: says the target is the per-row events")
    p.add_argument("--since", help="only events created at or after this timestamp")
    p.add_argument("--chunk", type=int, default=1000)
    p.add_argument("--apply", action="store_true", help="actually change something")
    args = p.parse_args(argv)

    db = SessionLocal()
    try:
        if args.finish_stranded:
            finish_stranded(db, args.apply)
            return 0
        if args.set_aside or args.rerun_set_aside:
            try:
                return set_aside_scope(db, args)
            except retroactive.RetroactiveRefused as e:
                print(f"REFUSED: {e}")
                return 2
        if args.count or not (args.cancel or args.replay_cancelled):
            count(db, args.table)
            return 0
        if args.cancel:
            if not args.table or not args.per_row:
                print("REFUSED: --cancel needs --table and --per-row, so the blast radius "
                      "is written down rather than assumed.")
                return 2
            cancel(db, args.table, args.since, args.apply)
            return 0
        if args.replay_cancelled:
            if not args.table:
                print("REFUSED: --replay-cancelled needs --table.")
                return 2
            try:
                replay_cancelled(db, args.table, args.apply, args.chunk)
            except retroactive.RetroactiveRefused as e:
                print(f"REFUSED: {e}")
                return 2
            except retroactive.RunCancelled as e:
                print(f"CANCELLED: {e}")
                return 2
            return 0
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
