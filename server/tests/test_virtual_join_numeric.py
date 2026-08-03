"""NUMERIC EXPOSE COLUMN through the virtual-join read surface (board item N7).

[The defect this closes ― and why nothing was red when it shipped]
`resolved_expression` builds `COALESCE(<parts>, '<unresolved_label>')`. When the exposed
column is numeric (table_config type `number` -> Float), the parts are FLOAT-typed and the
label is TEXT, and two things break at the SQL layer on the production dialect:
  1. `blank_to_null(col)` contains `col = ''` ― PostgreSQL rejects
     `double precision = ''` outright (`blank_sql_condition`'s stated precondition).
  2. `COALESCE(double precision, text)` cannot be matched to one type.
So every read that names the column (filter / `?q=` / export SELECT) died with 500 in
production (user report 2026-08-02). At ship time the measured axis was "0 numeric expose
columns in this environment", so no fixture activated it ― THIS file is that axis.

[Why the red looks different here than in production]
This suite runs on SQLite, which is dynamically typed: the same expression does not
raise, it silently resolves to the RAW FLOAT, and `cast(<float>, String)` renders '3.0'
where the payload path (`_resolve_one` -> `clean_str_value`) renders '3'. Same defect,
different symptom: production crashes, this dialect answers a search for what the grid
shows with zero rows. Both are killed by the same fix (user ruling 2026-08-02): render
numerics to TEXT before the COALESCE, with INT spelling for integral values
(`crud.numeric_text_sql`, the SQL twin of `clean_str_value`'s numeric branch).

[격리] 테이블명 접두 `vjn_test_` ― 사용자 gitignored config에 실존할 수 없다.
[승인 대역] sqlite에서 `unique_index_covering`은 항상 None이므로(모르면 거부) 대역
없이는 조인이 0건이고 모든 테스트가 헛통과한다 ― `test_virtual_column_search.py`와
같은 이유, 같은 대역이다.
"""
import csv
import io
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

LABEL = "미상"

NUM_TABLES = {
    "vjn_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            # collide AND numeric ― exists on the left and is exposed by the join
            "core_thk": "number",
        },
    },
    "vjn_test_wafer": {
        "business_key": "wafer_key",
        "column_types": {
            "wafer_key": "string", "core_lot": "string", "core_slot": "string",
            # virtual_only AND numeric ― the user's reported shape (a slot number)
            "slot_no": "number",
            "core_thk": "number",
        },
    },
}

DECL = {
    "vjn_rule": {
        "left_table": "vjn_test_log", "right_table": "vjn_test_wafer",
        "join_key": [{"left": "core_lot", "right": "core_lot"},
                     {"left": "core_slot", "right": "core_slot"}],
        "expose": ["slot_no", "core_thk"],
    }
}


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


@pytest.fixture()
def num_env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(NUM_TABLES)
    crud.TABLE_CONFIG.update(NUM_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "vjn_test_wafer" else None)
    vjx.reset_cache()
    import main
    main.TABLE_COUNT_CACHE.clear()

    _seed(db_session, "vjn_test_wafer", [
        # integral float ― the value the user's slot column holds. MUST come back as
        # 3, never 3.0 (user ruling 2026-08-02).
        {"wafer_key": "K1", "core_lot": "LOT-A", "core_slot": "01",
         "slot_no": "3", "core_thk": "1.25"},
        # fractional float ― the int-fold must NOT touch it
        {"wafer_key": "K2", "core_lot": "LOT-A", "core_slot": "02",
         "slot_no": "2.5"},
        # right row EXISTS, both numerics NULL ― case (2) of 미상
        {"wafer_key": "K3", "core_lot": "LOT-A", "core_slot": "03"},
    ])
    _seed(db_session, "vjn_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"},   # -> 3 / 1.25
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "02"},   # -> 2.5 / 미상
        {"log_id": "L3", "core_lot": "LOT-A", "core_slot": "03"},   # -> 미상 (case 2)
        {"log_id": "L4", "core_lot": "LOT-Z", "core_slot": "99"},   # -> 미상 (case 1)
        # left carries its OWN numeric core_thk and has no right row: absent-only says
        # the left value wins, and it too must spell 4, not 4.0.
        {"log_id": "L5", "core_lot": "LOT-Z", "core_slot": "98", "core_thk": "4"},
    ])
    db_session.commit()
    yield client
    vjx.reset_cache()
    main.TABLE_COUNT_CACHE.clear()


