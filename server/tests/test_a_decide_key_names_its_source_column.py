# -*- coding: utf-8 -*-
"""A decide's key and list items may name the derived column and the source column apart (owner 10-27, lead ㄱ).

    "key": [{"d_job": "s_job"}, ...]   - the derived row's d_job carries the source row's s_job
    "key": ["job", ...]                - a name alone: the same column on both tables (as before)

`decision_key` keeps the derived names; `chain_bindings.key_source` / `list_source` give the source columns, and
every seat that reads the SOURCE goes through them. The gate is a table, seat x (same name | pair): the pair fixture
spells no name on both tables, so a seat that still reads the source by the derived name reads nothing.

    seat                                  same name          pair
    validator: refusals and the cells     test_the_validator_*  (both shapes in each case)
    live chain: key, list, count          ROWS                ROWS
    a row that left its key (recount)     test_a_row_that_moves_off_a_key_is_recounted_by_its_source_column
    a key left empty, narrower identity   test_a_key_left_empty_keeps_the_derived_row_another_source_row_still_holds
    backfill                              test_the_backfill_makes_what_the_live_chain_made
    analysis (bind, presence, total)      test_the_queue_analysis_reads_the_source_by_its_columns
    analysis key part spelling            test_the_analysis_spells_a_key_part_by_its_source_column_type
    index wants · alignment index DDL     test_the_indexes_a_decide_asks_for_are_on_its_source_columns
    retype's key uses                     test_retype_names_the_source_column_as_the_decide_key
    alignment worklist · view             test_the_alignment_unit_finds_its_maps_by_the_source_column
    the two mapper samples                test_the_samples_name_the_unit_by_the_derived_column
"""
import anyio
import pytest

import chain_bindings
from chain import enrichment
from chain.enrichment import analysis, backfill
from database import crud, models, schemas
from tests.support.enrich_decl import enrich_chain_rules, write_rules

PAIR_SRC, PAIR_DRV, SAME_SRC, SAME_DRV = "dp_test_src", "dp_test_drv", "dp_test_src2", "dp_test_drv2"
TABLES = {
    PAIR_SRC: {"business_key": "s_row",
               "column_types": {"s_row": "string", "s_job": "string", "s_lot": "string", "s_note": "string",
                                "fill": "string"}},
    PAIR_DRV: {"business_key": "d_unit", "composite_key_source": ["d_job", "d_lot"], "composite_key_separator": "|",
               "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string", "d_note": "string",
                                "d_count": "number", "fill": "string"}},
    SAME_SRC: {"business_key": "row",
               "column_types": {"row": "string", "job": "string", "lot": "string", "note": "string",
                                "fill": "string"}},
    SAME_DRV: {"business_key": "unit", "composite_key_source": ["job", "lot"], "composite_key_separator": "|",
               "column_types": {"unit": "string", "job": "string", "lot": "string", "note": "string",
                                "d_count": "number", "fill": "string"}},
}
PAIR = {"source_table": PAIR_SRC, "derived_table": PAIR_DRV,
        "decision_key": [{"d_job": "s_job"}, {"d_lot": "s_lot"}], "target_fields": ["fill"],
        "list_columns": [{"d_note": "s_note"}], "aggregations": {"d_count": "count"}}
SAME = {"source_table": SAME_SRC, "derived_table": SAME_DRV,
        "decision_key": ["job", "lot"], "target_fields": ["fill"],
        "list_columns": ["note"], "aggregations": {"d_count": "count"}}
#: the pair fixture's derived names -> the same-name fixture's, so one expectation reads both
AS_SAME = {"d_job": "job", "d_lot": "lot", "d_note": "note", "d_count": "d_count", "fill": "fill"}
CASES = {"pair": (PAIR_SRC, PAIR_DRV, "s_row", {"job": "s_job", "lot": "s_lot", "note": "s_note"}),
         "same": (SAME_SRC, SAME_DRV, "row", {"job": "job", "lot": "lot", "note": "note"})}


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, {"dp_pair": PAIR, "dp_same": SAME})
    return db_session


def _rule(name):
    rule, why = enrichment.config._validate_rule(name, dict(PAIR if name == "dp_pair" else SAME), TABLES)
    assert why is None, why
    return rule


