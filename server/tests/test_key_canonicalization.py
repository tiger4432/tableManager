"""[7b] Canonical key values by DECLARED column type — unit + integration.

Production defect (2026-07-28): a `number`-declared slot column stores 1, so its
map identity is registered in metadata as 'LOT_1' — while a parsed material
token supplies '01' and a Float column round-trips '1.0'. Composing a map_id or
binding an availability pool with the raw value then misses silently (meta not
found -> alignment silently degrades to identity; pool bind -> 0 rows). Cell
data filters survive because crud casts by declared type; this suite pins the
same discipline for identity composition and pool binds.

THE implementation is `map_overlay.canonical_key_value` (single function — no
second implementation). Each integration test here has a MUTATION twin that
swaps the canonicalization for a raw str() identity and asserts the aggregate
COLLAPSES — proving the fixture actually activates the defect axis (a test
that also passes on the broken version proves nothing).

[Engine note] SQLite numeric affinity absorbs '01'/' 1 ' when the column is
Float, so number-column BIND mutations are invisible under SQLite. The two
engine-independent axes used here are:
  * map identity composition (pure string equality on metadata.map_id), and
  * whitespace-padded tokens against string-declared pool columns.

[Isolation] table names use the canon_test_* prefix (cannot exist in a real
user config — conftest initializes dynamic models from the real config at
import time, so a colliding name would preempt the schema).
"""
import json
import uuid

import pytest

import bonding_plan
import map_overlay
import transfer_plan
from database import crud, models

# ---------------------------------------------------------------------------
# Unit — the canonicalization function itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value,col_type,expected", [
    # number: the single-integer-judge semantics — '01' / '1' / ' 1 ' are one key
    ("01", "number", "1"),
    (" 1 ", "number", "1"),
    ("1", "number", "1"),
    ("+07", "number", "7"),
    (1, "number", "1"),
    (1.0, "number", "1"),          # Float column round-trip
    ("1.0", "number", "1"),        # stringified Float round-trip
    ("7.5", "number", "7.5"),      # non-integral numeric: value preserved
    ("0x10", "number", "0x10"),    # unreadable: trimmed original — no invention
    ("", "number", ""),
    (True, "number", "True"),      # bool is not a number — preserved, not int-cast
    # string: padding is SIGNIFICANT — only whitespace is trimmed
    ("01", "string", "01"),
    (" A ", "string", "A"),
    # undeclared type: string semantics (trim only)
    ("01", None, "01"),
    (" B ", None, "B"),
    # a float VALUE is numeric whatever the declared type — repr artifact folded
    # (mirrors crud.clean_str_value; the registration path pinned this shape)
    (3.0, None, "3"),
    (3.0, "string", "3"),
    (3.5, "string", "3.5"),
    (None, "number", None),
    (None, "string", None),
])
def test_canonical_key_value_matrix(value, col_type, expected):
    assert map_overlay.canonical_key_value(value, col_type) == expected


def test_nan_and_inf_are_preserved_not_invented():
    out = map_overlay.canonical_key_value(float("nan"), "number")
    assert out == "nan"
    assert map_overlay.canonical_key_value(float("inf"), "number") == "inf"


# ---------------------------------------------------------------------------
# Fixture — number-declared slot columns (the production shape)
# ---------------------------------------------------------------------------

CANON_TABLES = {
    # whitespace pool-bind axis: STRING-declared slot storing canonical '1'
    "canon_test_pool": {
        "business_key": "k",
        "column_types": {"k": "string", "lot": "string", "slot": "string",
                         "x": "number", "y": "number"},
    },
    "canon_test_dt_log": {
        "business_key": "dt_id",
        "column_types": {"dt_id": "string", "tape_lot": "string",
                         "tape_slot": "string", "tx": "number", "ty": "number",
                         "core_lot": "string", "core_slot": "number",  # <- Float col
                         "cx": "number", "cy": "number"},
    },
    "canon_test_defect": {   # canonical-frame fail source — slot number-declared
        "business_key": "k",
        "column_types": {"k": "string", "lot": "string", "slot": "number",
                         "x": "number", "y": "number", "val": "string"},
    },
    "canon_test_eds": {      # rotated (180) fail source — slot number-declared
        "business_key": "k",
        "column_types": {"k": "string", "lot": "string", "slot": "number",
                         "x": "number", "y": "number", "val": "string"},
    },
    "canon_test_meta": {
        "business_key": "map_pk",
        "column_types": {"map_pk": "string", "target_table": "string",
                         "map_id": "string", "grid_metadata": "string"},
    },
}

GRID = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
        "grid_y_invert": False, "side": "front",
        "phys_wafer_dia": 300, "phys_chip_x": 7, "phys_chip_y": 7,
        "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}


