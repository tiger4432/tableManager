# -*- coding: utf-8 -*-
"""A decide's key may expand into one derived row a listed value (owner 10-27 「하나의 키를 출력 테이블에 키+정해진
아이템 개수만큼 펼치고 싶을 때」, lead ㄱ):

    "decide": {"key": [...], "expand": {"column": "<derived column>", "values": ["<value>", ...]}}

The listed part has no source column: `chain_bindings.key_parts` splits the key into `source` and `listed`, the seats
that read the source keep reading `key_source`, and only the derived row's identity gains the listed column.

    seat                                    gate
    validator                               test_the_validator_*
    live chain - three listed, three rows   test_a_key_makes_a_row_a_listed_value
    backfill                                test_the_backfill_makes_the_listed_rows
    a row that left its key                 test_a_row_that_moves_off_a_key_recounts_every_listed_row
    a narrower identity, key left empty     test_a_key_left_empty_keeps_the_rows_another_source_row_holds
    the list changed, a replay              test_a_value_taken_off_the_list_goes_and_one_added_stands
    ... a person wrote on the row it took   test_a_value_taken_off_the_list_keeps_the_row_a_person_wrote_on
    no expand (control)                     test_without_expand_the_rule_and_its_rows_are_as_before
"""
import anyio
import pytest

import chain_bindings
from chain import enrichment
from chain.enrichment import backfill
from database import crud, models, schemas
from tests.support import line_tables
from tests.support.enrich_decl import enrich_chain_rules, rewrite_rules, write_rules

SRC, DRV, NARROW, PLAIN = "dx_test_src", "dx_test_drv", "dx_test_narrow", "dx_test_plain"
TABLES = {
    SRC: {"business_key": "s_row",
          "column_types": {"s_row": "string", "s_job": "string", "s_lot": "string", "s_note": "string"}},
    DRV: {"business_key": "d_unit", "composite_key_source": ["d_job", "d_lot", "item"], "composite_key_separator": "|",
          "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string", "item": "string",
                           "d_note": "string", "d_count": "number", "fill": "string"}},
    NARROW: {"business_key": "d_unit", "composite_key_source": ["d_job", "item"], "composite_key_separator": "|",
             "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string", "item": "string",
                              "fill": "string"}},
    PLAIN: {"business_key": "d_unit", "composite_key_source": ["d_job", "d_lot"], "composite_key_separator": "|",
            "column_types": {"d_unit": "string", "d_job": "string", "d_lot": "string", "item": "string",
                             "d_note": "string", "d_count": "number", "fill": "string"}},
}
LISTED = ["base", "leg 1", "leg 2"]
RULE = {"source_table": SRC, "derived_table": DRV, "decision_key": [{"d_job": "s_job"}, {"d_lot": "s_lot"}],
        "target_fields": ["fill"], "list_columns": [{"d_note": "s_note"}], "aggregations": {"d_count": "count"},
        "expand": {"column": "item", "values": LISTED}}
ROWS = [{"s_row": "r1", "s_job": "J1", "s_lot": "L1", "s_note": "N1"},
        {"s_row": "r2", "s_job": "J1", "s_lot": "L1"},
        {"s_row": "r3", "s_job": "J2", "s_lot": "L9", "s_note": "N3"}]


def _want(values=LISTED):
    return {(job, lot, item): {"d_note": note, "d_count": count, "unit": "%s|%s|%s" % (job, lot, item)}
            for job, lot, note, count in (("J1", "L1", "N1", 2), ("J2", "L9", "N3", 1)) for item in values}


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    for table in TABLES:                   # the table and its line table (old-shape recipe, owner 11-11)
        line_tables.build(db_session.get_bind(), table)
    path = write_rules(tmp_path, monkeypatch, {"dx_rule": RULE})
    db_session.info["rules_path"] = path
    yield db_session
    db_session.rollback()
    for table in TABLES:
        line_tables.drop(db_session.get_bind(), table)


def _write(db, rows, tx):
    items = [schemas.GeneralUpdateItem(updates=dict(row), source_name="pipeline_parser", updated_by="watcher")
             for row in rows]
    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=items, transaction_id=tx, silent=True))


