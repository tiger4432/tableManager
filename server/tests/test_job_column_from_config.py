"""A job column named something OTHER than `dt_job` must work, end to end.

WHY THIS FILE EXISTS
--------------------
Every other fixture in this tree writes `dt_job` — `trace_fixture/world.py`, `emit.py`,
the seed scripts, and every mapper test. So the suite was green forever while a
deployment whose column is spelled differently ran three dead chains and reported
success on all of them. A test written on `dt_job` cannot tell the working code from
the broken code, because the broken code's literal happens to be right.

Every table below spells the job column **`jobcol_test_job_id`**, and every assertion
is on that name. The prefix is deliberately one no operator config can contain (a
name collision with a real user table makes `init_dynamic_models` pre-empt the test
schema — see the `bonding_log` incident in the server-pm memory).

MUTATION CHECK — these were run against the pre-change mappers:
  * `dt_standard_map_mapper` with `_value(payload, "dt_job")` restored returns
    `{"batches": []}` for the payload here, so `test_standard_map_*` go red.
  * `dt_inventory_metadata_mapper` with `"dt_job": job_id` restored writes the wrong
    output key, so `test_inventory_metadata_writes_the_configured_name` goes red.
  * `core_usage_mapper` with `getattr(row, "dt_job", None)` restored skips every row
    and returns `[]`, so `test_core_usage_reads_the_configured_name` goes red.
None of them raises on the broken code — they all fail SILENTLY, which is the point.
"""
import json

import pytest

import chain_bindings
from database import crud, models, schemas


JOB = "jobcol_test_job_id"

_MAP_COLUMNS = {JOB: "string", "dt_x": "number", "dt_y": "number",
                "dt_index": "number", "c_bn": "string"}

TABLES = {
    # Source: identity derived from a single `map_key_columns`.
    "jobcol_test_src": {
        "business_key": "jobcol_test_cell_key",
        "map_key_columns": [JOB],
        "composite_key_source": [JOB, "dt_x", "dt_y"],
        "column_types": dict(_MAP_COLUMNS, jobcol_test_cell_key="string",
                             core_wafer="string", core_lot="string", core_slot="string",
                             core_x="number", core_y="number"),
    },
    # Target map: same shape, its own declaration.
    "jobcol_test_map": {
        "business_key": "jobcol_test_map_key",
        "map_key_columns": [JOB],
        "composite_key_source": [JOB, "dt_x", "dt_y"],
        "column_types": dict(_MAP_COLUMNS, jobcol_test_map_key="string"),
    },
    # Inventory: NO map_key_columns and NO composite_key_source, so the name has to be
    # inherited from the single-column `business_key`. This is `dt_inventory`'s shape.
    "jobcol_test_inv": {
        "business_key": JOB,
        "column_types": {JOB: "string", "dt_frame": "string",
                         "core_wafer_list": "string"},
    },
    # Two identity columns: which one carries the job is NOT derivable.
    "jobcol_test_pair": {
        "business_key": "jobcol_test_pair_key",
        "map_key_columns": ["ref_table", "map_key"],
        "column_types": {"ref_table": "string", "map_key": "string",
                         "jobcol_test_pair_key": "string"},
    },
}


@pytest.fixture(autouse=True)
def _declare_tables(monkeypatch):
    for name, cfg in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, cfg)


# ---------------------------------------------------------------------------
# The derivation itself
# ---------------------------------------------------------------------------

def test_identity_column_prefers_a_single_map_key_column():
    assert chain_bindings.identity_column("jobcol_test_src") == (
        JOB, "table_config.map_key_columns")


def test_identity_column_inherits_a_single_column_business_key():
    assert chain_bindings.identity_column("jobcol_test_inv") == (
        JOB, "table_config.business_key")


def test_identity_column_never_mistakes_a_composite_cell_key_for_the_job():
    """`jobcol_test_src`'s business key is a composite CELL key, not the job.

    It resolves through `map_key_columns`; the point of this test is that the
    `business_key` arm is gated on `composite_key_source` being absent, so it can
    never answer `jobcol_test_cell_key`.
    """
    name, _origin = chain_bindings.identity_column("jobcol_test_src")
    assert name == JOB and name != TABLES["jobcol_test_src"]["business_key"]


def test_two_identity_columns_are_refused_by_name():
    name, why = chain_bindings.identity_column("jobcol_test_pair")
    assert name is None
    assert "jobcol_test_pair" in why and "ref_table" in why and "map_key" in why


