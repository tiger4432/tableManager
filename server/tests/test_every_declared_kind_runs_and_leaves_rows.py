# -*- coding: utf-8 -*-
"""소유자 2026-09-17: 「각 체인 «선언 종류»별로 잘되는지도 체크해봐」

🔴 THE SUBJECT IS 「돈다」, NOT 「간다」. Every kind already had a test that it RESOLVES, and
resolution is a predicate - it says a name became a callable. This file asks the only
question that cannot be satisfied by a signature: after the seat ran this declaration, are
the rows THERE. 판정 562 was caught exactly here - a template that computed the right answer
and did not write it passed every resolution test in the repository.

⚠️ AND IT IS PER DECLARATION KIND, which the caller×door matrix
(`test_every_caller_and_door_leaves_the_same_envelope`) does not cover: that one varies WHO
runs a rule, this one varies WHAT was declared. The two together are the grid.

The five a declaration can be today, all reaching `dynamic_mappers` or an operator's own
module through the ONE seat (`rule_run.resolve`):
    join            derive: {kind: "join"}                     -> declared:join
    decide 파생행    derive: {kind: "decide"}, the dedup half    -> declared:enrich
    decide 오토컨펌  the same declaration's other half           -> declared:decide
    mapper          mapper_module / mapper_function             -> the operator's module
    virtual_join    virtual_join_rules.json, materialize: true  -> declared:virtual_join
"""
import json
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import dynamic_mappers, legacy_join_declaration            # noqa: E402
from chain import rule_run, rule_shape                                # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

SRC = "kinds_log"
DST = "kinds_attr"
ROWS = 3

TABLES = {
    SRC: {"business_key": "log_key", "composite_key_source": ["log_key"],
          "column_types": {"log_key": "string", "job": "string",
                           "lot_confirmed": "string", "note": "string",
                           "lot": "string"},
          "display_columns": ["log_key", "job", "lot_confirmed", "note", "lot"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "grade": "string"},
          "display_columns": ["job", "lot", "grade"]},
}

MAPPER_BODY = """
def map_it(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        key = ((p.get("data") or {}).get("log_key") or {}).get("value")
        out.append({"business_key_val": key,
                    "updates": {"log_key": key, "note": "seen"}})
    return {"updates": out}
"""


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.discover()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    # NEW rows only: `is_new` is the one shape `has_changed` cannot suppress, so a cell that
    # stays empty means the rule wrote nothing rather than that nothing changed.
    crud.apply_batch_updates(session, DST, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J", "lot": "LOT"},
                                  source_name="seed", updated_by="kinds")]))
    crud.apply_batch_updates(session, SRC, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "L%d" % n, "job": "J"},
                                  source_name="seed", updated_by="kinds")
        for n in range(ROWS)]))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _events(db, table):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == table).all()


def _values(db, table, column):
    model = models.DYNAMIC_TABLES[table]
    return [v for v in (getattr(r, column) for r in db.query(model).all()) if v]


def _run(db, tag, rules, trigger):
    worker._process_chain_transaction_group_sync(
        "tx-kinds-%s" % tag, _events(db, trigger), db, rules)
    db.commit()


def _door(rule):
    """Where this rule's name resolves - the seat, asked the way every caller asks it."""
    resolved = rule_run.resolve(rule)
    return "%s.%s" % (resolved.call.__module__, resolved.call.__name__)


# ---------------------------------------------------------------------------

def test_a_join_declaration_writes_the_taken_column(db):
    rules = rule_shape.expand_declaration(
        {"name": "kinds_join", "on": {"table": SRC}, "into": {"table": SRC},
         "derive": {"kind": "join", "join": {
             "right_table": DST, "on": [{"left": "job", "right": "job"}],
             "take": [{"from": "lot", "into": "lot_confirmed"}]}}},
        crud.TABLE_CONFIG)[0]

    assert rules[0]["mapper"] == "declared:join"
    assert _door(rules[0]) == "chain.dynamic_mappers._join"

    _run(db, "join", rules, SRC)

    assert _values(db, SRC, "lot_confirmed") == ["LOT"] * ROWS