def _canon_cfg():
    meta_binding = {
        "table": "canon_test_meta",
        "columns": {"target_table": "target_table", "map_id": "map_id",
                    "grid_metadata": "grid_metadata"},
    }
    return {
        "stages": {
            "canon": {
                "source_kind": "tape", "target_kind": "base",
                "source": {
                    "identity": {"compose": ["lot", "slot"]},
                    "map_metadata": meta_binding,
                    "total_chips": {
                        "table": "canon_test_dt_log",
                        "columns": {"lot": "tape_lot", "slot": "tape_slot",
                                    "x": "tx", "y": "ty"},
                    },
                    "origin_log": {
                        "table": "canon_test_dt_log",
                        "columns": {"lot": "tape_lot", "slot": "tape_slot",
                                    "x": "tx", "y": "ty",
                                    "origin_lot": "core_lot", "origin_slot": "core_slot",
                                    "origin_x": "cx", "origin_y": "cy"},
                    },
                    "fail_sources": {
                        "defect": {
                            "frame": "origin", "table": "canon_test_defect",
                            "columns": {"lot": "lot", "slot": "slot",
                                        "x": "x", "y": "y", "val": "val"},
                            "fail_values": ["D"],
                        },
                        "eds": {
                            "frame": "origin", "table": "canon_test_eds",
                            "columns": {"lot": "lot", "slot": "slot",
                                        "x": "x", "y": "y", "val": "val"},
                            "fail_values": ["F"],
                        },
                    },
                },
                "target_map": {"table": "canon_test_target"},
            },
            "canon_pool": {
                "source_kind": "core", "target_kind": "tape",
                "source": {
                    "total_chips": {
                        "table": "canon_test_pool",
                        "columns": {"lot": "lot", "slot": "slot", "x": "x", "y": "y"},
                    },
                },
                "target_map": {"table": "canon_test_target2"},
            },
        },
    }


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = CANON_TABLES[table]["business_key"]
    row = model(row_id=str(uuid.uuid4()),
                business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols)
    db.add(row)
    return row


def _add_meta(db, target_table, map_id, rotation=0):
    meta = dict(GRID)
    meta["rotation"] = rotation
    _add(db, "canon_test_meta", map_pk=f"{target_table}_{map_id}",
         target_table=target_table, map_id=map_id, grid_metadata=json.dumps(meta))


@pytest.fixture()
def canon_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(CANON_TABLES)
    crud.TABLE_CONFIG.update(CANON_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    tp_path = tmp_path / f"tp_{uuid.uuid4().hex[:6]}.json"
    tp_path.write_text(json.dumps(_canon_cfg()), encoding="utf-8")
    monkeypatch.setattr(transfer_plan, "CONFIG_PATH", str(tp_path))
    monkeypatch.setattr(bonding_plan, "CONFIG_PATH", str(tmp_path / "no_bp.json"))
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(tmp_path / "no_ovl.json"))
    return db_session


def _seed_composition_scenario(db):
    """Tape TAPEC/01 with 2 chips from core (CLOT, slot=1 — a Float column, so
    the ORM hands back 1.0). Metas are registered under the CANONICAL identity
    'CLOT_1' (exactly what a number-declared registration produces).

    Defect (rotation 0) fails canonical (2,2)  -> tape (2,1).
    EDS    (rotation 180) stores (6,6) = canonical (1,1) -> tape (1,1).

    Defect survives an identity-transform mutation (stored == canonical), EDS
    does NOT: without the meta the 180 flip is lost and (6,6) matches no origin
    chip — that asymmetry is the observable defect axis.
    """
    chips = [(1, 1, 1, 1), (2, 2, 2, 1)]   # (cx, cy, tx, ty)
    for i, (cx, cy, tx, ty) in enumerate(chips):
        _add(db, "canon_test_dt_log", dt_id=f"C-{i}", tape_lot="TAPEC",
             tape_slot="01", tx=tx, ty=ty, core_lot="CLOT", core_slot=1,
             cx=cx, cy=cy)
    _add(db, "canon_test_defect", k="D1", lot="CLOT", slot=1, x=2, y=2, val="D")
    _add(db, "canon_test_eds", k="E1", lot="CLOT", slot=1, x=6, y=6, val="F")
    _add_meta(db, "canon_test_defect", "CLOT_1", rotation=0)
    _add_meta(db, "canon_test_eds", "CLOT_1", rotation=180)
    db.commit()


def _raw_str_mutant(monkeypatch):
    """The defective version: canonicalization degenerates to raw str()."""
    monkeypatch.setattr(map_overlay, "canonical_key_value",
                        lambda v, t: None if v is None else str(v))


# ---------------------------------------------------------------------------
# Integration — map identity composition (meta lookup axis)
# ---------------------------------------------------------------------------


def test_float_stored_slot_composes_canonical_map_id_and_meta_is_found(canon_env):
    """origin_slot comes off a Float column as 1.0; composition must produce
    'CLOT_1' (not 'CLOT_1.0') so the 180-rotated EDS meta is found and the
    fail projects onto the tape frame."""
    _seed_composition_scenario(canon_env)
    cfg = transfer_plan.load_transfer_plan_config()
    out = transfer_plan.get_stage_source_summary(canon_env, cfg, "canon",
                                                 "TAPEC", "01")
    assert out["chips"]["total"] == 2
    assert out["chips"]["fail_breakdown"] == {"defect": 1, "eds": 1}
    # the 180 alignment actually engaged (not identity-by-accident)
    assert "aligned:180" in out["sources"]["eds"]
    # transfer_log is undeclared here (missing -> remaining nulled by design):
    # the served bound is what carries the arithmetic — both chips are blocked
    assert out["chips"]["remaining_upper_bound"] == 0


