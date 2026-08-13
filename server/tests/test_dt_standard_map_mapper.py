"""S3 mapper: the map key is the PHYSICAL unit, and removal is by SOURCE.

What changed and why the old assertions could not survive it. `dt_map`'s map key moved
from the acquisition unit (`dt_job`) to the physical unit `(dt_lot, dt_slot)`, so several
jobs now converge on one map. `replace_map` purges a whole map, and purging the map to
correct one job would delete every sibling job's contribution to it - so this mapper
emits a `retract` envelope instead, and the worker removes only what the job owns and no
longer derives.

TABLE NAMES ARE FIXTURES, NOT THE LIVE ONES. `s3test_*` cannot collide with a user's
config, and the mapper resolves every table name from the rule, so a fixture name proves
exactly as much as the real one. It also makes these tests independent of run order:
`test_dt_map_derivation`'s fixture calls `init_dynamic_models` with only its own tables,
which REPLACES `crud.TABLE_CONFIG` - a test that read `dt_map` out of the live config
passed alone and failed in a suite. The LANDED declaration gets its own test at the
bottom, which skips where the gitignored config is absent.
"""
import json

import pytest

import chain_bindings
from database import crud, models
from mappers import dt_standard_map_mapper


FRAME = {
    "grid_cols": 10, "grid_rows": 8,
    "grid_start_x": 1, "grid_start_y": 1,
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": 300, "phys_chip_x": 1, "phys_chip_y": 1,
    "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3,
    "valid_die_ref": {"table": "valid_die_ref", "map_id": "PRD-A_DT13"},
}

LOT = "CL_2601_005_A5"
SLOT = "05"
JOB = "SYN-META-001"

TRIGGER, SOURCE, TARGET = "s3test_inventory", "s3test_log", "s3test_map"

# The landed shape, expressed as a fixture. `dt_job` is declared on the target but is in
# NEITHER `map_key_columns` NOR `composite_key_source`: it travels as the source.
TABLES = {
    TRIGGER: {
        "business_key": "dt_job",
        "column_types": {"dt_job": "string", "dt_lot": "string", "dt_slot": "string",
                         "dt_frame": "string",
                         "dt_x_base": "string", "dt_x_sign": "number",
                         "dt_x_offset": "number", "dt_y_base": "string",
                         "dt_y_sign": "number", "dt_y_offset": "number"},
    },
    SOURCE: {
        "business_key": "dt_cell_key",
        "composite_key_source": ["dt_job", "dt_x", "dt_y"],
        "composite_key_separator": "_",
        "column_types": {"dt_cell_key": "string", "dt_job": "string",
                         "dt_x": "number", "dt_y": "number", "dt_index": "number",
                         "c_bn": "string"},
        "map_key_columns": ["dt_job"],
    },
    TARGET: {
        "business_key": "cell_key",
        "composite_key_source": ["dt_lot", "dt_slot", "dt_x", "dt_y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "dt_lot": "string", "dt_slot": "string",
                         "dt_job": "string", "dt_x": "number", "dt_y": "number",
                         "dt_index": "number", "c_bn": "string"},
        "map_key_columns": ["dt_lot", "dt_slot"],
    },
}

RULE = {
    "name": "dt_inventory_to_standard_dt_map",
    "trigger_table": TRIGGER,
    "source_table": SOURCE,
    "target_table": TARGET,
    # Can no longer be derived: the target declares TWO map_key_columns and neither of
    # them is the job. The refusal for the undeclared case is its own test below.
    "target_job_column": "dt_job",
}


class _JobColumn:
    def __eq__(self, value):
        return value


class _DtLog:
    dt_job = _JobColumn()


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, job_id):
        assert job_id == JOB
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is _DtLog
        return _Query(self.rows)


class _Row:
    def __init__(self, x, y, index, bin_value):
        self.dt_x, self.dt_y = x, y
        self.dt_index, self.c_bn = index, bin_value


def _payload(lot=LOT, slot=SLOT):
    return {"data": {
        "dt_job": {"value": JOB},
        "dt_frame": {"value": json.dumps(FRAME)},
        "dt_x_base": {"value": "X"}, "dt_x_sign": {"value": 1}, "dt_x_offset": {"value": 0},
        "dt_y_base": {"value": "Y"}, "dt_y_sign": {"value": 1}, "dt_y_offset": {"value": 0},
        "dt_lot": {"value": lot}, "dt_slot": {"value": slot},
    }}