def test_a_decide_declaration_writes_one_derived_row_per_key(db):
    """파생행 — 「키당 한 행」 is the whole of what the dedup half does, so N source rows
    collapsing to ONE derived identity is the assertion. A per-row count would pass for a
    mapper that never grouped."""
    rules = rule_shape.expand_declaration(
        {"name": "kinds_decide", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}},
        crud.TABLE_CONFIG)[0]
    dedup = [r for r in rules if r["name"].startswith("enrichment_dedup:")][0]

    assert dedup["mapper"] == "declared:enrich"
    assert _door(dedup) == "chain.dynamic_mappers._enrich"

    _run(db, "enrich", [dedup], SRC)

    # ROWS source rows carry one 「job」, so the derived table holds ONE identity.
    assert _values(db, DST, "job") == ["J"]


def test_an_auto_confirm_declaration_writes_the_single_candidate(db):
    """오토컨펌 «과» 참조뷰를 같이 잰다. The candidate comes out of a REFERENCE VIEW running
    real SQL, so this is also the proof that the reference-view capability survives - 소유자
    「인리치는 참조뷰 기능은 «보존»해야 해」 - measured by the value it wrote, not by a name."""
    rules = rule_shape.expand_declaration(
        {"name": "kinds_confirm", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {
             "key": ["job"], "fields": ["grade"], "auto_confirm": True,
             "reference_views": [{
                 "label": "후보",
                 "query": "SELECT lot AS grade FROM %s WHERE job = :job" % DST,
                 "candidate_for": {"grade": "grade"}}]}}},
        crud.TABLE_CONFIG)[0]
    dedup = [r for r in rules if r["name"].startswith("enrichment_dedup:")][0]
    confirm = [r for r in rules if r["name"].startswith("enrichment_auto_confirm:")][0]

    assert confirm["mapper"] == "declared:decide"
    assert _door(confirm) == "chain.dynamic_mappers._auto_confirm"

    _run(db, "ac-derive", [dedup], SRC)
    assert _values(db, DST, "grade") == [], "nothing may be confirmed before the probe runs"

    _run(db, "ac-confirm", [confirm], DST)

    assert _values(db, DST, "grade") == ["LOT"]


def test_a_file_mapper_declaration_writes_what_it_returned(db, tmp_path, monkeypatch):
    """The operator's own door, on the SAME arguments - 소유자 「체인 프로세스에 다 같은
    맵퍼 메소드로 인식되어서 움직이면됨. 같은 io를 가지고」."""
    (tmp_path / "kinds_probe_mapper.py").write_text(
        textwrap.dedent(MAPPER_BODY), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("kinds_probe_mapper", None)
    rule = {"name": "kinds_mapper", "enabled": True, "is_batch": True,
            "trigger_table": SRC, "target_table": SRC,
            "mapper_module": "kinds_probe_mapper", "mapper_function": "map_it"}
    try:
        assert _door(rule) == "kinds_probe_mapper.map_it"

        _run(db, "mapper", [rule], SRC)

        assert _values(db, SRC, "note") == ["seen"] * ROWS
    finally:
        sys.modules.pop("kinds_probe_mapper", None)


def test_a_materialized_virtual_join_writes_the_exposed_column(db, tmp_path):
    """virtual_join_rules.json 의 `materialize: true` — 판정 581 keeps its own body because a
    virtual join treats a colliding column absent-only, so folding it into `declared:join`
    would overwrite a hand-edited value. Three implementations, one door."""
    path = tmp_path / "virtual_join_rules.json"
    path.write_text(json.dumps({"kinds_vjoin": {
        "left_table": SRC, "right_table": DST,
        "join_key": [{"left": "job", "right": "job"}], "expose": ["lot"],
        "materialize": True, "max_rewrite_rows": 100, "enabled": True}}), encoding="utf-8")

    rules = legacy_join_declaration.synthesized_join_chain_rules(
        path=str(path), known_tables=crud.TABLE_CONFIG)

    assert [r["name"] for r in rules] == ["virtual_join:kinds_vjoin"]
    assert rules[0]["mapper"] == "declared:virtual_join"
    assert _door(rules[0]) == "chain.dynamic_mappers._legacy_materialized_join"

    _run(db, "vjoin", rules, SRC)

    assert _values(db, SRC, "lot") == ["LOT"] * ROWS


def test_the_five_kinds_are_the_whole_of_what_the_product_builds():
    """⚠️ THE CONTROL ON THIS FILE ITSELF. Four of the five names above are built by
    `dynamic_mappers`; if a fifth template appears, the tests above still pass and this file
    has quietly stopped being 「종류별로」. The remaining kind is an operator's own module,
    which has no name here to count."""
    mapper_sdk.discover()

    assert sorted(dynamic_mappers.TEMPLATES) == [
        "declared:decide", "declared:enrich", "declared:join", "declared:virtual_join"]
