# -*- coding: utf-8 -*-
"""인덱스는 «선언»에서 나온다 — 도메인 낱말이 코드에 없다 (S-94, 판정 237).

🔴 WHY THIS FILE EXISTS. An alignment view build runs one
`SELECT DISTINCT … FROM <source> WHERE <decision_key> = ? ORDER BY …` per job, and the
alignment mapper builds one view per job. Measured on this box: a Seq Scan removing
109,877 rows to keep 88, 21.96 ms, one thousand times per chain group - 23.8 s of a 44.9 s
group, the single largest thing the chain does.

⛔ AND THE FIX MUST NOT KNOW A DOMAIN WORD. `dt_job` appears in no product line: the
columns are `decision_key`, which is what the rule declares it keys on, so an installation
keying on something else gets an index on that instead with zero code changes. That is the
owner's definition of done ("두 줄로 말해진다: 이 규칙에 이 칸을 적으면 됩니다"), and it is
what these cases pin.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.models import (                                        # noqa: E402
    alignment_decision_key_index_ddl,
    map_key_index_ddl,
)


def test_the_columns_are_the_rules_declared_decision_key():
    name, ddl = alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "some_source", "decision_key": ["a", "b"]},
        {"kind": "table"})

    assert name == "idx_some_source_decision_key"
    assert '"a", "b"' in ddl, ddl
    assert 'ON "some_source"' in ddl
    assert "CONCURRENTLY" in ddl and "IF NOT EXISTS" in ddl


def test_a_view_gets_no_index_because_a_view_cannot_be_indexed():
    """The same refusal `map_key_index_ddl` already makes, and for the reason it records:
    without it `dt_log_transferable` failed on every boot and every config reload."""
    assert alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "v", "decision_key": ["a"]},
        {"kind": "view"}) == (None, None)


def test_a_rule_that_is_not_an_alignment_rule_asks_for_nothing():
    """⛔ THE COST BEING FIXED IS THE ALIGNMENT VIEW'S. An index for every enrichment rule
    would be a write cost on tables whose reads this never touches - the opposite of the
    standing rule about being careful with schema."""
    assert alignment_decision_key_index_ddl(
        {"source_table": "t", "decision_key": ["a"]}, {"kind": "table"}) == (None, None)


def test_a_rule_with_no_decision_key_asks_for_nothing():
    assert alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "t", "decision_key": []},
        {"kind": "table"}) == (None, None)


def test_the_map_key_builder_still_says_what_it_said():
    """⚠️ THE NEIGHBOUR, PINNED BECAUSE THIS ROUND MOVED ITS BUILD STEP. The CONCURRENTLY
    dance - including the invalid-leftover repair - was extracted so both ensures call one
    copy; the DDL each one asks for did not change, and nothing else covered that."""
    name, ddl = map_key_index_ddl("some_map", {"map_key_columns": ["k1", "k2"]})

    assert name == "idx_some_map_map_key"
    assert '"k1", "k2"' in ddl and 'ON "some_map"' in ddl
    assert map_key_index_ddl("v", {"kind": "view",
                                   "map_key_columns": ["k"]}) == (None, None)


def test_the_declared_rows_are_built_at_the_start_and_every_reload_by_the_one_door():
    """🔴 착지는 배선이 아니다. The map key, the decision key and the page order are rows of the one comparison
    (`derived_key_indexes`, 총괄 11-06 ㄷ) and the line's declared work - its start and every Reload - builds what is
    owed through `ensure_model_indexes`; nothing else builds them."""
    import inspect

    from database import models
    from runtime import maintenance_line

    body = inspect.getsource(maintenance_line._declared_work)
    assert "ensure_model_indexes_sync" in body, body[:400]
    assert "derived_key_indexes(tables)" in inspect.getsource(models.index_states)


def test_two_rules_over_one_table_ask_for_one_index():
    """🔴 A COUNT THAT IS NOT THE NUMBER OF THINGS THAT EXIST (깔끔 ①): two alignment rules over the same table and key
    name one index - one row; a rule over a table the catalogue does not hold names none."""
    from database import models

    rules = [{"params": {"alignment": True, "source_table": "t", "decision_key": ["a"]}},
             {"params": {"alignment": True, "source_table": "t", "decision_key": ["a"]}},
             {"params": {"alignment": True, "source_table": "u", "decision_key": ["a"]}}]
    rows = models.derived_key_indexes({"t": {"kind": "table"}}, rules=rules)
    assert [(table, name) for table, name, shape in rows if shape["purpose"] == "decision key"] == [
        ("t", "idx_t_decision_key")]


def test_every_caller_of_the_one_builder_hands_it_the_table_its_statement_builds_on(monkeypatch):
    """Each caller of `_ensure_one_index` passes `table=` the very table its statement is ON - the wait before the
    build asks who holds it and a built one is noted for the round's ANALYZE; a wrong or missing one makes neither
    happen and nothing says so (C 11-06: decision-key's `table=None` survived a count of keywords). Measured on the
    value: each caller is run against a builder that records what it was handed."""
    import contextlib
    import re

    from chain import ingestion_worker as worker
    from chain import join_key_index as vjc
    from chain import unique_key
    from database import models
    from migrations import add_business_key_unique_index as uq

    handed = []

    def record(engine, name, statement, what, say=print, table=None, **_kw):
        handed.append((what, table, re.search(r' ON\s+"?([^"\s(]+)', statement).group(1)))
        return models.INDEX_PRESENT

    class Db:
        def get_bind(self):
            return None

        def close(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(models, "_ensure_one_index", record)
    for table, name, shape in models.derived_key_indexes(       # the declared rows - built as every declared one is
            {"t_dyn": {"kind": "table"}, "t_dec": {"kind": "table"},
             "t_map": {"kind": "table", "map_key_columns": ["x"]}},
            rules=[{"params": {"alignment": True, "source_table": " t_dec ", "decision_key": ["a"]}}]):  # spaced
        row = dict(shape, name=name, table=table)
        models._build_one(None, models.table_index_ddl(row), row, lambda line: None, None)
    with contextlib.suppress(Exception):                    # what it says after the build is not this test's
        worker._ensure_human_claims_index_sync(lambda: Db())
    worker._build_unique_index_waiting(None, uq, "t_bk", "uq_bk_t_bk")
    unique_key._build(Db(), "t_join", "uq_t_join", vjc.required_index_ddl("t_join", ["k"]), "join unique")
    models._build_one(None, 'CREATE INDEX CONCURRENTLY IF NOT EXISTS "n_decl" ON "t_decl" ("a")',
                      {"name": "n_decl", "table": "t_decl"}, lambda line: None, None)    # declared · automatic

    assert {what for what, _t, _on in handed} == {"human-claims", "business-key unique", "join unique",
                                                  "declared"}, handed
    assert {on for what, _t, on in handed if what == "declared"} >= {"t_dyn", "t_dec", "t_map"}, handed
    assert [(what, table, on) for what, table, on in handed if table != on] == [], handed
