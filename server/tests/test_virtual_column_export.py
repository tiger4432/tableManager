"""CSV EXTRACT ― what is on screen is what comes out of the file.

[The defect this closes]
`export_table_csv` never touched the join. For a `virtual_only` column the extract simply
had no such column; for a `collide` column - which is what the PRODUCTION declaration is -
the extract carried the RAW STORED value where the grid showed the resolved one. That
second shape is the dangerous one: the column is present, the file opens, and the cells
are just quietly empty where the screen said `미상`. An append-only fix would have looked
complete and done nothing for production.

[The constraint that shaped the implementation]
The join is in the SAME SQL statement, never a per-chunk attach. The stream runs on ONE
server-side cursor (`stream_results=True`, `yield_per(5000)`) inside a `StreamingResponse`:
by the time rows are produced, 200 OK and the headers are already on the wire, so a
mid-stream failure hands the user a truncated CSV that looks complete.
`test_the_export_issues_no_query_per_chunk` is what stops that being re-introduced.

[격리] 테이블명 접두 `vjex_test_` ― 사용자 gitignored config에 실존할 수 없다.
[승인 대역] sqlite에서 `unique_index_covering`은 항상 None이므로(모르면 거부) 대역 없이는
조인이 0건이고 모든 테스트가 헛통과한다 ― `test_virtual_join_executor.py`와 같은 이유.
"""
import csv
import io
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

EXPORT_TABLES = {
    "vjex_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            "wafer_id": "string",          # collide
        },
    },
    "vjex_test_wafer": {
        "business_key": "wafer_key",
        "column_types": {
            "wafer_key": "string", "core_lot": "string", "core_slot": "string",
            "wafer_id": "string",
            "fab_site": "string",          # virtual_only
        },
    },
}

DECL = {
    "vjex_rule": {
        "left_table": "vjex_test_log", "right_table": "vjex_test_wafer",
        "join_key": [{"left": "core_lot", "right": "core_lot"},
                     {"left": "core_slot", "right": "core_slot"}],
        "expose": ["wafer_id", "fab_site"],
    }
}


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


@pytest.fixture()
def export_env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(EXPORT_TABLES)
    crud.TABLE_CONFIG.update(EXPORT_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "vjex_test_wafer" else None)
    vjx.reset_cache()
    import main
    main.TABLE_COUNT_CACHE.clear()

    _seed(db_session, "vjex_test_wafer", [
        {"wafer_key": "K1", "core_lot": "LOT-A", "core_slot": "01",
         "wafer_id": "WF-1", "fab_site": "M1"},
        {"wafer_key": "K2", "core_lot": "LOT-A", "core_slot": "02",
         "wafer_id": "WF-2", "fab_site": "M2"},
        # right row exists, carries nothing -> case (2) of 미상
        {"wafer_key": "K3", "core_lot": "LOT-A", "core_slot": "03"},
    ])
    _seed(db_session, "vjex_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"},
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "02"},
        {"log_id": "L3", "core_lot": "LOT-A", "core_slot": "03"},   # matched-but-empty
        {"log_id": "L4", "core_lot": "LOT-Z", "core_slot": "99"},   # no right row
        {"log_id": "L5", "core_lot": "LOT-Z", "core_slot": "98", "wafer_id": "WF-LEFT"},
    ])
    db_session.commit()
    yield client
    vjx.reset_cache()
    main.TABLE_COUNT_CACHE.clear()


def _extract(client, table="vjex_test_log", **params):
    """Returns (header, {log_id: {col: value}}, response)."""
    r = client.get(f"/tables/{table}/export", params=params)
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:]
    by_id = {}
    for row in body:
        if not row:
            continue
        rec = dict(zip(header, row))
        by_id[rec["log_id"]] = rec
    return header, by_id, r


def _grid(client, table="vjex_test_log", **params):
    """The same rows as `/tables/{t}/data` sees them ― the comparison oracle."""
    r = client.get(f"/tables/{table}/data", params={"limit": 500, **params})
    assert r.status_code == 200, r.text
    return {d["data"]["log_id"]["value"]:
            {k: v.get("value") for k, v in d["data"].items()}
            for d in r.json()["data"]}


# ---------------------------------------------------------------------------
# The header
# ---------------------------------------------------------------------------

def test_the_header_carries_the_virtual_only_column(export_env):
    header, _, _ = _extract(export_env)
    assert "fab_site" in header, (
        "a virtual_only column the grid displays is missing from the extract entirely")
    # System pair stays last ― the row writer indexes them positionally (`row[-2:]`).
    assert header[-2:] == ["created_at", "updated_at"]
    # ...and the virtual column sits after the stored business columns, before that pair.
    assert header.index("fab_site") > header.index("wafer_id")
    assert header.index("fab_site") < header.index("created_at")