def _write(db, table, rows, tx):
    items = [schemas.GeneralUpdateItem(updates=dict(row), source_name="pipeline_parser", updated_by="watcher")
             for row in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=items, transaction_id=tx, silent=True))


def _seed(db, case, rows, tx):
    """rows as (row id, job, lot, note) - spelled in the case's own source columns."""
    src, _drv, row_col, cols = CASES[case]
    _write(db, src, [{row_col: r, cols["job"]: j, cols["lot"]: lot, cols["note"]: n} for r, j, lot, n in rows], tx)


def _run(db, table, tx):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrich_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = [e for e in db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == table,
                                                         DatabaseOutbox.processed_chain == False)  # noqa: E712
              .order_by(DatabaseOutbox.id.asc()).all() if (e.payload or {}).get("transaction_id") == tx]
    assert events, (table, tx)

    async def run():
        ok, err, _ = await process_chain_transaction_group(tx, events, db, rules)
        assert ok, err
        for e in events:
            e.processed_chain = True
        db.commit()

    anyio.run(run)


def _derived(db, case):
    """{(job, lot): {note, d_count, fill}} in the same-name spelling, whichever fixture wrote it."""
    drv = CASES[case][1]
    model = models.DYNAMIC_TABLES[drv]
    names = AS_SAME if case == "pair" else {v: v for v in AS_SAME.values()}
    out = {}
    for row in db.query(model).all():
        cells = {same: getattr(row, mine) for mine, same in names.items()}
        key = (cells.pop("job"), cells.pop("lot"))
        out[key] = dict(cells, unit=row.business_key_val)
    return out


ROWS = [("r1", "J1", "L1", "N1"), ("r2", "J1", "L1", None), ("r3", "J2", "L9", "N3")]
WANT = {("J1", "L1"): {"note": "N1", "d_count": 2, "fill": None, "unit": "J1|L1"},
        ("J2", "L9"): {"note": "N3", "d_count": 1, "fill": None, "unit": "J2|L9"}}


# ---------------------------------------------------------------------------
# the validator
# ---------------------------------------------------------------------------

def test_the_validator_writes_the_source_cells_and_a_name_alone_reads_itself():
    pair, same = _rule("dp_pair"), _rule("dp_same")
    assert (pair["decision_key"], pair["key_source"]) == (["d_job", "d_lot"], ["s_job", "s_lot"])
    assert (pair["list_columns"], pair["list_source"]) == (["d_note"], {"d_note": "s_note"})
    assert (same["decision_key"], same["key_source"]) == (["job", "lot"], ["job", "lot"])
    assert (same["list_columns"], same["list_source"]) == (["note"], {"note": "note"})
    for rule in (pair, same):
        assert chain_bindings.key_source(rule) == rule["key_source"]
        assert chain_bindings.list_source(rule) == rule["list_source"]
    # a rule built by hand without the cells: a name alone, as before
    assert chain_bindings.key_source({"decision_key": ["a"]}) == ["a"]
    assert chain_bindings.list_source({"list_columns": ["b"]}) == {"b": "b"}


@pytest.mark.parametrize("cell, item, said", [
    ("decision_key", {"d_job": "ghost"}, "decision_key column(s) missing in source table: ['ghost']"),
    ("decision_key", "ghost", "decision_key column(s) missing in source table: ['ghost']"),
    ("decision_key", {"ghost": "s_job"}, "decision_key column(s) missing in derived table: ['ghost']"),
    ("list_columns", {"d_note": "ghost"}, "list_columns pair(s) read column(s) missing in source table "
                                          "'dp_test_src': ['d_note <- ghost']"),
    ("decision_key", {"d_job": "s_job", "d_lot": "s_lot"}, "'decision_key' must be a non-empty list of column "
                                                           "names or {derived: source} pairs"),
    ("decision_key", {"d_job": 1}, "'decision_key' must be a non-empty list"),
    ("list_columns", {"d_note": ""}, "'list_columns' must be a list of column names or {derived: source} pairs"),
])
def test_the_validator_refuses_a_name_the_tables_lack(cell, item, said):
    raw = dict(PAIR, **{cell: [item]})
    if cell == "list_columns":
        raw["decision_key"] = PAIR["decision_key"]
    rule, why = enrichment.config._validate_rule("dp_pair", raw, TABLES)
    assert rule is None
    assert said in why


