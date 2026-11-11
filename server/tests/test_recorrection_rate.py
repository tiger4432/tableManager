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

from conftest import retire_dynamic_model
from database import crud, lines, models
from tests.support import line_tables

# Table names are namespaced so they can never collide with a real table in the
# user's (gitignored) table_config.json - a collision there has broken this
# suite before by pre-empting the shared in-memory SQLite schema.
T = "recorr_test_tbl"
OTHER = "recorr_test_other"
COLUMNS = ("a", "b", "z", "filled")
_BITS = {}


@pytest.fixture(autouse=True)
def line_tables_of_both(db_session, monkeypatch):
    """The cell-source overhaul: a person's writes are lines (`crud.human_lines`) - both tables keep them."""
    engine = db_session.get_bind()
    for name in (T, OTHER):
        entry = {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": dict({"k": "string"}, **{c: "string" for c in COLUMNS})}
        models.init_dynamic_models({name: entry})
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
        _BITS[name] = line_tables.build(engine, name)
    yield
    for name in (T, OTHER):
        line_tables.drop(engine, name)
        retire_dynamic_model(name)


def _log(db, *, row, col, tx, source=crud.USER_SOURCE, days_ago=1, new="after", table=T, by="tester", acted_by=None):
    """One line `source` wrote in transaction `tx` - the cell `col` said `new` (None: emptied) - and the write's audit
    row, its actor `acted_by` (the author `by` when not given), as `write_lines` leaves them."""
    at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    line_tables.line(db.connection(), table, _BITS[table], row, source=source, batch=tx, written_by=by, at=at,
                     values={col: new})
    line_tables.audit_batch(db.connection(), tx, table, written_by=acted_by or by, at=at)


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

def test_clearing_a_cell_still_counts_as_a_write(db_session):
    """Guard against over-filtering: value -> empty is a real human edit."""
    _log(db_session, row="r1", col="a", tx="tx-1", new=None)
    _log(db_session, row="r1", col="a", tx="tx-2", new="redone")

    s = _stats(db_session)
    assert s["measured_cells"] == 1
    assert s["recorrected_cells"] == 1


# ── 7. Cell identity ─────────────────────────────────────────────────────────

def test_same_column_on_different_rows_and_tables_are_different_cells(db_session):
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r2", col="a", tx="tx-2")
    _log(db_session, row="r1", col="a", tx="tx-3", table=OTHER)

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
    #: 🪦 `total_tables` 는 «측정하고» 제거됐다(`471f66f7`, 2026-09-05) — 읽는 쪽 0(소스·번들)에
    #:    이 라우트 벽의 67%. 이 단언이 재던 것은 «그 수»가 아니라 「나머지가 여전히 그려진다」이므로
    #:    살아 있는 그 라우트의 «자기» 통계로 옮긴다. 「있음」이 아니라 «값»이다.
    assert body["system_health"], "the rest of the dashboard still renders"
    assert body["system_health"], "the dashboard's own verdict went dark with the failing part"
    assert body["recorrection"]["rate_pct"] is None
    assert body["recorrection"]["unavailable_reason"]
    main.RECORRECTION_CACHE["value"] = None


def test_the_unavailable_reason_names_the_actual_cause_not_a_canned_timeout(
        client, db_session, monkeypatch):
    """TWIN of the effort instrument's F6 fix (test_effort_metric.py).

    This helper used to return one canned string -- "집계 시간 초과 또는 실패
    (idx_audit_user_recorrection 인덱스 확인)" -- for EVERY failure mode. A missing
    column or a broken query therefore read as "the index is slow", sending whoever
    was on call to tune an index that was never the problem.
    """
    import main

    def boom(*a, **kw):
        raise RuntimeError("column audit_logs.source_name does not exist")

    monkeypatch.setattr(crud, "get_recorrection_stats", boom)
    main.RECORRECTION_CACHE["value"] = None

    reason = client.get("/dashboard/summary").json()["recorrection"]["unavailable_reason"]
    assert "source_name does not exist" in reason, "name the real failure"
    assert "RuntimeError" in reason
    assert "시간 초과" not in reason, "must not claim a timeout that did not happen"
    main.RECORRECTION_CACHE["value"] = None


def test_a_real_recorrection_timeout_is_still_identified_as_one(
        client, db_session, monkeypatch):
    import main

    def boom(*a, **kw):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(crud, "get_recorrection_stats", boom)
    main.RECORRECTION_CACHE["value"] = None

    reason = client.get("/dashboard/summary").json()["recorrection"]["unavailable_reason"]
    assert "시간 초과" in reason and lines.index_name("<table>", "p") in reason, \
        "the timeout case must still point at the index that fixes it"
    main.RECORRECTION_CACHE["value"] = None


# ── 9. Whose line (lead 11-10 ㄴ) ─────────────────────────────────────────────

def test_a_merge_copy_of_a_persons_line_is_a_persons(db_session):
    """`crud.layer_writer` is the one judgment: a collision merge keeps a person's line as «user (…)»."""
    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="tx-2", source="user (old_exist_K9)")
    s = _stats(db_session)
    assert (s["measured_cells"], s["recorrected_cells"]) == (1, 1)