def _get(client, **params):
    r = client.get("/tables/vjn_test_log/data", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {d["data"]["log_id"]["value"] for d in body["data"]}
    return ids, body["total"]


def _filters(col, ftype, val=None):
    spec = {"type": ftype}
    if val is not None:
        spec["filter"] = val
    return json.dumps({col: spec})


def _payload_cells(client, col):
    r = client.get("/tables/vjn_test_log/data", params={"limit": 500})
    assert r.status_code == 200, r.text
    out = {}
    for d in r.json()["data"]:
        cell = d["data"].get(col)
        out[d["data"]["log_id"]["value"]] = cell["value"] if isinstance(cell, dict) else None
    return out


# ---------------------------------------------------------------------------
# The payload path (attach / _resolve_one) ― already worked, pinned so the fix
# to the SQL path cannot regress it.
# ---------------------------------------------------------------------------

def test_the_payload_carries_the_numeric_values_and_the_label(num_env):
    slots = _payload_cells(num_env, "slot_no")
    assert crud.clean_str_value(slots["L1"]) == "3", "integral slot must render 3, not 3.0"
    assert crud.clean_str_value(slots["L2"]) == "2.5"
    assert slots["L3"] == LABEL and slots["L4"] == LABEL and slots["L5"] == LABEL

    thk = _payload_cells(num_env, "core_thk")
    assert crud.clean_str_value(thk["L1"]) == "1.25"
    assert crud.clean_str_value(thk["L5"]) == "4", "left-owned numeric wins (absent-only)"
    assert thk["L2"] == LABEL and thk["L3"] == LABEL and thk["L4"] == LABEL


# ---------------------------------------------------------------------------
# 🔴 The SQL path ― RED before this round.
# On PostgreSQL the pre-fix expression is a hard 500 (`double precision = ''`,
# `COALESCE(double precision, text)`). On this suite's SQLite it survives and
# instead spells the value '3.0' while the grid says '3' ― so every assertion
# below both reproduces the defect here and pins the production fix.
# ---------------------------------------------------------------------------

def test_filter_equals_int_spelling_finds_the_integral_row(num_env):
    """Searching what the grid DISPLAYS (3) must find the row holding 3.0."""
    ids, total = _get(num_env, filters=_filters("slot_no", "equals", "3"))
    assert ids == {"L1"}
    assert total == 1


def test_filter_never_answers_to_the_float_spelling(num_env):
    """'3.0' is not a value anyone SEES; matching it would be the same seam reopened
    from the other side (grid says 3, search only answers to 3.0)."""
    ids, total = _get(num_env, filters=_filters("slot_no", "equals", "3.0"))
    assert ids == set()
    assert total == 0


def test_filter_fractional_value_is_not_folded(num_env):
    ids, total = _get(num_env, filters=_filters("slot_no", "equals", "2.5"))
    assert ids == {"L2"}
    assert total == 1


def test_unresolved_rows_are_found_on_a_numeric_column(num_env):
    """Both faces of 미상 on a NUMERIC virtual_only column ― the highest-value filter."""
    ids, total = _get(num_env, filters=_filters("slot_no", "equals", LABEL))
    assert ids == {"L3", "L4", "L5"}
    assert total == 3


def test_numeric_collide_respects_absent_only_in_int_spelling(num_env):
    """The LEFT part of the COALESCE is numeric too and must get the same rendering."""
    ids, total = _get(num_env, filters=_filters("core_thk", "equals", "4"))
    assert ids == {"L5"}
    assert total == 1
    ids, total = _get(num_env, filters=_filters("core_thk", "equals", LABEL))
    assert ids == {"L2", "L3", "L4"}
    assert total == 3


def test_a_numeric_filter_value_is_normalized_to_the_int_spelling(num_env):
    """AG-Grid may send the filter value as a NUMBER (3 or 3.0). Against a text-resolved
    expression that must compare as '3' ― not error, not miss."""
    ids, total = _get(num_env, filters=json.dumps({"slot_no": {"type": "equals", "filter": 3}}))
    assert ids == {"L1"} and total == 1
    ids, total = _get(num_env, filters=json.dumps({"slot_no": {"type": "equals", "filter": 3.0}}))
    assert ids == {"L1"} and total == 1


def test_q_search_reaches_the_numeric_virtual_column(num_env):
    ids, total = _get(num_env, q="2.5", cols="slot_no")
    assert ids == {"L2"}
    assert total == 1
    # Unscoped search must see it too (the column is not in column_types).
    ids, total = _get(num_env, q="2.5")
    assert ids == {"L2"}
    assert total == 1


def test_the_two_spellings_agree_cell_by_cell(num_env, db_session):
    """The acceptance criterion itself: SQL `resolved_expression` and the payload path
    must say the same thing about every cell of a numeric column.

    Scored as render agreement ― the payload carries the raw number (like every other
    numeric cell in the system) and the display renders it through the int-fold; the
    SQL side must produce exactly that displayed text.
    """
    m = models.DYNAMIC_TABLES["vjn_test_log"]
    for col in ("slot_no", "core_thk"):
        payload = _payload_cells(num_env, col)
        q = db_session.query(m.row_id)
        q, expr, _label = vjx.resolved_expression(db_session, m, "vjn_test_log", col, q)
        assert expr is not None
        sql_by_log = {r[0]: r[1] for r in q.with_entities(m.log_id, expr).all()}
        for log_id, py_value in payload.items():
            py_text = py_value if py_value == LABEL else crud.clean_str_value(py_value)
            assert sql_by_log[log_id] == py_text, (
                f"{col}/{log_id}: grid displays {py_text!r}, "
                f"search compares {sql_by_log[log_id]!r}")


# ---------------------------------------------------------------------------
# CSV export ― gained virtual columns this week; must not re-break on numeric.
# ---------------------------------------------------------------------------

def test_export_carries_the_numeric_virtual_column_in_int_spelling(num_env):
    r = num_env.get("/tables/vjn_test_log/export")
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    assert "slot_no" in header
    by_id = {rec["log_id"]: rec for rec in (dict(zip(header, row)) for row in body if row)}
    assert by_id["L1"]["slot_no"] == "3", "the CSV must say what the screen says"
    assert by_id["L2"]["slot_no"] == "2.5"
    assert by_id["L3"]["slot_no"] == LABEL and by_id["L4"]["slot_no"] == LABEL
    assert by_id["L1"]["core_thk"] == "1.25"
    assert by_id["L5"]["core_thk"] == "4"
    assert by_id["L2"]["core_thk"] == LABEL


# ---------------------------------------------------------------------------
# /schema stays honest, write refusal stays untouched.
# ---------------------------------------------------------------------------

def test_schema_announces_the_numeric_column_with_its_label(num_env):
    r = num_env.get("/tables/vjn_test_log/schema")
    assert r.status_code == 200
    body = r.json()
    vcols = {c["name"]: c for c in body.get("virtual_columns", [])}
    assert "slot_no" in vcols
    # The type is the RIGHT table's declaration, and the label rides beside it ―
    # that pairing is the documented "a number column may carry the string label".
    assert vcols["slot_no"]["type"] == "number"
    assert vcols["slot_no"]["unresolved_label"] == LABEL
    jrc = {c["name"]: c for c in body.get("join_resolved_columns", [])}
    assert jrc["slot_no"]["kind"] == "virtual_only"
    assert jrc["core_thk"]["kind"] == "collide"


def test_writes_to_the_numeric_virtual_only_column_are_still_refused(num_env):
    r = num_env.put("/tables/vjn_test_log/data/updates",
                    json={"updates": [{"updates": {"log_id": "L1", "slot_no": "7"},
                                       "source_name": "user", "updated_by": "tester"}]})
    assert r.status_code == 400, (
        f"write refusal funnel must be untouched, got {r.status_code}: {r.text}")
    assert "slot_no" in r.text