def test_a_list_column_the_derived_table_lacks_is_dropped_and_said_whichever_shape():
    for item in ({"ghost": "s_note"}, "ghost"):
        said = []
        rule, why = enrichment.config._validate_rule("dp_pair", dict(PAIR, list_columns=[item, {"d_note": "s_note"}]),
                                                     TABLES, rejections=said)
        assert why is None, why
        assert (rule["list_columns"], rule["list_source"]) == (["d_note"], {"d_note": "s_note"})
        assert any("list_column 'ghost' dropped" in str(r) for r in said), said
    # a name alone the source lacks stands, as before - it only shows the derived column
    rule, why = enrichment.config._validate_rule("dp_pair", dict(PAIR, list_columns=["d_count"]), TABLES)
    assert why is None and rule["list_source"] == {"d_count": "d_count"}


# ---------------------------------------------------------------------------
# the live chain, the recount, the backfill
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["pair", "same"])
def test_the_live_chain_carries_the_key_the_list_and_the_count(env, case):
    _seed(env, case, ROWS, "tx-%s" % case)
    _run(env, CASES[case][0], "tx-%s" % case)
    assert _derived(env, case) == WANT


@pytest.mark.parametrize("case", ["pair", "same"])
def test_a_row_that_moves_off_a_key_is_recounted_by_its_source_column(env, case):
    src, _drv, row_col, cols = CASES[case]
    _seed(env, case, ROWS, "tx1-%s" % case)
    _run(env, src, "tx1-%s" % case)
    _write(env, src, [{row_col: "r2", cols["lot"]: "L2"}], "tx2-%s" % case)
    _run(env, src, "tx2-%s" % case)
    got = _derived(env, case)
    assert got[("J1", "L1")]["d_count"] == 1
    assert got[("J1", "L2")]["d_count"] == 1


@pytest.mark.parametrize("case", ["pair", "same"])
def test_the_backfill_makes_what_the_live_chain_made(env, case):
    name = "dp_%s" % case
    _seed(env, case, ROWS, "tx-%s" % case)        # its outbox events are never run: the backfill makes the rows
    stats = backfill.run_backfill(env, backfill.load_rule(name, crud.TABLE_CONFIG), apply=True, log=lambda *_: None)
    assert stats["rows_scanned"] == 3, stats
    assert _derived(env, case) == WANT


def test_a_key_left_empty_keeps_the_derived_row_another_source_row_still_holds(db_session, tmp_path, monkeypatch):
    """The derived identity (d_job) is narrower than the key (d_job, d_lot): a key left with no source row is asked
    whether any source row still holds its identity - by the identity's SOURCE column."""
    tables = {PAIR_SRC: TABLES[PAIR_SRC],
              "dp_test_drv3": {"business_key": "d_unit", "composite_key_source": ["d_job"],
                               "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string",
                                                "fill": "string"}}}
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, {"dp_narrow": dict(PAIR, derived_table="dp_test_drv3", list_columns=[],
                                                          aggregations={})})
    _write(db_session, PAIR_SRC, [{"s_row": "r1", "s_job": "J1", "s_lot": "L1"},
                                  {"s_row": "r2", "s_job": "J1", "s_lot": "L2"}], "tx1")
    _run(db_session, PAIR_SRC, "tx1")
    _write(db_session, PAIR_SRC, [{"s_row": "r1", "s_lot": "L2"}], "tx2")
    _run(db_session, PAIR_SRC, "tx2")
    model = models.DYNAMIC_TABLES["dp_test_drv3"]
    assert [row.business_key_val for row in db_session.query(model).all()] == ["J1"]


