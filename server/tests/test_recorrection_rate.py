"""Re-correction rate — the instrument for SYSTEM_OVERVIEW §1 core value #1
("minimum-effort correction").

The metric: of the distinct cells a HUMAN wrote in the window, what share did a
human write MORE THAN ONCE. A cell is (table_name, row_id, column_name).

Every test here pins one of the decisions that silently produce a wrong number.
If you change `crud.get_recorrection_stats`, these are the invariants that say
whether the number still means what the dashboard claims it means.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from database import crud, models

# Table names are namespaced so they can never collide with a real table in the
# user's (gitignored) table_config.json - a collision there has broken this
# suite before by pre-empting the shared in-memory SQLite schema.
T = "recorr_test_tbl"


def _log(db, *, row, col, tx, source=crud.USER_SOURCE, days_ago=1,
         old="before", new="after", table=T):
    db.add(models.AuditLog(
        table_name=table, row_id=row, column_name=col,
        old_value=old, new_value=new,
        source_name=source, updated_by="tester", transaction_id=tx,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))


def _stats(db, window_days=7):
    db.commit()
    return crud.get_recorrection_stats(db, window_days=window_days)


# ── 1. USER-only counting ────────────────────────────────────────────────────

def test_counts_only_cells_a_human_wrote(db_session):
    """Denominator = distinct cells written by source 'user'. Nothing else."""
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="b", tx="tx-1")
    _log(db_session, row="r2", col="a", tx="tx-2")

    s = _stats(db_session)
    assert s["measured_cells"] == 3          # (r1,a) (r1,b) (r2,a)
    assert s["recorrected_cells"] == 0       # each touched by exactly one tx
    assert s["rate_pct"] == 0.0


def test_same_cell_in_two_transactions_is_a_re_correction(db_session):
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2")   # came back to it later
    _log(db_session, row="r1", col="b", tx="tx-1")

    s = _stats(db_session)
    assert s["measured_cells"] == 2
    assert s["recorrected_cells"] == 1
    assert s["rate_pct"] == 50.0


# ── 2. Automatic sources excluded (TRAP 1) ───────────────────────────────────

@pytest.mark.parametrize("auto_source", [
    "pipeline_parser",
    "collision_merge",
    "chain_ingestion",
    "custom_script",
    "system",
    # File parsers write under the INGESTED FILENAME as their source name, so the
    # set of automatic source values is open-ended (10,750 distinct values on the
    # live DB). This is why the filter must be a positive match on 'user' and can
    # never be a blacklist of known automatic sources.
    "inventory_master.csv",
    "web_bonding_data_20260717_181403.csv",
])
def test_automatic_sources_never_enter_the_metric(db_session, auto_source):
    """A parser rewriting the same cell 50x is normal operation, not re-correction.

    Counting it would make the metric drift with ingestion volume instead of with
    human effort - the exact failure this instrument exists to avoid.
    """
    for i in range(50):
        _log(db_session, row="r1", col="a", tx=f"auto-{i}", source=auto_source)

    s = _stats(db_session)
    assert s["measured_cells"] == 0, f"{auto_source} leaked into the denominator"
    assert s["recorrected_cells"] == 0
    assert s["rate_pct"] is None

    # ...and it must not contaminate a real human measurement running alongside it.
    _log(db_session, row="r9", col="z", tx="human-1")
    s2 = _stats(db_session)
    assert s2["measured_cells"] == 1
    assert s2["recorrected_cells"] == 0


def test_heavy_automatic_traffic_does_not_move_the_rate(db_session):
    """The rate must be identical with and without a flood of automatic writes."""
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2")
    _log(db_session, row="r2", col="a", tx="tx-3")
    before = _stats(db_session)

    for i in range(200):
        _log(db_session, row="r1", col="a", tx=f"parser-{i}", source="some_file.csv")
    after = _stats(db_session)

    assert before == after


# ── 3. Same-transaction collapse (TRAP 2) ────────────────────────────────────

def test_one_transaction_is_one_human_action(db_session):
    """An Excel paste can touch the same cell twice inside a single commit.

    That is one human act, not two. Counting audit ROWS instead of distinct
    transactions inflates the live 44-day number from 2.96% to 3.88%.
    """
    # Same cell, same transaction, three audit rows.
    _log(db_session, row="r1", col="a", tx="tx-paste")
    _log(db_session, row="r1", col="a", tx="tx-paste")
    _log(db_session, row="r1", col="a", tx="tx-paste")

    s = _stats(db_session)
    assert s["measured_cells"] == 1
    assert s["recorrected_cells"] == 0, "same-transaction duplicates must collapse"
    assert s["rate_pct"] == 0.0


def test_collapse_does_not_hide_a_genuine_second_visit(db_session):
    """Guard against over-collapsing: different tx on the same cell still counts."""
    _log(db_session, row="r1", col="a", tx="tx-paste")
    _log(db_session, row="r1", col="a", tx="tx-paste")   # collapses
    _log(db_session, row="r1", col="a", tx="tx-later")   # genuine re-correction

    s = _stats(db_session)
    assert s["measured_cells"] == 1
    assert s["recorrected_cells"] == 1
    assert s["rate_pct"] == 100.0


# ── 4. Empty window ──────────────────────────────────────────────────────────

def test_empty_window_reports_no_rate_rather_than_zero_percent(db_session):
    """No sample must not render as a healthy 0%."""
    s = _stats(db_session)
    assert s["measured_cells"] == 0
    assert s["recorrected_cells"] == 0
    assert s["rate_pct"] is None


def test_writes_outside_the_window_are_excluded(db_session):
    _log(db_session, row="r1", col="a", tx="tx-1", days_ago=30)
    _log(db_session, row="r1", col="a", tx="tx-2", days_ago=30)

    assert _stats(db_session, window_days=7)["measured_cells"] == 0
    wide = _stats(db_session, window_days=60)
    assert wide["measured_cells"] == 1
    assert wide["recorrected_cells"] == 1


# ── 5. Small denominator must be visible ─────────────────────────────────────

def test_small_sample_exposes_its_denominator(db_session):
    """'33.33%' over 3 cells and over 30,000 cells must be distinguishable.

    A rate with no denominator is the kind of confident-looking number that gets
    read as a trend when it is noise.
    """
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2")     # re-corrected
    _log(db_session, row="r2", col="a", tx="tx-3")
    _log(db_session, row="r3", col="a", tx="tx-4")

    s = _stats(db_session)
    assert s["rate_pct"] == 33.33
    assert s["measured_cells"] == 3, "denominator must always be reported"
    assert s["recorrected_cells"] == 1


def test_single_cell_denominator_is_reported(db_session):
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2")
    s = _stats(db_session)
    assert (s["measured_cells"], s["recorrected_cells"], s["rate_pct"]) == (1, 1, 100.0)


# ── 6. Identical / empty rewrites (TRAP 3) ───────────────────────────────────

def test_row_creation_placeholders_are_not_counted_as_written_cells(db_session):
    """Creating a row logs EVERY declared column, including ones left blank.

    `apply_row_update_internal` short-circuits its has_changed guard when is_new
    is true (crud.py), so a new row emits null->null audit rows for columns the
    person never filled in. Those are blank cells, not writes: 4,290 such rows
    exist on the live DB and they would pad the denominator with cells nobody
    touched.
    """
    _log(db_session, row="r1", col="filled", tx="tx-create", old=None, new="typed")
    _log(db_session, row="r1", col="blank_a", tx="tx-create", old=None, new=None)
    _log(db_session, row="r1", col="blank_b", tx="tx-create", old=None, new=None)

    s = _stats(db_session)
    assert s["measured_cells"] == 1, "only the cell the person actually filled counts"
    assert s["recorrected_cells"] == 0


def test_clearing_a_cell_still_counts_as_a_write(db_session):
    """Guard against over-filtering: value -> empty is a real human edit."""
    _log(db_session, row="r1", col="a", tx="tx-1", old="something", new=None)
    _log(db_session, row="r1", col="a", tx="tx-2", old=None, new="redone")

    s = _stats(db_session)
    assert s["measured_cells"] == 1
    assert s["recorrected_cells"] == 1


# ── 7. Cell identity ─────────────────────────────────────────────────────────

def test_same_column_on_different_rows_and_tables_are_different_cells(db_session):
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r2", col="a", tx="tx-2")
    _log(db_session, row="r1", col="a", tx="tx-3", table="recorr_test_other")

    s = _stats(db_session)
    assert s["measured_cells"] == 3
    assert s["recorrected_cells"] == 0


# ── 8. Endpoint contract ─────────────────────────────────────────────────────

def test_dashboard_summary_carries_rate_and_denominator(client, db_session):
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2")
    _log(db_session, row="r2", col="a", tx="tx-3")
    db_session.commit()

    import main
    main.RECORRECTION_CACHE["value"] = None   # TTL cache must not serve a stale run

    res = client.get("/dashboard/summary")
    assert res.status_code == 200
    body = res.json()["recorrection"]
    assert body["window_days"] == crud.RECORRECTION_WINDOW_DAYS
    assert body["measured_cells"] == 2
    assert body["recorrected_cells"] == 1
    assert body["rate_pct"] == 50.0
    assert body["unavailable_reason"] is None


def test_dashboard_survives_a_failing_recorrection_query(client, db_session, monkeypatch):
    """The dashboard must degrade to '-' in that one cell, never to a 500.

    Without the index this aggregate falls back to a sequential scan; the endpoint
    is required to give up rather than make the whole page wait on it.
    """
    import main

    def boom(*a, **kw):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(crud, "get_recorrection_stats", boom)
    main.RECORRECTION_CACHE["value"] = None

    res = client.get("/dashboard/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["total_tables"] >= 1, "the rest of the dashboard still renders"
    assert body["recorrection"]["rate_pct"] is None
    assert body["recorrection"]["unavailable_reason"]
    main.RECORRECTION_CACHE["value"] = None