# ---------------------------------------------------------------------------
# The refusals. A refusal has to NAME what is missing, or it is just a crash.
# ---------------------------------------------------------------------------

def test_undeclared_and_underivable_refuses_and_names_rule_key_and_table():
    with pytest.raises(chain_bindings.ColumnBindingRefused) as excinfo:
        chain_bindings.resolve_column(
            {"name": "r_pair"}, "trigger_job_column", "jobcol_test_pair", "the trigger")
    message = str(excinfo.value)
    assert "r_pair" in message
    assert "trigger_job_column" in message
    assert "jobcol_test_pair" in message
    assert "chain_rules.json" in message and "table_config.json" in message


def test_a_declared_name_the_table_does_not_have_is_refused_by_name():
    with pytest.raises(chain_bindings.ColumnBindingRefused) as excinfo:
        chain_bindings.resolve_column(
            {"name": "r_typo", "source_job_column": "dt_job"},
            "source_job_column", "jobcol_test_src", "the source filter")
    message = str(excinfo.value)
    assert "r_typo" in message and "dt_job" in message and "jobcol_test_src" in message


def test_a_rule_with_no_table_is_refused_rather_than_defaulted():
    with pytest.raises(chain_bindings.ColumnBindingRefused) as excinfo:
        chain_bindings.resolve_column({"name": "r_notable"}, "trigger_job_column",
                                      None, "the trigger payload")
    assert "r_notable" in str(excinfo.value)


def test_decision_column_refuses_a_name_outside_the_decision_key():
    with pytest.raises(chain_bindings.ColumnBindingRefused) as excinfo:
        chain_bindings.resolve_decision_column(
            {"name": "r_dk", "reference_job_column": "dt_job"},
            "reference_job_column", [JOB], "the reference pattern")
    message = str(excinfo.value)
    assert "dt_job" in message and JOB in message


def test_decision_column_derives_a_single_key_and_refuses_two():
    assert chain_bindings.resolve_decision_column(
        {"name": "r_dk"}, "reference_job_column", [JOB], "x") == JOB
    with pytest.raises(chain_bindings.ColumnBindingRefused):
        chain_bindings.resolve_decision_column(
            {"name": "r_dk"}, "reference_job_column", [JOB, "product"], "x")


def test_model_column_refusal_names_the_table_and_the_column():
    class _Bare:
        pass

    with pytest.raises(chain_bindings.ColumnBindingRefused) as excinfo:
        chain_bindings.model_column(_Bare, "jobcol_test_src", JOB, "the source filter")
    assert "jobcol_test_src" in str(excinfo.value) and JOB in str(excinfo.value)


# ---------------------------------------------------------------------------
# The mappers, driven on a NON-`dt_job` name
# ---------------------------------------------------------------------------

FRAME = {
    "grid_cols": 10, "grid_rows": 8,
    "grid_start_x": 1, "grid_start_y": 1,
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": 300, "phys_chip_x": 1, "phys_chip_y": 1,
    "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3,
}


class _Column:
    """Stands in for an InstrumentedAttribute: records what it was compared to."""

    def __eq__(self, value):
        return ("eq", value)

    def in_(self, values):
        return ("in", list(values))


class _SourceModel:
    pass


setattr(_SourceModel, JOB, _Column())


class _Row:
    def __init__(self, x, y, index, bin_value):
        self.dt_x, self.dt_y = x, y
        self.dt_index, self.c_bn = index, bin_value


class _Query:
    def __init__(self, rows, seen):
        self.rows, self.seen = rows, seen

    def filter(self, criterion):
        self.seen.append(criterion)
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows, self.seen = rows, []

    def query(self, _model):
        return _Query(self.rows, self.seen)


def _standard_map_rule():
    return {
        "name": "jobcol_test_standard_map",
        "trigger_table": "jobcol_test_inv",
        "source_table": "jobcol_test_src",
        "target_table": "jobcol_test_map",
    }


def _standard_map_payload():
    return {"data": {
        JOB: {"value": "J-1"},
        "dt_frame": {"value": json.dumps(FRAME)},
        "dt_x_base": {"value": "X"}, "dt_x_sign": {"value": 1}, "dt_x_offset": {"value": 0},
        "dt_y_base": {"value": "Y"}, "dt_y_sign": {"value": 1}, "dt_y_offset": {"value": 0},
    }}