# ---------------------------------------------------------------------------
# the analysis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["pair", "same"])
def test_the_queue_analysis_reads_the_source_by_its_columns(env, case):
    src, _drv, row_col, cols = CASES[case]
    _seed(env, case, ROWS, "tx-%s" % case)
    _run(env, src, "tx-%s" % case)
    _write(env, src, [{row_col: "r1", "fill": "F"}], "tx2-%s" % case)
    rule = _rule("dp_%s" % case)
    keys = {rule["decision_key"][0]: "J1", rule["decision_key"][1]: "L1"}
    clean, raw = analysis._typed_key_values(rule, keys)
    assert clean == ("J1", "L1")
    assert analysis._source_target_presence(env, rule, "fill", {clean: raw}) == {("J1", "L1"): 1}
    out = analysis.classify_queue(env, rule, log=lambda *_: None)
    assert sum(out["counts"].values()) == 2, out


def test_the_analysis_spells_a_key_part_by_its_source_column_type(env):
    """A number source column read under a text derived name: the part is spelled as the SOURCE stores it."""
    tables = {"dp_test_src5": {"business_key": "s_row",
                               "column_types": {"s_row": "string", "s_job": "string", "s_lot": "number"}},
              "dp_test_drv5": {"business_key": "d_unit", "composite_key_source": ["d_job", "d_lot"],
                               "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string"}}}
    crud.TABLE_CONFIG.update(tables)
    rule, why = enrichment.config._validate_rule("dp_typed", dict(PAIR, source_table="dp_test_src5",
                                                                  derived_table="dp_test_drv5", target_fields=[],
                                                                  list_columns=[], aggregations={}), tables)
    assert why is None, why
    clean, raw = analysis._typed_key_values(rule, {"d_job": "J1", "d_lot": "01"})
    assert clean == ("J1", "1")
    assert raw[1] == 1


# ---------------------------------------------------------------------------
# the indexes, retype
# ---------------------------------------------------------------------------

def test_the_indexes_a_decide_asks_for_are_on_its_source_columns(env):
    wants = {(table, tuple(columns)) for table, columns, _why in models.decide_key_wants(crud.TABLE_CONFIG)}
    assert (PAIR_SRC, ("s_job", "s_lot")) in wants
    assert (SAME_SRC, ("job", "lot")) in wants
    for name, columns in (("dp_pair", '"s_job", "s_lot"'), ("dp_same", '"job", "lot"')):
        _index, ddl = models.alignment_decision_key_index_ddl(dict(_rule(name), alignment=True), {})
        assert ddl.endswith("(%s)" % columns), ddl


def test_retype_names_the_source_column_as_the_decide_key(env):
    from admin import retype

    assert "decide dp_pair" in retype.key_uses(PAIR_SRC, "s_job")
    assert "decide dp_pair" not in retype.key_uses(PAIR_SRC, "d_job")
    assert "decide dp_same" in retype.key_uses(SAME_SRC, "job")


# ---------------------------------------------------------------------------
# alignment
# ---------------------------------------------------------------------------

def _alignment_tables(unit):
    import map_overlay
    from tests import test_map_alignment_single_key as sk1

    tables = {
        "dpa_test_log": {"business_key": "cell_key",
                         "column_types": {"cell_key": "string", "s_job": "string", "job_id": "string", "job": "string",
                                          "dt_x": "number", "dt_y": "number", "c_bn": "string"},
                         "map_key_columns": ["job"]},
        "dpa_test_inv_" + unit: {"business_key": "unit_key", "composite_key_separator": "|", "composite_key_source": [unit],
                         "column_types": {"unit_key": "string", "d_job": "string", "job_id": "string",
                                          "map_metadata": "string"}},
        "dpa_test_map": dict(sk1.TABLES[sk1.MAPT]),
    }
    for product_table in (map_overlay.VALID_DIE_TABLE, map_overlay.META_TABLE):
        tables[product_table] = sk1.TABLES[product_table]
    return tables


