# -*- coding: utf-8 -*-
"""총괄 e027f669d (소유자 10-09 「거두기 했는데 transfer 원자 남아있음 · 예전에 dt_log 에서 했던 버전 거임」 ->
「거두기는 ㄱ」): `--whole-source` takes back the atoms a source wrote from a table its declaration no
longer reads, and every atom of a name the declaration no longer has - aimed from the ledger's own
refs, so an atom with no row-index line is reached too.

  a source moved to another table      the old table's atoms go, the new table's are made
  a renamed source                     the old name's atoms all go, the new name's stay
  atoms with no index line             reached all the same
  a retired source                     refused, its atoms stay
  another source on the same rows      its atoms and index lines stay
  preview = run, again = 0             and a page is a stop's place
"""
import copy
import json
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from admin import retroactive                                       # noqa: E402
from ledger import backfill, schema                                 # noqa: E402
from ledger.roleframe import claim_source_row_refs                  # noqa: E402
from ledger.setup import LedgerSetupError, load_setup               # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _sample, _seed, fixture_config, fixture_world)

pytestmark = pytest.mark.pg
RENAMED, SECOND = "wafer_process_recipe_v2", "wafer_tool"
OLD, NEW = "wafer_process", "lot_slot_wafer"


@pytest.fixture(autouse=True)
def _this_files_sources_leave_nothing(world):
    yield
    with world["engine"].begin() as conn:
        for table in (schema.LEDGER_TABLE, schema.ROW_REF_TABLE):
            conn.execute(text("DELETE FROM %s WHERE source_who IN (:a, :b)" % table),
                         {"a": RENAMED, "b": SECOND})


def _declare(document):
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w",
              encoding="utf-8") as fh:
        json.dump(document, fh)


def _setup():
    return load_setup(schema.world_names().declaration_root)


def _moved(document=None):
    """CHANGED now reads the table KEPT reads - its old table is one the declaration no longer reads."""
    document = document or _sample("ledger_config.json.sample")
    document["sources"][CHANGED] = copy.deepcopy(document["sources"][KEPT])
    return document


def _with_second_source(document):
    """A second source on CHANGED's old table - the same rows, another speaker."""
    document["entities"]["tool@1"] = {"keys": ["tool"]}
    document["vocabulary"]["processed_on@1"] = {
        "status": "active", "subjects": ["wafer@1"],
        "object": {"kind": "entity_ref", "types": ["tool@1"], "qualifiers": {"required": [], "optional": []}}}
    source = copy.deepcopy(_sample("ledger_config.json.sample")["sources"][CHANGED])
    source["bind"]["mappings"] = {"wafer-on-tool": {"predicate": "processed_on@1", "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}},
        "target": {"kind": "entity", "entity_type": "tool@1",
                   "keys": {"tool": {"kind": "column", "column": "step"}}}}}}
    document["sources"][SECOND] = source
    return document


def _atoms(world, source):
    """{table: atoms} of this source, by the tables its refs name."""
    with world["engine"].connect() as conn:
        rows = conn.execute(text("SELECT source_raw_ref, count(*) FROM %s WHERE source_who = :s GROUP BY 1"
                                 % schema.LEDGER_TABLE), {"s": source}).fetchall()
    out = {}
    for ref, n in rows:
        for table in {item.split(":", 1)[0] for item in claim_source_row_refs(ref) if ":" in item}:
            out[table] = out.get(table, 0) + int(n)
    return out


def _lines(world, source):
    with world["engine"].connect() as conn:
        return {table: int(n) for table, n in conn.execute(text(
            "SELECT relation, count(*) FROM %s WHERE source_who = :s GROUP BY 1" % schema.ROW_REF_TABLE),
            {"s": source})}


def _whole(world, source, apply=True):
    return backfill.rescope(world["engine"], _setup(), source, None, None, apply=apply,
                            page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)