def test_mutation_raw_composition_loses_the_rotated_fail(canon_env, monkeypatch):
    """MUTATION TWIN: with raw str() composition the map_id becomes 'CLOT_1.0',
    both metas miss, alignment silently falls to identity and the EDS fail
    vanishes (6,6 matches no origin chip). This failing aggregate proves the
    fixture activates the composition axis the fix guards."""
    _seed_composition_scenario(canon_env)
    _raw_str_mutant(monkeypatch)
    cfg = transfer_plan.load_transfer_plan_config()
    out = transfer_plan.get_stage_source_summary(canon_env, cfg, "canon",
                                                 "TAPEC", "01")
    assert out["chips"]["fail_breakdown"]["eds"] == 0        # lost
    assert "aligned:180" not in out["sources"]["eds"]        # identity-by-accident
    assert out["chips"]["fail_breakdown"]["defect"] == 1     # survives (rot 0)


# ---------------------------------------------------------------------------
# Integration — availability pool bind axis
# ---------------------------------------------------------------------------


def _seed_pool(db):
    for i in range(3):
        _add(db, "canon_test_pool", k=f"P-{i}", lot="PLOT", slot="1", x=i, y=1)
    db.commit()


def test_whitespace_padded_token_finds_the_pool(canon_env):
    """' 1 ' must bind as '1' against a string-declared slot column storing '1'
    (the '같은 정수 판정기' whitespace leg; SQLite cannot mask this axis)."""
    _seed_pool(canon_env)
    cfg = transfer_plan.load_transfer_plan_config()
    out = transfer_plan.get_stage_source_summary(canon_env, cfg, "canon_pool",
                                                 "PLOT", " 1 ")
    assert out["chips"]["total"] == 3
    assert out["sources"]["total_chips"] == "connected"


def test_mutation_raw_bind_misses_the_pool(canon_env, monkeypatch):
    """MUTATION TWIN: raw ' 1 ' against the string column finds nothing —
    proving the bind actually routes through the canonicalization."""
    _seed_pool(canon_env)
    _raw_str_mutant(monkeypatch)
    cfg = transfer_plan.load_transfer_plan_config()
    out = transfer_plan.get_stage_source_summary(canon_env, cfg, "canon_pool",
                                                 "PLOT", " 1 ")
    assert out["chips"]["total"] == 0


# ---------------------------------------------------------------------------
# Unit — the shared lookup/composition helpers
# ---------------------------------------------------------------------------


def test_declared_column_type_reads_the_live_table_config(canon_env):
    assert map_overlay.declared_column_type("canon_test_defect", "slot") == "number"
    assert map_overlay.declared_column_type("canon_test_defect", "lot") == "string"
    assert map_overlay.declared_column_type("canon_test_defect", "nope") is None
    assert map_overlay.declared_column_type("no_such_table", "slot") is None


def test_compose_map_id_canonicalizes_per_binding(canon_env):
    binding = {"table": "canon_test_defect",
               "columns": {"lot": "lot", "slot": "slot"}}
    out = map_overlay.compose_map_id(["lot", "slot"],
                                     {"lot": " CLOT ", "slot": "01"}, binding)
    assert out == "CLOT_1"
    # no binding -> no declared type -> raw str() passthrough (legacy shape)
    assert map_overlay.compose_map_id(["lot", "slot"],
                                      {"lot": "CLOT", "slot": "01"}) == "CLOT_01"


def test_build_key_filters_binds_canonical_literals(canon_env):
    """map_key 'CLOT_01' decomposed against a number-declared slot must bind the
    canonical '1' (engine-independent check on the bound literal itself)."""
    model = models.DYNAMIC_TABLES["canon_test_defect"]
    binding = {"x": "x", "y": "y", "val": "val", "key_columns": ["lot", "slot"]}
    filters = map_overlay.build_key_filters(model, binding, "CLOT_01")
    assert filters is not None and len(filters) == 2
    assert filters[0].right.value == "CLOT"
    assert filters[1].right.value == "1"


def test_registration_composes_the_same_canonical_identity(canon_env):
    """Registration side (map_meta_registrar) routed through the SAME function:
    a raw pre-cast '01' arriving for a number-declared key column must register
    'CLOT_1' — the identity every lookup site composes. If registration and
    lookup ever diverge again, meta written by ingestion becomes unfindable."""
    from map_meta_registrar import compose_map_id as registrar_compose
    assert registrar_compose(["lot", "slot"], {"lot": "CLOT", "slot": "01"},
                             table_name="canon_test_defect") == "CLOT_1"
    # undeclared table: previous clean_str_value pin preserved
    assert registrar_compose(["lot", "slot"], {"lot": "CLOT", "slot": 3.0}) == "CLOT_3"
    assert registrar_compose(["lot", "slot"], {"lot": "CLOT"}) is None