@pytest.mark.parametrize("unit, item", [("d_job", {"d_job": "s_job"}), ("job_id", "job_id")])
def test_the_alignment_unit_finds_its_maps_by_the_source_column(db_session, unit, item):
    import json

    import map_alignment as ma
    import map_overlay
    from tests import test_map_alignment_single_key as sk1

    tables = _alignment_tables(unit)
    inv = "dpa_test_inv_" + unit
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    for table in tables:             # each one, not create_all: a test before this may have retired a product table
        models.DYNAMIC_TABLES[table].__table__.create(bind=db_session.get_bind(), checkfirst=True)
    map_overlay._FRAME_TF_CACHE.clear()
    raw = {"source_table": "dpa_test_log", "derived_table": inv, "decision_key": [item],
           "target_fields": ["map_metadata"], "alignment": True}
    rule, why = enrichment.config._validate_rule("dpa_rule", raw, tables)
    assert why is None, why
    read = chain_bindings.key_source(rule)[0]
    d, s = models.DYNAMIC_TABLES[inv], models.DYNAMIC_TABLES["dpa_test_log"]
    meta = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    job, map_id = "J-" + unit, "M-" + unit       # the log and the meta table are shared by both cases
    db_session.add(d(row_id="d_" + unit, business_key_val=job, unit_key=job, **{unit: job}))
    for i in range(2):
        db_session.add(s(row_id="s%d_%s" % (i, unit), business_key_val="c%d_%s" % (i, unit), cell_key="c%d_%s" % (i, unit),
                         job=map_id, dt_x=i + 3, dt_y=i + 3, c_bn="1", **{read: job}))
    db_session.add(meta(row_id="m_" + unit, business_key_val="dpa_test_map|" + map_id, target_table="dpa_test_map",
                        map_id=map_id, grid_metadata=json.dumps(sk1._meta())))
    db_session.commit()

    units = ma.build_alignment_worklist(db_session, {}, rule, "dpa_test_map")["units"]
    assert [(u["unit_key"], u["map_count"]) for u in units] == [(job, 1)]
    view = ma.build_alignment_view(db_session, {}, rule, {unit: job}, "dpa_test_map",
                                   include_cells=False, x_col="dt_x", y_col="dt_y")
    assert view["sources"]["map_count"] == 1


def test_the_samples_name_the_unit_by_the_derived_column(env, monkeypatch):
    from conftest import carried_mapper

    dt = carried_mapper("dt_alignment_metadata_mapper")
    payloads = [{"row_id": "r1", "data": {"s_job": {"value": "J1"}, "d_job": {"value": "WRONG"}}}]
    assert dt._decision_units(payloads, ["d_job"], ["s_job"]) == [{"d_job": "J1"}]
    seen = []
    monkeypatch.setattr(dt.alignment_view_service, "declared_alignment_rule",
                        lambda _name: {"decision_key": ["d_job"], "key_source": ["s_job"]})
    monkeypatch.setattr(dt.alignment_view_service, "resolve_alignment_view",
                        lambda _db, _rule, key_values, *_a, **_k: seen.append(key_values) or {"state": "none"})
    monkeypatch.setattr(dt.map_overlay, "load_overlay_config", lambda: {})
    dt.build_dt_alignment_metadata_batch(None, payloads, {"alignment_rule": "r", "map_table": "m",
                                                          "metadata_target_table": "t"})
    assert seen == [{"d_job": "J1"}]

    core = carried_mapper("core_alignment_mapper")
    seen.clear()
    monkeypatch.setattr(core.alignment_view_service, "declared_alignment_rule",
                        lambda _name: {"decision_key": ["d_job"], "key_source": ["s_job"]})
    monkeypatch.setattr(core.alignment_view_service, "resolve_alignment_view",
                        lambda _db, _rule, key_values, *_a, **_k: seen.append(key_values) or {"state": "none"})
    monkeypatch.setattr(core, "_primary_group", lambda rows, _selector: {"identity": {}, "rows": rows})
    monkeypatch.setattr(core, "_reference_spec", lambda _rule, _identity: "ref:1")
    _write(env, PAIR_SRC, [{"s_row": "r1", "s_job": "J1"}], "tx-core")
    core.build_core_frame_confirmation_batch(env, [{"row_id": "r1", "data": {"s_job": {"value": "J1"}}}], {
        "alignment_rule": "r", "map_table": PAIR_SRC, "target_table": PAIR_DRV, "source_table": PAIR_SRC,
        "job_column": "s_job", "target_job_column": "d_job"})
    assert seen == [{"d_job": "J1"}]