@pytest.fixture()
def wired(monkeypatch):
    for name, cfg in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, cfg)
    monkeypatch.setitem(models.DYNAMIC_TABLES, SOURCE, _DtLog)
    monkeypatch.setattr(dt_standard_map_mapper.map_meta_registrar, "meta_business_key",
                        lambda table, map_id: f"{table}_{map_id}")
    monkeypatch.setattr(dt_standard_map_mapper.map_overlay, "load_map_meta",
                        lambda _db, table, map_id: {
                            "valid_die_ref": {"table": "valid_die_ref", "map_id": "PRD-SOURCE"}
                        } if (table, map_id) == (SOURCE, JOB) else None)


def test_registers_standard_metadata_and_retracts_exactly_one_job(wired):
    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        _Db([_Row(1, 1, 1, "B4"), _Row(2, 3, 2, "B1")]), [_payload()], rule=RULE,
    )

    meta = result["map_metadata_updates"]
    assert len(meta) == 1
    assert meta[0]["updates"]["target_table"] == TARGET
    # 🔴 The meta is registered against the MAP, so its id is the physical unit. It was
    # the job id before the key moved, and a meta registered under the job id is a meta
    # the cells' own identity can never find.
    assert meta[0]["updates"]["map_id"] == f"{LOT}_{SLOT}"
    standard = json.loads(meta[0]["updates"]["grid_metadata"])
    assert standard["grid_start_x"] == standard["grid_start_y"] == 1
    assert standard["rotation"] == 0 and standard["side"] == "front"
    assert standard["valid_die_ref"] == {"table": "valid_die_ref", "map_id": "PRD-SOURCE"}

    batch = result["batches"]
    assert len(batch) == 1
    # Removal is by SOURCE, not by map. Both of these matter: a `replace_map` left on
    # this batch would purge the whole (lot, slot) map, sibling jobs included.
    assert "replace_map" not in batch[0]
    assert "scope" not in batch[0]
    assert batch[0]["retract"] == {"source_column": "dt_job", "source_value": JOB}
    assert [item["updates"] for item in batch[0]["updates"]] == [
        {"dt_lot": LOT, "dt_slot": SLOT, "dt_job": JOB,
         "dt_x": 1, "dt_y": 1, "dt_index": 1, "c_bn": "B4"},
        {"dt_lot": LOT, "dt_slot": SLOT, "dt_job": JOB,
         "dt_x": 2, "dt_y": 3, "dt_index": 2, "c_bn": "B1"},
    ]


def test_the_job_travels_on_every_cell_but_is_not_key_material(wired):
    """Without the job on the cell there is nothing to retract by, and
    `plan_retraction` refuses by name rather than falling back to set difference."""
    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        _Db([_Row(1, 1, 1, "B4")]), [_payload()], rule=RULE)
    cell = result["batches"][0]["updates"][0]["updates"]

    assert cell["dt_job"] == JOB
    key_cols = TABLES[TARGET]["composite_key_source"]
    assert "dt_job" not in key_cols, "the job must not be key material"
    assert set(key_cols) <= set(cell), "every key column must be filled by the mapper"


@pytest.mark.parametrize("lot,slot,blank_column", [
    (LOT, "", "dt_slot"),
    (LOT, None, "dt_slot"),
    ("", SLOT, "dt_lot"),
    ("   ", SLOT, "dt_lot"),
])
def test_unconfirmed_metadata_is_emitted_blank_for_the_gate_not_gated_here(
        wired, lot, slot, blank_column):
    """A job with no confirmed lot/slot must produce NO MAP - but the refusal belongs to
    `chain_key_gate`, not to this file.

    `server/mappers/*.py` is gitignored by design, so a guard written here does not reach
    a deployment at all and a mapper written next month starts with no guard. The gate is
    tracked and sits on the funnel every chain-emitted row passes through. So the mapper's
    job is to emit the blank HONESTLY and let the gate name it; what this pins is that the
    blank survives to the gate rather than being dropped, and that the gate then refuses
    the row and NAMES the column - executed, not asserted about.
    """
    from database import schemas
    import chain_key_gate

    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        _Db([_Row(1, 1, 1, "B4")]), [_payload(lot=lot, slot=slot)], rule=RULE)
    cells = result["batches"][0]["updates"]
    assert cells, "the mapper must not silently drop the job; the gate does the refusing"
    assert blank_column in cells[0]["updates"], "the blank key column must reach the gate"

    chain_key_gate.reset_counters()
    try:
        items = [schemas.GeneralUpdateItem(**c) for c in cells]
        kept, report = chain_key_gate.screen(TARGET, items, rule_names=[RULE["name"]],
                                             transaction_id="t")
        assert kept == []
        assert report["refused_rows"] == len(cells)
        assert blank_column in report["by_column"]
        assert chain_key_gate.refused_rows() == {TARGET: len(cells)}
        assert crud.unfilled_key_columns(TARGET, items[0]) == [blank_column]
    finally:
        chain_key_gate.reset_counters()


