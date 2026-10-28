# -*- coding: utf-8 -*-
"""Owner 10-29 «함수조인 ㄱ» (lead): a gathering join (`take ... fn`) reads every value row of the keys a batch touched,
and the value table had no index on the join key - many rows a key, so no unique one - so each batch scanned the
whole value table. The left lookup seat (`declared_lookup_targets` -> `ensure_lookup_once`) now names the value side
of a gathering join too; the index is the key expression the read compares (`notation_norm`, one author)."""
import os
import sys

import pytest
from sqlalchemy import event, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import join_into, rule_shape, synthesis, unique_key  # noqa: E402
from chain import join_key_index as vjc                         # noqa: E402
from database import crud, models, schemas                     # noqa: E402

TABLES = {"gk_meas": {"business_key": "rid", "composite_key_source": ["rid"],
                      "column_types": {"rid": "string", "lot": "string", "item": "string", "v": "number"},
                      "display_columns": ["rid", "lot", "item", "v"]},
          "gk_tgt": {"business_key": "tid", "composite_key_source": ["tid"],
                     "column_types": {"tid": "string", "lot": "string", "item": "string", "m": "number",
                                      "w": "number"},
                     "display_columns": ["tid", "lot", "item", "m", "w"]}}
VALUE_INDEX = vjc.required_index_name("gk_meas", ["lot", "item"], [None, None], vjc.LOOKUP_PREFIX)


def _stood(take):
    declaration = {"name": "gk", "on": {"table": "gk_meas"}, "into": {"table": "gk_tgt"},
                   "derive": {"kind": "join", "join": {"on": [{"left": c, "right": c} for c in ("lot", "item")],
                                                       "take": take}}}
    stood, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
    assert not refusal, refusal
    return stood


@pytest.fixture(name="tables")
def fixture_tables():
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def test_the_value_side_of_a_gathering_join_is_a_lookup_target_and_a_plain_joins_is_not(tables):
    gathering = {t for t, _c, _f in synthesis.declared_lookup_targets(_stood([{"from": "v", "into": "m", "fn": "max"}]))}
    plain = {t for t, _c, _f in synthesis.declared_lookup_targets(_stood([{"from": "v", "into": "w"}]))}
    assert (gathering, plain) == ({"gk_tgt", "gk_meas"}, {"gk_tgt"})


@pytest.mark.pg
def test_the_gathering_read_is_planned_through_the_value_key_index(tables, pg_session):
    db = pg_session
    from database.database import Base

    Base.metadata.create_all(bind=db.get_bind(), tables=[models.DYNAMIC_TABLES[t].__table__ for t in TABLES])
    rules = _stood([{"from": "v", "into": "m", "fn": "max"}])
    unique_key.forget()
    report = synthesis.ensure_declared_lookup_keys(db, rules)
    assert (VALUE_INDEX, "ok") in [(name, one.get("state")) for name, one in report["ensured"]], report
    crud.apply_batch_updates(db, "gk_meas", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"rid": "m%d" % i, "lot": "L1", "item": "I%d" % (i % 3), "v": i},
                                  source_name="seed", updated_by="gk") for i in range(6)]))
    crud.apply_batch_updates(db, "gk_tgt", schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"tid": "t1", "lot": "L1", "item": "I1"}, source_name="seed", updated_by="gk")]))
    db.commit()
    reference = next(r for r in rules if r.get("trigger_table") == "gk_meas")
    row_ids = [r[0] for r in db.execute(text("SELECT row_id FROM gk_meas"))]
    said = []

    def seen(_conn, _cursor, statement, params, _context, _many):
        if "FROM gk_meas" in statement and "coalesce" in statement.lower() and "v" in statement:
            said.append((statement, params))
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", seen)
    try:
        join_into.read(db, reference, row_ids)
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    assert said, "the read asked the value table nothing - this measures nothing"
    statement, params = said[-1]
    raw = db.connection().connection.dbapi_connection
    with raw.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute("EXPLAIN " + statement, params)
        plan = " / ".join(row[0] for row in cursor.fetchall())
    assert VALUE_INDEX in plan, plan