def _run(db, tx):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrich_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = [e for e in db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC,
                                                         DatabaseOutbox.processed_chain == False)  # noqa: E712
              .order_by(DatabaseOutbox.id.asc()).all() if (e.payload or {}).get("transaction_id") == tx]
    assert events, tx

    async def run():
        ok, err, _ = await process_chain_transaction_group(tx, events, db, rules)
        assert ok, err
        for e in events:
            e.processed_chain = True
        db.commit()

    anyio.run(run)


def _rows(db, table=DRV):
    model = models.DYNAMIC_TABLES[table]
    return {(row.d_job, row.d_lot, row.item): {"d_note": row.d_note, "d_count": row.d_count,
                                               "unit": row.business_key_val}
            for row in db.query(model).all()}


def _rule(raw, tables=TABLES):
    return enrichment.config._validate_rule("dx_rule", dict(raw), tables)


# ---------------------------------------------------------------------------
# the validator
# ---------------------------------------------------------------------------

def test_the_validator_carries_expand_and_key_parts_split_the_key():
    rule, why = _rule(RULE)
    assert why is None, why
    assert rule["expand"] == {"column": "item", "values": LISTED}
    assert rule["decision_key"] == ["d_job", "d_lot"]
    parts = chain_bindings.key_parts(rule)
    assert parts == {"source": [("d_job", "s_job"), ("d_lot", "s_lot")], "listed": [("item", LISTED)],
                     "row": ["d_job", "d_lot", "item"]}
    assert chain_bindings.key_source(rule) == ["s_job", "s_lot"]


@pytest.mark.parametrize("change, said", [
    ({"expand": {"column": "item", "values": []}}, "'expand' must be {\"column\": <derived column>"),
    ({"expand": {"column": "item", "values": ["a", 1]}}, "'expand' must be {\"column\": <derived column>"),
    ({"expand": ["item"]}, "'expand' must be {\"column\": <derived column>"),
    ({"expand": {"column": "d_job", "values": ["a"]}}, "expand column 'd_job' is already a decision_key or fields"),
    ({"expand": {"column": "fill", "values": ["a"]}}, "expand column 'fill' is already a decision_key or fields"),
    ({"expand": {"column": "ghost", "values": ["a"]}}, "expand column 'ghost' missing in derived table"),
    ({"alignment": True}, "expand on an alignment rule is not supported - its unit would become key × values"),
    ({"derived_table": PLAIN}, "expand column 'item' is not in derived table 'dx_test_plain' composite_key_source"),
])
def test_the_validator_refuses_an_expand_it_cannot_make_rows_of(change, said):
    rule, why = _rule(dict(RULE, **change))
    assert rule is None
    assert said in why


def test_the_key_contract_names_the_listed_column():
    tables = dict(TABLES, **{NARROW: dict(TABLES[NARROW], composite_key_source=["d_job", "item", "d_note"],
                                          column_types=dict(TABLES[NARROW]["column_types"], d_note="string"))})
    rule, why = _rule(dict(RULE, derived_table=NARROW, list_columns=[], aggregations={}), tables)
    assert rule is None
    assert "composite_key_source must be a subset of decision_key + expand.column (violation: ['d_note'])" in why


# ---------------------------------------------------------------------------
# the rows
# ---------------------------------------------------------------------------

def test_a_key_makes_a_row_a_listed_value(env):
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    assert _rows(env) == _want()


def test_the_backfill_makes_the_listed_rows(env):
    _write(env, ROWS, "tx1")                       # its events are never run: the backfill makes the rows
    stats = backfill.run_backfill(env, backfill.load_rule("dx_rule", crud.TABLE_CONFIG), apply=True,
                                  log=lambda *_: None)
    assert stats["rows_scanned"] == 3, stats
    assert _rows(env) == _want()


def test_a_row_that_moves_off_a_key_recounts_every_listed_row(env):
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    _write(env, [{"s_row": "r2", "s_lot": "L2"}], "tx2")
    _run(env, "tx2")
    got = _rows(env)
    assert {item: got[("J1", "L1", item)]["d_count"] for item in LISTED} == {item: 1 for item in LISTED}
    assert {item: got[("J1", "L2", item)]["d_count"] for item in LISTED} == {item: 1 for item in LISTED}