def test_a_collide_column_is_not_announced_twice(export_env):
    """`wafer_id` is a STORED column that the join also fills. One header slot, not two."""
    header, _, _ = _extract(export_env)
    assert header.count("wafer_id") == 1
    assert len(header) == len(set(header)), f"duplicate header cells: {header}"


# ---------------------------------------------------------------------------
# The values ― the extract must equal the grid
# ---------------------------------------------------------------------------

def test_the_collide_column_carries_the_RESOLVED_value(export_env):
    """🔴 **RED before this round, and the only shape production actually has.**

    Before: the extract selected `bonding_log.wafer_id` raw, so a row whose displayed
    `wafer_id` came from the join exported as an EMPTY CELL, and a row the grid showed as
    `미상` exported as blank too. The column was there; it was just quietly wrong.

    Defect-injection check (actually run): select `getattr(table_model, col)` instead of
    the resolved expression for collide columns and L1/L2 export '' instead of WF-1/WF-2.
    """
    _, rows, _ = _extract(export_env)
    assert rows["L1"]["wafer_id"] == "WF-1"      # from the join
    assert rows["L2"]["wafer_id"] == "WF-2"      # from the join
    assert rows["L5"]["wafer_id"] == "WF-LEFT"   # left value wins (absent-only)


def test_an_unresolved_row_carries_the_label_not_an_empty_cell(export_env):
    """An empty cell where the screen said 미상 is the same lie in a different medium.

    Covers BOTH faces: L3 (right row exists, value empty) and L4 (no right row).
    """
    _, rows, _ = _extract(export_env)
    assert rows["L3"]["fab_site"] == "미상"
    assert rows["L4"]["fab_site"] == "미상"
    assert rows["L3"]["wafer_id"] == "미상"
    assert rows["L4"]["wafer_id"] == "미상"


def test_every_virtual_cell_matches_what_the_grid_returns(export_env):
    """🔴 The oracle test the round asked for: diff the extract against `/tables/{t}/data`.

    Not a header check ― a value-by-value comparison over every row, for every column the
    join contributes. If these two ever disagree, one of the two readers is lying and the
    operator has no way to know which.
    """
    _, rows, _ = _extract(export_env)
    grid = _grid(export_env)
    assert set(rows) == set(grid), "the extract and the grid returned different rows"
    compared = 0
    for log_id, grid_row in grid.items():
        for col in ("wafer_id", "fab_site"):
            assert rows[log_id][col] == grid_row[col], (
                f"{log_id}.{col}: extract={rows[log_id][col]!r} "
                f"grid={grid_row[col]!r}")
            compared += 1
    assert compared == 10, f"expected 5 rows x 2 columns, compared {compared}"


# ---------------------------------------------------------------------------
# `?cols=` / `?filters=` ― the same defect, the same fix, now the same code
# ---------------------------------------------------------------------------

def test_cols_naming_an_unsearchable_column_is_refused_in_the_export_too(export_env):
    """🔴 **RED before this round.** It streamed the WHOLE TABLE with 200.

    This is the defect that was fixed in the grid route and left live here, because the
    two routes held verbatim copies of the search block. They now call one function.
    """
    r = export_env.get("/tables/vjex_test_log/export",
                       params={"q": "anything", "cols": "no_such_column"})
    assert r.status_code == 400, (
        f"expected a refusal, got {r.status_code} with "
        f"{len(r.content.decode('utf-8-sig').splitlines())} lines")


def test_the_export_filters_on_the_virtual_column(export_env):
    _, rows, _ = _extract(export_env, filters=json.dumps(
        {"fab_site": {"type": "equals", "filter": "미상"}}))
    assert set(rows) == {"L3", "L4", "L5"}


def test_search_scoped_to_a_virtual_column_narrows_the_export(export_env):
    _, rows, _ = _extract(export_env, q="M1", cols="fab_site")
    assert set(rows) == {"L1"}


def test_the_export_and_the_grid_agree_under_the_same_filter(export_env):
    """The two routes must answer the same question the same way ― now by construction."""
    f = json.dumps({"wafer_id": {"type": "equals", "filter": "미상"}})
    _, rows, _ = _extract(export_env, filters=f)
    grid = _grid(export_env, filters=f)
    assert set(rows) == set(grid) == {"L3", "L4"}


# ---------------------------------------------------------------------------
# The properties the streaming design rests on
# ---------------------------------------------------------------------------

