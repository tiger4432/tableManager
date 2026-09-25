# -*- coding: utf-8 -*-
"""Triage a flooded outbox: see what is queued, skip per-row events, re-fire them collapsed.

🔴 WHY THIS EXISTS (S-172). A quarantined 1,000-row chunk re-expands into 1,000 per-row
events so the poison row can be found. That is right when ONE chunk fails and ruinous when
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

from event_constants import CANCEL_MARK, CANCEL_REASON              # noqa: E402

OPERATOR = "operator"


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
    """Mark per-row pending events as handled-by-operator. Never deletes."""
    where = ["processed_chain = false", "table_name = :t",
             "NOT " + _has_key_sql(db, "payload", "row_ids")]
    params = {"t": table}
    if since:
        where.append("created_at >= :since")
        params["since"] = since
    sql = " AND ".join(where)
    n = db.execute(text("SELECT count(*) FROM database_outbox WHERE " + sql), params).scalar()
    print("per-row pending events on %s%s: %d" % (table, " since %s" % since if since else "", n))
    if not apply:
        print("   dry run - nothing changed. Re-run with --apply to skip them.")
        return n
    # ⚠️ SET-BASED ON POSTGRESQL, because production has ~660,000 of these and loading
    # them through the ORM to edit a dict would be its own outage. Elsewhere (the suite's
    # SQLite) the same edit is done row by row, so the LOGIC is exercised rather than
    # skipped - a test that cannot reach this branch certifies nothing about it.
    # 🔴 BOTH BRANCHES WRITE 「processed」 THROUGH ONE DEFINITION (총괄 8a1f32f99) - the flag,
    #   SUCCESS and the database time; the set-based one used to leave the time out.
    import event_constants
    from database.models import DatabaseOutbox

    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import func, update

        db.execute(
            update(DatabaseOutbox).where(text(sql)).values(
                **event_constants.processed_columns("SUCCESS"),
                payload=DatabaseOutbox.payload.op("||")(func.jsonb_build_object(
                    CANCEL_MARK, OPERATOR, CANCEL_REASON, reason)))
            .execution_options(synchronize_session=False), params)
    else:
        ids = [r[0] for r in db.execute(
            text("SELECT id FROM database_outbox WHERE " + sql), params).fetchall()]
        for event in db.query(DatabaseOutbox).filter(DatabaseOutbox.id.in_(ids)).all():
            event_constants.mark_cancelled(event, OPERATOR, reason)
    db.commit()
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
    """Re-fire the rows those cancelled events named, collapsed, through the replay path."""
    ids = [r[0] for r in db.execute(text(
        "SELECT DISTINCT payload->'data'->>'row_id' FROM database_outbox"
        " WHERE table_name = :t AND payload->>:mark = :who"
        "   AND payload->'data'->>'row_id' IS NOT NULL"), 
        {"t": table, "mark": CANCEL_MARK, "who": OPERATOR}).fetchall()]
    print("rows named by cancelled events on %s: %d  (-> %d collapsed group(s) of %d)"
          % (table, len(ids), (len(ids) + chunk - 1) // chunk if ids else 0, chunk))
    if not ids:
        return 0
    if not apply:
        print("   dry run - nothing replayed. Re-run with --apply.")
        return len(ids)

    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    from chain import replay

    rules = [r for r in replay.load_rules()
             if r.get("trigger_table") == table and r.get("enabled", True)]
    for rule in replay.order_rules(rules):
        # One run record per rule: the admin button's gate and cancel; the work stays here.
        # By `row_ids` - the rows these events named, which is also what makes a join's
        # companion half a legal subject (S-270); business keys would be refused for it.
        retroactive.run_here("chain_replay", {"rule": rule.get("name"), "row_ids": ids},
                             log=lambda *a, **k: None)
        print("   replayed %s" % rule.get("name"))
    return len(ids)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--count", action="store_true", help="what is queued, by shape and cause")
    p.add_argument("--cancel", action="store_true", help="skip per-row pending events")
    p.add_argument("--replay-cancelled", action="store_true",
                   help="re-fire the cancelled rows as collapsed groups")
    p.add_argument("--finish-stranded", action="store_true",
                   help="mark rows left processed-but-PENDING as SUCCESS")
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
