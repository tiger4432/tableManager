# -*- coding: utf-8 -*-
"""총괄 3eca39091 (응용 표 7: a candidate query a key, 25,000 at 100k): a page of the auto-confirm queue asks
each reference view once for all its keys - VALUES of the keys CROSS JOIN LATERAL the probe - and answers what
asking key by key answers: the same candidates in the same order, the view's limit as it is. A statement that
fails is asked again key by key, and the answer says so (`probe_batch_fallbacks`). PostgreSQL only - SQLite
has no LATERAL and keeps asking key by key.
"""
import os
import sys

import pytest
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model                 # noqa: E402
from chain.enrichment import analysis, candidates                         # noqa: E402
from chain.enrichment import config as enrichment_config                  # noqa: E402
from database import crud, models, schemas                                # noqa: E402
from support.isolated_pg import scratch_connect_args                      # noqa: E402
from tests.support.enrich_decl import write_rules                         # noqa: E402

import test_backfill_enrichment as be                                     # noqa: E402

pytestmark = pytest.mark.pg
S = PG_TEST_SCHEMA
VIEWS = [
    {"label": "the chip", "limit": 5, "candidate_for": {"wafer_id": "wafer_id"},
     "query": "SELECT min(chip_id) AS wafer_id FROM bkfl_test_src WHERE equipment = :equipment "
              "AND event_time = :event_time"},
    # by the equipment alone, two values at most: one chip, two (ambiguous) and three (cut)
    {"label": "every chip", "limit": 2, "candidate_for": {"wafer_id": "wafer_id"},
     "query": "SELECT chip_id AS wafer_id FROM bkfl_test_src WHERE equipment = :equipment"},
]
CHIPS = {"E1": ["C1"], "E2": ["C1", "C2"], "E3": ["C1", "C2", "C3"], "E4": []}


@pytest.fixture(name="db")
def fixture_db(pg_engine, monkeypatch, tmp_path):
    engine = create_engine(pg_engine.url, pool_size=5, connect_args=scratch_connect_args(S))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
    for name in be.BKFL_TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(be.BKFL_TABLES)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.update(be.BKFL_TABLES)
    scratch = MetaData(schema=S)
    for name in be.BKFL_TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(engine)
    write_rules(tmp_path, monkeypatch, {"bkfl_rule": dict(be.RULES_FILE["bkfl_rule"], reference_views=VIEWS)})
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        for equipment, chips in CHIPS.items():
            for t in range(3):
                for chip in chips:
                    db.execute(text('INSERT INTO "%s".bkfl_test_src (row_id, business_key_val, log_key, equipment, '
                                    'event_time, chip_id) VALUES (:r, :r, :r, :e, :t, :c)' % S),
                               {"r": "%s_%d_%s" % (equipment, t, chip), "e": equipment, "t": "T%d" % t, "c": chip})
        crud.apply_batch_updates(db, "bkfl_test_derived", schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"equipment": equipment, "event_time": "T%d" % t},
                                      source_name="seed", updated_by="seed")
            for equipment in CHIPS for t in range(3)]))
        db.commit()
        yield db
    finally:
        db.close()
        with engine.begin() as conn:
            for name in be.BKFL_TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (S, name)))
            conn.execute(text('DELETE FROM "%s".cell_sources WHERE table_name = ANY(:t)' % S), {"t": list(be.BKFL_TABLES)})
            conn.execute(text('DELETE FROM "%s".database_outbox WHERE table_name = ANY(:t)' % S),
                         {"t": list(be.BKFL_TABLES)})
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in be.BKFL_TABLES:
            retire_dynamic_model(name)
        engine.dispose()


def _queue(db, rule):
    return [{"row_id": r["row_id"], "business_key_val": r["business_key_val"], "keys": r["keys"],
             "blank_targets": ["wafer_id"]}
            for page in analysis.derived_pages(db, rule, scope=analysis.SCOPE_QUEUE) for r in page]


def _confirm(db, rule, keyed, statements):
    def seen(_conn, _cursor, statement, *_rest):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", seen)
    try:
        return candidates.confirm_keys(db, rule, keyed, apply=False, caps=enrichment_config.load_read_caps())
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", seen)


def _rule():
    from admin import retroactive
    return retroactive._enrichment_rule("bkfl_rule")