def test_the_export_issues_no_query_per_chunk(export_env, db_session):
    """🔴 The constraint, asserted rather than trusted: ONE statement, no per-row queries.

    A per-chunk attach would fail mid-stream AFTER 200 OK and the headers, handing the
    user a truncated CSV that looks complete. Counting executed statements is the only
    way to notice that someone re-introduced it - a functional test would still pass.
    """
    from sqlalchemy import event
    bind = db_session.get_bind()
    seen = []

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(bind, "before_cursor_execute", _before)
    try:
        _extract(export_env)
    finally:
        event.remove(bind, "before_cursor_execute", _before)

    # Measured: 3 (the 10-row sample, the count, the stream).
    assert len(seen) <= 4, (
        f"the export issued {len(seen)} SELECTs; a per-chunk attach was re-introduced:\n"
        + "\n".join(s[:120] for s in seen))
    # 🔴 Not vacuous: if `seen` were empty (listener wired wrong) `len(seen) <= 4` would
    # pass and prove nothing. This is what makes the count above mean something.
    joined = [s for s in seen if "LEFT OUTER JOIN" in s.upper()]
    assert joined, "no statement carried the join - the extract cannot be resolving anything"


def test_the_statement_count_does_not_grow_with_the_row_count(export_env, db_session):
    """🔴 The bound is CONSTANT, not `rows / 5000`. Measured at two sizes, not asserted once.

    A single-size count cannot tell a constant apart from a small multiple. This crosses
    the 5,000-row `yield_per` boundary (12,000 rows = 3 chunks), so a per-chunk attach
    would show up as 3 extra statements here and 0 extra in the test above.
    """
    import uuid6
    from sqlalchemy import event
    model = models.DYNAMIC_TABLES["vjex_test_log"]
    # Raw insert: 12k rows through the layering funnel would also write 12k CellSource
    # rows, and this test is about statement COUNT, not about provenance.
    db_session.bulk_save_objects([
        model(row_id=str(uuid6.uuid7()), business_key_val=f"B{i}", log_id=f"B{i}",
              core_lot="LOT-A", core_slot="01") for i in range(12000)])
    db_session.commit()
    import main
    main.TABLE_COUNT_CACHE.clear()

    bind = db_session.get_bind()
    seen = []

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(bind, "before_cursor_execute", _before)
    try:
        _, rows, r = _extract(export_env)
    finally:
        event.remove(bind, "before_cursor_execute", _before)

    assert len(rows) == 12005, f"expected 12005 exported rows, got {len(rows)}"
    assert r.headers["X-Total-Rows"] == "12005"
    assert len(seen) <= 4, (
        f"12,005 rows (3 yield_per chunks) issued {len(seen)} SELECTs - the count grew "
        f"with the data, which is what a per-chunk attach looks like")
    # And the joined values are still right at this size - a constant statement count
    # would also be achieved by not joining at all.
    assert rows["L1"]["wafer_id"] == "WF-1"
    assert rows["B0"]["wafer_id"] == "WF-1"


def test_the_size_estimate_accounts_for_the_virtual_columns(export_env):
    """`X-Estimated-Content-Length` is derived from a 10-row sample of `select_entities`.

    If the sample query were built from a different entity list than the stream, the
    estimate would under-report by exactly the width of the missing columns and the
    client's progress bar would run past 100%. Compare the header against the real body.
    """
    _, _, r = _extract(export_env)
    estimated = int(r.headers["X-Estimated-Content-Length"])
    actual = len(r.content)
    assert r.headers["X-Total-Rows"] == "5"
    # The estimate is an estimate; what must hold is that it is in the right ballpark and
    # NOT short by a whole column's worth. A sample missing `fab_site` + the resolved
    # `wafer_id` would land far below the true size.
    assert 0.7 * actual <= estimated <= 1.5 * actual, (
        f"estimate {estimated} vs actual {actual} - the sample and the stream disagree "
        f"about which columns are being written")


def test_the_join_does_not_multiply_exported_rows(export_env, db_session):
    """One CSV line per left row. The right side's UNIQUE index is what guarantees it."""
    _seed(db_session, "vjex_test_log",
          [{"log_id": f"N{i}", "core_lot": "LOT-A", "core_slot": "01"} for i in range(30)])
    db_session.commit()
    import main
    main.TABLE_COUNT_CACHE.clear()
    _, rows, r = _extract(export_env)
    assert len(rows) == 35
    assert r.headers["X-Total-Rows"] == "35"


def test_a_table_with_no_declaration_exports_exactly_as_before(export_env):
    """The extract of an undeclared table must be byte-identical to the pre-feature one.

    `raw_table_1` comes from conftest and no rule names it, so `exposed_columns` is empty,
    no join is added, and the header carries no extra cell. This is what proves the
    feature costs nothing where it does not apply.
    """
    r = export_env.get("/tables/raw_table_1/export")
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["EQP_ID", "created_at", "updated_at"]
    assert len(rows) - 1 == 10