def test_a_source_moved_to_another_table_takes_back_the_old_tables_atoms(world):
    _seed(world)
    assert _atoms(world, CHANGED).get(OLD) and _lines(world, CHANGED).get(OLD), "canary: atoms from the old table"
    _declare(_moved())
    done = _whole(world, CHANGED)
    after = _atoms(world, CHANGED)
    assert OLD not in after and after.get(NEW), after
    assert OLD not in _lines(world, CHANGED) and done["stale_forgotten"] > 0
    assert done["stale_withdrawn"] > 0 and done["stale_pages"] == 1


def test_a_renamed_source_takes_back_every_atom_of_the_old_name(world):
    _seed(world)
    document = _sample("ledger_config.json.sample")
    document["sources"][RENAMED] = document["sources"].pop(CHANGED)
    _declare(document)
    backfill.run(world["engine"], source=RENAMED)
    renamed = _atoms(world, RENAMED)
    assert renamed and _atoms(world, CHANGED), "canary: both names hold atoms"
    params = retroactive.validate("ledger_rescope", {"source": CHANGED, "whole_source": True})
    said = retroactive.OPERATIONS["ledger_rescope"]["count"](world["db"], params, 1000)
    assert said["affected"] == sum(_atoms(world, CHANGED).values()) and "is not in today's declaration" in said["detail"]
    done = _whole(world, CHANGED)
    assert _atoms(world, CHANGED) == {} and _lines(world, CHANGED) == {}
    assert _atoms(world, RENAMED) == renamed and done["stale_withdrawn"] == said["affected"]


def test_an_atom_with_no_index_line_is_reached(world):
    """09-08 and before an atom could be written without a row-index line - made here by deleting them."""
    _seed(world)
    with world["engine"].begin() as conn:
        conn.execute(text("DELETE FROM %s WHERE source_who = :s" % schema.ROW_REF_TABLE), {"s": CHANGED})
    assert _atoms(world, CHANGED).get(OLD) and not _lines(world, CHANGED), "canary: atoms, no lines"
    _declare(_moved())
    _whole(world, CHANGED)
    assert OLD not in _atoms(world, CHANGED)


def test_a_retired_source_is_refused_and_its_atoms_stay(world):
    _seed(world)
    before = _atoms(world, CHANGED)
    document = _moved()
    document["sources"][CHANGED]["status"] = "retired"
    _declare(document)
    for apply in (False, True):
        with pytest.raises(LedgerSetupError) as refused:
            _whole(world, CHANGED, apply=apply)
        assert refused.value.code == "source_retired"
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.validate("ledger_rescope", {"source": CHANGED, "whole_source": True})
    assert _atoms(world, CHANGED) == before


def test_another_source_on_the_same_rows_keeps_its_atoms_and_lines(world):
    _seed(world)
    _declare(_with_second_source(_sample("ledger_config.json.sample")))
    backfill.run(world["engine"], source=SECOND)
    second, lines = _atoms(world, SECOND), _lines(world, SECOND)
    assert second.get(OLD) and lines.get(OLD), "canary: the second source speaks for the old table's rows"
    _declare(_moved(_with_second_source(_sample("ledger_config.json.sample"))))
    _whole(world, CHANGED)
    assert OLD not in _atoms(world, CHANGED)
    assert _atoms(world, SECOND) == second and _lines(world, SECOND) == lines


def test_the_preview_says_what_the_run_takes_and_a_second_run_takes_nothing(world, monkeypatch):
    _seed(world)
    stale = _atoms(world, CHANGED)[OLD]
    _declare(_moved())
    preview = _whole(world, CHANGED, apply=False)
    assert (preview["stale_atoms"], preview["stale_withdrawn"]) == (stale, 0)
    assert sum(preview["stale_tables"][OLD].values()) == stale and _atoms(world, CHANGED)[OLD] == stale
    monkeypatch.setattr(backfill, "STALE_PAGE_REFS", 1)                   # a page a ref
    done = _whole(world, CHANGED)
    assert done["stale_withdrawn"] == stale and done["stale_pages"] == preview["stale_refs"]
    again = _whole(world, CHANGED, apply=False)
    assert (again["stale_atoms"], _whole(world, CHANGED)["stale_withdrawn"]) == (0, 0)
