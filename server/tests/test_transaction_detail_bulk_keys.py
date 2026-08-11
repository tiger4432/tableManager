"""`/audit_logs/transaction/{tx}` resolved deleted-row business keys ONE LOG AT A TIME.

`get_deleted_row_business_key` costs up to two SELECTs per call and was invoked inside
the per-log loop, in BOTH branches of the route (the in-memory cache branch and the DB
branch). The route's default `limit` is 20,000, so one click on a large transaction
could issue ~40,000 round trips. A bulk form of the same lookup -
`get_deleted_rows_business_keys_bulk`, same semantics, 1000-row chunked IN queries -
already sat 700 lines up in the same file, written for `batch_delete`.

What is pinned here, and why each one is a way the fix could be green and wrong:

  * The statement count does not grow with the number of logs. A functional test
    passes either way; only counting statements notices a re-introduced N+1.
  * BOTH branches are covered. The cache branch is checked FIRST and is the common
    path, so fixing only the DB branch would leave the live route unchanged. (Two
    doors, and closing one changes nothing - server-pm memory.)
  * The keys are still CORRECT, compared against the per-row function the bulk form
    replaces. A fix that stopped resolving keys entirely would be the fastest of all.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

import main as main_mod
from audit_cache import audit_cache
from database import models

TABLE = "raw_table_1"
OTHER = "inventory_master"


@pytest.fixture(autouse=True)
def _cold_audit_cache():
    """Each test decides for itself whether the route takes the cache branch."""
    audit_cache.groups = []
    audit_cache.is_loaded = False
    yield
    audit_cache.groups = []
    audit_cache.is_loaded = False


def _seed_deleted_rows(db, tx_id, n, table=TABLE, key_col="EQP_ID"):
    """`n` DELETE logs for rows that do NOT exist -> every one needs a key lookup.

    The key is deliberately reachable only through the FALLBACK path (an edit log on
    the key column), because that is the arm that costs the second query per row.
    """
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    row_ids = []
    for i in range(n):
        r_id = f"{table}-gone-{i}-{uuid.uuid4().hex[:6]}"
        row_ids.append(r_id)
        db.add(models.AuditLog(
            table_name=table, row_id=r_id, column_name=key_col,
            old_value=None, new_value=f"BK-{table}-{i}",
            source_name="user", updated_by="tester",
            transaction_id=f"old-{r_id}", timestamp=base - timedelta(days=1)))
        db.add(models.AuditLog(
            table_name=table, row_id=r_id, column_name="DELETE",
            old_value=None, new_value=None,
            source_name="user", updated_by="tester",
            transaction_id=tx_id, timestamp=base + timedelta(seconds=i)))
    db.commit()
    return row_ids


def _count_selects(db_session, fn):
    bind = db_session.get_bind()
    seen = []

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(bind, "before_cursor_execute", _before)
    try:
        out = fn()
    finally:
        event.remove(bind, "before_cursor_execute", _before)
    return out, seen


@pytest.mark.parametrize("warm_cache", [False, True], ids=["db-branch", "cache-branch"])
def test_the_statement_count_does_not_grow_with_the_number_of_logs(
        client, db_session, warm_cache):
    """The defect, measured rather than argued.

    Two transactions of very different sizes; the difference in SELECTs between them
    must stay flat. Under the per-log form it grew by ~2 per extra log.
    """
    counts = {}
    for n, tx in ((3, "tx-small"), (30, "tx-large")):
        _seed_deleted_rows(db_session, tx, n)
        if warm_cache:
            client.get("/audit_logs/recent")
            # 🔴 `is_loaded` is NOT enough. The route only takes the cache branch if
            # THIS transaction is among the cached groups; otherwise it falls through
            # to the DB branch and this parametrization would silently be a duplicate
            # of the other one - a green test covering one door twice.
            assert audit_cache.is_loaded, "cache branch requested but the cache is cold"
            assert any(g.get("transaction_id") == tx for g in audit_cache.groups), \
                f"{tx} is not in the cache; this case is not exercising the cache branch"
        else:
            audit_cache.is_loaded = False

        (r, seen) = _count_selects(
            db_session, lambda: client.get(f"/audit_logs/transaction/{tx}"))
        assert r.status_code == 200, r.text
        assert len(r.json()["logs"]) == n, "fixture did not land in the response"
        counts[n] = len(seen)

    growth = counts[30] - counts[3]
    assert growth <= 4, (
        f"27 extra logs cost {growth} extra SELECTs ({counts[3]} -> {counts[30]}); "
        f"the per-log lookup is back")


def test_the_business_keys_are_still_the_ones_the_per_row_function_finds(
        client, db_session):
    """Speed is worthless if the column goes blank. Compared against the function
    the bulk form replaced, on the same rows."""
    tx = "tx-correct"
    row_ids = _seed_deleted_rows(db_session, tx, 5)

    r = client.get(f"/audit_logs/transaction/{tx}")
    assert r.status_code == 200, r.text
    got = {log["row_id"]: log["business_key"]
           for log in r.json()["logs"] if log["column_name"] == "DELETE"}

    assert set(got) == set(row_ids)
    for r_id in row_ids:
        expected = main_mod.get_deleted_row_business_key(db_session, TABLE, r_id)
        assert expected, "fixture produced no recoverable key; the test proves nothing"
        assert got[r_id] == expected, f"{r_id}: {got[r_id]!r} != {expected!r}"
        assert got[r_id] is not None
    assert all(log["is_row_deleted"] for log in r.json()["logs"]
               if log["column_name"] == "DELETE")


def test_one_transaction_spanning_two_tables_resolves_both(client, db_session):
    """A chain transaction writes to several tables, and the bulk primitive takes ONE
    table per call. Grouping by table is the whole difference between this and the
    per-log form, so a fix that dropped the grouping would blank one table's keys."""
    tx = "tx-two-tables"
    a = _seed_deleted_rows(db_session, tx, 3, table=TABLE, key_col="EQP_ID")
    b = _seed_deleted_rows(db_session, tx, 3, table=OTHER, key_col="part_no")

    r = client.get(f"/audit_logs/transaction/{tx}")
    assert r.status_code == 200, r.text
    got = {log["row_id"]: log["business_key"]
           for log in r.json()["logs"] if log["column_name"] == "DELETE"}

    for r_id in a + b:
        assert got.get(r_id), f"{r_id} lost its business key"
    assert {got[r] for r in a}.isdisjoint({got[r] for r in b}), \
        "the two tables' keys collapsed together"