def test_a_page_asks_each_view_once_and_answers_as_key_by_key(db, monkeypatch):
    rule = _rule()
    keyed = _queue(db, rule)
    assert len(keyed) == 12, "canary: four equipments, three times each"
    together, one_by_one = [], []
    asked = _confirm(db, rule, keyed, together)
    with monkeypatch.context() as each:
        each.setattr(enrichment_config, "LATERAL_DIALECTS", ())
        alone = _confirm(db, rule, keyed, one_by_one)
    assert asked == alone and "probe_batch_fallbacks" not in asked
    # the four kinds of answer are all there, or the equality says nothing
    assert asked["confirmed"] == 3 and asked["per_target"]["wafer_id"]["refused"] == {
        candidates.REASON_AMBIGUOUS: 3, candidates.REASON_DISTINCT_TRUNCATED: 3, candidates.REASON_NO_CANDIDATE: 3}, asked
    lateral = [s for s in together if "CROSS JOIN LATERAL" in s]
    probes = [s for s in together if "__enrichment_ref" in s]
    assert (len(lateral), len(probes)) == (2, 2), "one statement a view for the page, none a key"
    assert len([s for s in one_by_one if "__enrichment_ref" in s]) == 2 * 12

    # and each key's whole verdict - evidence, candidates, their order - is the one key by key gives
    together_asked = candidates.ask_together(db, rule, keyed, {(r["row_id"], "wafer_id") for r in keyed},
                                             enrichment_config.load_read_caps(), {})
    for entry in keyed:
        with_page = candidates.resolve_target_candidate(db, rule, entry["keys"], "wafer_id", asked=together_asked)
        alone = candidates.resolve_target_candidate(db, rule, entry["keys"], "wafer_id")
        assert with_page == alone, entry["keys"]


def test_a_statement_that_fails_is_asked_key_by_key_and_the_answer_says_so(db, monkeypatch):
    rule = _rule()
    keyed = _queue(db, rule)
    run = enrichment_config._isolated_execute

    def refuse_together(session, stmt, params):
        if "CROSS JOIN LATERAL" in str(stmt):
            raise RuntimeError("the one statement failed")
        return run(session, stmt, params)
    with monkeypatch.context() as each:
        each.setattr(enrichment_config, "LATERAL_DIALECTS", ())
        alone = _confirm(db, rule, keyed, [])
    monkeypatch.setattr(enrichment_config, "_isolated_execute", refuse_together)
    fell_back = _confirm(db, rule, keyed, [])
    assert fell_back.pop("probe_batch_fallbacks") == {"the chip": 12, "every chip": 12}
    assert fell_back == alone


def test_a_failed_batch_says_itself_in_the_log_and_the_preview(db, monkeypatch, caplog):
    """총괄 59c0bfb8c 2: the batch failure has its own sentence (not the view's own failure) and its count reaches
    the log line and the preview's sentence."""
    from admin import retroactive

    run = enrichment_config._isolated_execute

    def refuse_together(session, stmt, params):
        if "CROSS JOIN LATERAL" in str(stmt):
            raise RuntimeError("the one statement failed")
        return run(session, stmt, params)
    monkeypatch.setattr(enrichment_config, "_isolated_execute", refuse_together)
    # a fresh incident book: a condition already seen is only counted, so its sentence would not show here
    monkeypatch.setattr(enrichment_config, "_driver_error_incidents", {})
    caplog.set_level("INFO")
    counted = retroactive._count_enrichment_confirm(db, {"rule": "bkfl_rule"}, 200)
    incidents = [r.getMessage() for r in caplog.records if r.levelname == "ERROR" and "[Enrichment]" in r.getMessage()]
    assert incidents and all(m.startswith("[Enrichment] " + enrichment_config.SITE_CANDIDATE_PROBE_BATCH)
                             for m in incidents), incidents
    # the sweep's first page is one row, asked alone as ever - the other eleven of each view fell back
    assert "Batch -> key by key: 22 key(s) asked one at a time" in counted["detail"], counted["detail"]
    said = caplog.text
    assert enrichment_config.SITE_CANDIDATE_PROBE_BATCH in said
    assert enrichment_config.SITE_CANDIDATE_PROBE not in said, "the batch failure reads as the view failing"
    assert "batch -> key by key for 22 key(s) (every chip: 11, the chip: 11)" in said


def test_a_view_of_another_type_is_asked_key_by_key_and_answers_the_same(db, monkeypatch, tmp_path):
    """총괄 ff4eb2cf0 ②: no cast. A key holding the derived table's own value (a number, as the rows are read)
    is asked on the page; a key spelled as text against a number comparison fails the page's one statement,
    is asked key by key, answers the same, and the answer says how many keys fell back."""
    view = {"label": "counted", "limit": 5, "candidate_for": {"wafer_id": "wafer_id"},
            "query": "SELECT min(chip_id) AS wafer_id FROM bkfl_test_src WHERE equipment = :equipment "
                     "AND :chip_count >= 1"}
    write_rules(tmp_path, monkeypatch, {"bkfl_rule": dict(be.RULES_FILE["bkfl_rule"], reference_views=[view])})
    rule = _rule()
    for spelled, falls_back in ((3, False), ("3", True)):
        keyed = [dict(entry, keys=dict(entry["keys"], chip_count=spelled)) for entry in _queue(db, rule)]
        together = _confirm(db, rule, keyed, [])
        with monkeypatch.context() as each:
            each.setattr(enrichment_config, "LATERAL_DIALECTS", ())
            alone = _confirm(db, rule, keyed, [])
        fallbacks = together.pop("probe_batch_fallbacks", None)
        assert (fallbacks is not None) == falls_back, (spelled, fallbacks)
        assert together == alone and together["confirmed"] == 9, (spelled, together)