def test_a_key_left_empty_keeps_the_rows_another_source_row_holds(env, tmp_path, monkeypatch):
    """The identity (d_job, item) is narrower than the row key (d_job, d_lot, item): a key left with no source row
    keeps its rows while a source row still holds d_job - asked by the identity's SOURCE column only."""
    write_rules(tmp_path, monkeypatch, {"dx_rule": dict(RULE, derived_table=NARROW, list_columns=[],
                                                        aggregations={})})
    _write(env, [{"s_row": "r1", "s_job": "J1", "s_lot": "L1"}, {"s_row": "r2", "s_job": "J1", "s_lot": "L2"}], "tx1")
    _run(env, "tx1")
    _write(env, [{"s_row": "r1", "s_lot": "L2"}], "tx2")
    _run(env, "tx2")
    model = models.DYNAMIC_TABLES[NARROW]
    assert sorted(row.business_key_val for row in env.query(model).all()) == sorted("J1|" + item for item in LISTED)


def test_a_value_taken_off_the_list_goes_and_one_added_stands(env):
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    changed = ["base", "leg 2", "leg 3"]
    rewrite_rules(env.info["rules_path"], {"dx_rule": dict(RULE, expand={"column": "item", "values": changed})})
    _write(env, [{"s_row": "r1", "s_note": "N1b"}], "tx2")      # the key J1/L1 runs again, as a replay runs it
    _run(env, "tx2")
    got = _rows(env)
    assert sorted(item for job, _lot, item in got if job == "J1") == sorted(changed)
    assert sorted(item for job, _lot, item in got if job == "J2") == sorted(LISTED)    # not run again: as it was


def test_a_value_taken_off_the_list_keeps_the_row_a_person_wrote_on(env):
    """뒤집음 · 소유자 10-28: the row a person wrote on stays - the rule's cells go, its key and the person's stay."""
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    crud.apply_batch_updates(env, DRV, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="J1|L1|leg 1", updates={"fill": "F"}, source_name=crud.USER_SOURCE, updated_by="okey")]))
    rewrite_rules(env.info["rules_path"], {"dx_rule": dict(RULE, expand={"column": "item", "values": ["base"]})})
    _write(env, [{"s_row": "r1", "s_note": "N1b"}], "tx2")
    _run(env, "tx2")

    got = _rows(env)
    assert sorted(item for job, _lot, item in got if job == "J1") == ["base", "leg 1"]
    assert got[("J1", "L1", "leg 1")] == {"d_note": None, "d_count": None, "unit": "J1|L1|leg 1"}
    model = models.DYNAMIC_TABLES[DRV]
    assert env.query(model).filter_by(business_key_val="J1|L1|leg 1").one().fill == "F"


def test_a_row_made_before_expand_goes_when_the_key_runs(env):
    """A row with no listed value (made before `expand` was written) holds no listed value - it goes."""
    model = models.DYNAMIC_TABLES[DRV]
    env.add(model(row_id="old", business_key_val="J1|L1|", d_unit="J1|L1|", d_job="J1", d_lot="L1"))
    env.commit()
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    assert set(_rows(env)) == set(_want())


def test_without_expand_the_rule_and_its_rows_are_as_before(env, tmp_path, monkeypatch):
    plain = {key: value for key, value in RULE.items() if key != "expand"}
    rule, why = _rule(dict(plain, derived_table=PLAIN))
    assert why is None, why
    assert "expand" not in rule
    assert chain_bindings.key_parts(rule)["listed"] == []
    write_rules(tmp_path, monkeypatch, {"dx_rule": dict(plain, derived_table=PLAIN)})
    _write(env, ROWS, "tx1")
    _run(env, "tx1")
    assert _rows(env, PLAIN) == {(job, lot, None): {"d_note": note, "d_count": count, "unit": "%s|%s" % (job, lot)}
                                 for job, lot, note, count in (("J1", "L1", "N1", 2), ("J2", "L9", "N3", 1))}