def _run_standard_map(monkeypatch):
    from mappers import dt_standard_map_mapper

    monkeypatch.setitem(models.DYNAMIC_TABLES, "jobcol_test_src", _SourceModel)
    monkeypatch.setattr(dt_standard_map_mapper.map_meta_registrar, "meta_business_key",
                        lambda table, map_id: "%s_%s" % (table, map_id))
    monkeypatch.setattr(dt_standard_map_mapper.map_overlay, "load_map_meta",
                        lambda _db, _table, _map_id: None)
    db = _Db([_Row(1, 1, 1, "B4"), _Row(2, 3, 2, "B1")])
    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        db, [_standard_map_payload()], rule=_standard_map_rule())
    return db, result


def test_standard_map_reads_the_trigger_payload_by_the_configured_name(monkeypatch):
    """The trigger table has no `map_key_columns` — the name comes from `business_key`."""
    _db, result = _run_standard_map(monkeypatch)
    assert len(result["batches"]) == 1, "a non-dt_job payload produced no batch at all"
    assert len(result["batches"][0]["updates"]) == 2


def test_standard_map_filters_the_source_by_the_configured_name(monkeypatch):
    db, _result = _run_standard_map(monkeypatch)
    assert db.seen == [("eq", "J-1")], "the source filter did not use the resolved column"


def test_standard_map_writes_the_configured_name_as_the_output_key(monkeypatch):
    _db, result = _run_standard_map(monkeypatch)
    written = result["batches"][0]["updates"][0]["updates"]
    assert JOB in written and written[JOB] == "J-1"
    assert "dt_job" not in written


def test_standard_map_scopes_the_replace_by_the_configured_name(monkeypatch):
    """The `replace_map` scope is the one output key whose spelling decides a DELETE."""
    _db, result = _run_standard_map(monkeypatch)
    assert result["batches"][0]["scope"] == {JOB: "J-1"}


def test_inventory_metadata_writes_the_configured_name(monkeypatch):
    from mappers.dt_inventory_metadata_mapper import copy_dt_metadata_to_inventory_batch

    result = copy_dt_metadata_to_inventory_batch(None, [{"data": {
        "target_table": {"value": "jobcol_test_src"},
        "map_id": {"value": "J-1"},
        "grid_metadata": {"value": json.dumps({"ncols": 12})},
    }}], rule={"name": "jobcol_test_inv_meta",
               "metadata_target_table": "jobcol_test_src",
               "target_table": "jobcol_test_inv"})
    written = result["updates"][0]["updates"]
    assert written[JOB] == "J-1"
    assert "dt_job" not in written


def test_core_usage_reads_the_configured_name(monkeypatch):
    from types import SimpleNamespace

    from mappers import core_usage_mapper

    equation = {"core_x_base": "X", "core_x_sign": 1, "core_x_offset": 4,
                "core_y_base": "Y", "core_y_sign": 1, "core_y_offset": 4}
    rows = [SimpleNamespace(core_wafer="W1", core_x=1, core_y=2,
                            core_lot="L1", core_slot="S1", **{JOB: "J-1"})]
    batches = core_usage_mapper._usage_batches(rows, {"J-1": equation}, JOB,
                                               "jobcol_test_usage")
    assert len(batches) == 1, "a non-dt_job row was skipped and produced no usage map"
    assert batches[0]["updates"][0]["updates"]["used_count"] == 1


# ---------------------------------------------------------------------------
# What a wrongly-named `replace_map` scope actually does downstream.
#
# This is the question the survey flagged as load-bearing: the scope is the ONE
# class-(c) output key that can DELETE rather than merely fail to write. Pin the
# answer so a future change cannot quietly turn the refusal into a purge.
# ---------------------------------------------------------------------------

def test_an_undeclared_explicit_scope_key_refuses_before_anything_is_deleted():
    batch = schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates={JOB: "J-1", "dt_x": 1, "dt_y": 1})],
        replace_map=True, scope={"dt_job": "J-1"})
    with pytest.raises(ValueError) as excinfo:
        crud.derive_replace_map_scope("jobcol_test_map", batch)
    message = str(excinfo.value)
    assert "dt_job" in message and "jobcol_test_map" in message


def test_a_correctly_named_explicit_scope_resolves_to_exactly_that_filter():
    batch = schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates={JOB: "J-1", "dt_x": 1, "dt_y": 1})],
        replace_map=True, scope={JOB: "J-1"})
    assert crud.derive_replace_map_scope("jobcol_test_map", batch) == {JOB: "J-1"}
