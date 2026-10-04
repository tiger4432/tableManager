# -*- coding: utf-8 -*-
"""총괄 5fec118bb ①: a backfill of a new source on a table translated every source reading that
table - its rows are queued by TABLE as CREATEs, and a CREATE is translated without withdrawing
(판정 166). For a source that already had those rows that wrote its facts again, and an atom's
version is the whole declaration's hash, so after any declaration edit they did not dedupe:
the same fact twice, neither superseding the other.

  the default declares a second source on wafer_process after the first was translated
  backfill of the new source      the first source's atoms: as many as before
  the first source translated again (whole source, and an edit followed live): as many
"""
import copy
import json
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from conftest import PG_TEST_SCHEMA                                 # noqa: E402
from ledger import backfill, schema                                 # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, _follow, _sample, _seed, _write, fixture_config, fixture_world)

pytestmark = pytest.mark.pg
NEW = "wafer_tool"
#: RUN.md's count, word for word: per source, the atoms that say a fact another atom of that
#: source already says about the same row - neither superseding the other.
EXTRA_SQL = """
SELECT source_who, sum(n - 1) AS extra FROM (
  SELECT source_who, count(*) AS n FROM {ledger} WHERE supersedes IS NULL
   GROUP BY source_who, source_raw_ref, occurred_at, predicate, subject_type, subject_keys,
            coalesce(object_payload, '{{}}'::jsonb)
  HAVING count(*) > 1) d GROUP BY source_who
"""


@pytest.fixture(autouse=True)
def _the_second_source_leaves_nothing(world):
    """The worlds fixture cleans the sample's two sources; this file's own goes by name."""
    yield
    with world["engine"].begin() as conn:
        for table in (schema.LEDGER_TABLE, schema.ROW_REF_TABLE):
            conn.execute(text("DELETE FROM %s WHERE source_who = :s" % table), {"s": NEW})


def _declare_a_second_source():
    document = _sample("ledger_config.json.sample")
    document["entities"]["tool@1"] = {"keys": ["tool"]}
    document["vocabulary"]["processed_on@1"] = {
        "status": "active", "subjects": ["wafer@1"],
        "object": {"kind": "entity_ref", "types": ["tool@1"],
                   "qualifiers": {"required": [], "optional": []}}}
    source = copy.deepcopy(document["sources"][CHANGED])
    source["bind"]["mappings"] = {"wafer-on-tool": {"predicate": "processed_on@1", "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}},
        "target": {"kind": "entity", "entity_type": "tool@1",
                   "keys": {"tool": {"kind": "column", "column": "step"}}}}}}
    document["sources"][NEW] = source
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w",
              encoding="utf-8") as fh:
        json.dump(document, fh)


def _atoms(world, source):
    with world["engine"].connect() as conn:
        return conn.execute(text("SELECT count(*) FROM %s WHERE source_who = :s"
                                 % schema.LEDGER_TABLE), {"s": source}).scalar()


def _extra(world):
    with world["engine"].connect() as conn:
        return {who: int(n) for who, n in conn.execute(text(
            EXTRA_SQL.format(ledger=schema.LEDGER_TABLE)))}


def test_a_backfill_of_a_new_source_writes_no_other_sources_fact_twice(world):
    _seed(world)
    before = _atoms(world, CHANGED)
    assert before, "canary: the first source was translated"
    _declare_a_second_source()

    backfill.run(world["engine"], source=NEW)
    assert _atoms(world, NEW), "canary: the new source was translated"
    assert _atoms(world, CHANGED) == before

    backfill.rescope(world["engine"], load_setup(schema.world_names().declaration_root), CHANGED,
                     None, None, apply=True, page_rows=backfill.RESCOPE_PAGE_ROWS,
                     whole_source=True)
    assert _atoms(world, CHANGED) == before

    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-2"}], key="P1")
    _follow(world)
    assert _atoms(world, CHANGED) == before


def test_the_whole_source_redo_takes_back_a_fact_written_twice(world):
    """What RUN.md tells an operator to run on a ledger the old backfill left doubled: the same
    fact twice under two versions folds back to one."""
    from ledger import followup

    _seed(world)
    before = _atoms(world, CHANGED)
    _declare_a_second_source()                                   # the declaration moved
    with world["engine"].connect() as conn:
        rows = [r[0] for r in conn.execute(text('SELECT row_id FROM "%s".wafer_process'
                                                % PG_TEST_SCHEMA))]
    followup.enqueue("wafer_process", rows, "CREATE")            # the old backfill's shape
    while followup.drain_once(world["engine"], load_setup(schema.world_names().declaration_root)):
        pass
    doubled = _atoms(world, CHANGED)
    assert doubled == 2 * before, "canary: the fact was written twice"
    assert _extra(world) == {CHANGED: before}

    backfill.rescope(world["engine"], load_setup(schema.world_names().declaration_root), CHANGED,
                     None, None, apply=True, page_rows=backfill.RESCOPE_PAGE_ROWS,
                     whole_source=True)
    assert _atoms(world, CHANGED) == before and _extra(world) == {}