@pytest.mark.parametrize("name", ["user", "user (old_exist_K9)", "users.csv", "user(", "xuser", "chain:r1", ""])
def test_the_sql_says_of_each_name_what_layer_writer_says(db_session, name):
    import sqlalchemy as sa

    one = sa.select(sa.literal(name).label("source_name")).subquery()
    picked = db_session.execute(sa.select(sa.func.count()).select_from(one).where(crud.human_source_clause())).scalar()
    assert bool(picked) == (crud.layer_writer(name) == crud.USER_SOURCE), name


# ── 10. Who acted (lead 11-11: a line's written_by is its value's author, its audit row the write's actor) ────────

def test_a_line_a_retroactive_op_re_spelled_is_no_new_act(db_session):
    """The notation backfill re-spells a person's line: the person stays its author, the op is the write's actor -
    one act of the person's, no re-correction."""
    from chain.replay import NOTATION_BACKFILL_SOURCE

    _log(db_session, row="r1", col="a", tx="tx-1")
    _log(db_session, row="r1", col="a", tx="nb-1", acted_by=NOTATION_BACKFILL_SOURCE)
    s = _stats(db_session)
    assert (s["measured_cells"], s["recorrected_cells"]) == (1, 0)


def test_another_person_correcting_a_persons_value_is_a_re_correction(db_session):
    """Person B fixes the cell person A wrote: the new line's author is its actor, B - counted."""
    _log(db_session, row="r1", col="a", tx="tx-1", by="kim")
    _log(db_session, row="r1", col="a", tx="tx-2", by="lee")
    s = _stats(db_session)
    assert (s["measured_cells"], s["recorrected_cells"]) == (1, 1)


def test_write_lines_names_the_actor_on_the_audit_row_and_the_author_on_the_line(db_session):
    """`acted_by` reaches the audit row; the line keeps `written_by` - through the write seat, not a hand-made seed."""
    import sqlalchemy as sa

    from chain.replay import NOTATION_BACKFILL_SOURCE
    from database import lines
    from database.write_lines import write_lines

    db = db_session
    write_lines(db, T, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": crud.USER_SOURCE,
                         "written_by": "kim"}], kind="funnel", transaction_id="tx-a")
    [row_id] = [r for (r,) in db.execute(sa.text('SELECT row_id FROM "%s"' % T))]
    write_lines(db, T, [{"row_id": row_id, "values": {"a": "X"}, "source_name": crud.USER_SOURCE, "written_by": "kim",
                         "acted_by": NOTATION_BACKFILL_SOURCE}], kind="notation", transaction_id="nb-a")
    db.commit()
    ab = lines.AuditBatch
    assert dict(db.execute(sa.select(ab.transaction_id, ab.written_by).where(ab.table_name == T)).all()) == {
        "tx-a": "kim", "nb-a": NOTATION_BACKFILL_SOURCE}
    said = db.execute(sa.text('SELECT batch, written_by FROM "%s" ORDER BY line_id' % lines.lines_relation(T))).all()
    assert [tuple(r) for r in said] == [("tx-a", "kim"), ("nb-a", "kim")], "the line keeps its value's author"
    s = crud.get_recorrection_stats(db)
    assert (s["measured_cells"], s["recorrected_cells"]) == (2, 0)