def test_a_confirmed_job_is_not_refused_by_the_gate(wired):
    """The control for the test above. Without it, a gate that refused EVERYTHING would
    make that test pass."""
    from database import schemas
    import chain_key_gate

    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        _Db([_Row(1, 1, 1, "B4")]), [_payload()], rule=RULE)
    items = [schemas.GeneralUpdateItem(**c) for c in result["batches"][0]["updates"]]
    kept, report = chain_key_gate.screen(TARGET, items, transaction_id="t")
    assert report["refused_rows"] == 0
    assert len(kept) == 1


def test_target_job_column_can_no_longer_be_derived_and_the_refusal_says_so(wired):
    """Two map_key_columns and neither is the job. A rule that does not declare it is
    refused by name rather than being handed `dt_job`, which is only correct on the
    machine that wrote it."""
    rule = {k: v for k, v in RULE.items() if k != "target_job_column"}
    with pytest.raises(chain_bindings.ColumnBindingRefused) as exc:
        dt_standard_map_mapper.build_standard_dt_map_batches(
            _Db([_Row(1, 1, 1, "B4")]), [_payload()], rule=rule)
    assert "target_job_column" in str(exc.value)
    assert "2 map_key_columns" in str(exc.value)


def test_a_deployment_that_spells_the_confirmed_lot_differently_is_refused_by_name(wired):
    """No fallback to the stored lot: it is absent 40% of the time and WRONG 10% of the
    time, and a wrong lot writes cells into another lot's map with an identical cell
    count either way."""
    with pytest.raises(chain_bindings.ColumnBindingRefused) as exc:
        dt_standard_map_mapper._identity_source_columns(
            {"name": "s3", "map_key_source_columns": {"dt_lot": "not_a_column"}},
            TARGET, TRIGGER)
    assert "not_a_column" in str(exc.value)
    assert TRIGGER in str(exc.value)


def test_map_key_source_columns_lets_a_deployment_rename_the_confirmed_column(wired,
                                                                             monkeypatch):
    """The declaration layer, exercised. Same precedence as `chain_bindings`: a declared
    name out-ranks the same-name derivation."""
    cfg = dict(TABLES[TRIGGER])
    cfg["column_types"] = dict(cfg["column_types"], confirmed_lot="string")
    monkeypatch.setitem(crud.TABLE_CONFIG, TRIGGER, cfg)
    assert dt_standard_map_mapper._identity_source_columns(
        {"name": "s3", "map_key_source_columns": {"dt_lot": "confirmed_lot"}},
        TARGET, TRIGGER) == {"dt_lot": "confirmed_lot", "dt_slot": "dt_slot"}


# ---------------------------------------------------------------------------
# The fixtures above prove the CODE. This proves the landed DECLARATION.
# ---------------------------------------------------------------------------

def test_the_live_dt_map_declaration_is_the_physical_unit():
    """`server/config/` is gitignored, so this is skipped rather than failed where the
    file is absent. Where it IS present, a half-landed key move is the dangerous shape -
    `map_key_columns` gaining a column that `composite_key_source` did not would widen
    every derived purge scope."""
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "config", "table_config.json")
    if not os.path.exists(path):
        pytest.skip("live table_config.json not present in this checkout")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    dt_map = cfg.get("dt_map")
    if dt_map is None:
        pytest.skip("this deployment declares no dt_map")

    assert dt_map["map_key_columns"] == ["dt_lot", "dt_slot"]
    assert dt_map["composite_key_source"] == ["dt_lot", "dt_slot", "dt_x", "dt_y"]
    # The map key must be a PREFIX of the composite key, or the derived coordinate list
    # is not what the row key actually orders by.
    assert dt_map["composite_key_source"][:2] == dt_map["map_key_columns"]
    types = dt_map["column_types"]
    for col in ("dt_lot", "dt_slot", "dt_job"):
        assert types.get(col) == "string", col
    # Lot ids in this system are strings (`CL_2601_005_A5`). A number-declared lot column
    # cannot hold one, and the value is lost on the way in rather than at the key.
    inv = cfg.get("dt_inventory")
    if inv is not None:
        assert inv["column_types"]["dt_lot"] == "string"
        assert inv["column_types"]["dt_slot"] == "string"
