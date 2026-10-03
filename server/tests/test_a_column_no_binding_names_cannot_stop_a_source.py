# -*- coding: utf-8 -*-
"""총괄 164553a6f: the two stops 97101fd2e opened, closed. The read brings every column of the
relation, and a column no binding names reaches no atom (판정 201) - so neither its TYPE nor its
ABSENCE may stop a source.

  a row unit's ordering key        the named columns and row_id only - a NUMERIC, DATE or naive
                                   TIMESTAMP cell elsewhere leaves the atoms as they were
  a column only table_config has   not read, named once; the source goes on
  a binding naming that column     the read still stops on it, as it always did
"""
import copy
import datetime as dt
import decimal
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                              # noqa: E402
from ledger.event_frame import named_columns                             # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.runtime_v2 import last_cursor, preview_cursor_batch          # noqa: E402
from ledger.setup import LedgerSetup, preview_selected_cursor_batch      # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,                  # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from support import hold_world as hw                                     # noqa: E402
from support.read_frame import as_read                                   # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
ROW_SOURCE = "wafer_process_recipe"


@pytest.fixture(scope="module", name="snapshot")
def fixture_snapshot():
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    return compile_setup_snapshot(require_ready_bundle(validate_bundle(document, catalog=catalog)),
                                  trusted_implementations(), catalog=catalog)


def _said(snapshot, frame):
    plan = snapshot.source_plans[ROW_SOURCE]
    preview = preview_cursor_batch(snapshot, ROW_SOURCE, frame, last_cursor(plan, frame),
                                   role_mapper_registry(), known_registrations=())
    return sorted(json.dumps(a, sort_keys=True, default=str) for a in preview.candidate_semantics)


def test_a_cell_with_no_canonical_form_in_an_unnamed_column_moves_no_atom(snapshot):
    plan = snapshot.source_plans[ROW_SOURCE]
    assert plan.driver.unit == "row", "the ordering key under test is the row unit's"
    rows = [{"row_id": "P%d" % i, "wafer_id": "W%d" % i, "recipe_id": "R1", "step": "S1",
             "eventtime": "2026-09-30 12:00:00", "mat_type": ""} for i in (1, 2, 3)]
    plain = as_read(plan, rows)
    unnamed = [c for c in plan.relation_columns if c not in named_columns(plan)]
    assert len(unnamed) >= 3, unnamed
    odd = plain.copy()
    for column, value in zip(unnamed, (decimal.Decimal("1.50"), dt.date(2026, 9, 30),
                                       dt.datetime(2026, 9, 30, 10))):
        odd[column] = [value] * len(odd)

    expected = _said(snapshot, plain)
    assert expected, "canary: the plain rows are said"
    assert _said(snapshot, odd) == expected


# ------------------------------------------------------------------- PostgreSQL, the read


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(backfill, "_SKIPPED_SAID", set())
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _setup_with(world, source, extra_columns):
    """The world's declaration over a catalogue whose official table names columns the table
    does not have."""
    catalog = copy.deepcopy(dict(world["setup"].catalog))
    catalog[hw.OFFICIAL] = copy.deepcopy(dict(catalog[hw.OFFICIAL]))
    catalog[hw.OFFICIAL]["columns"] = {**catalog[hw.OFFICIAL]["columns"], **extra_columns}
    doc = hw.sample("ledger_config.json.sample")
    doc["sources"] = {hw.SOURCE: source}
    bundle = require_ready_bundle(validate_bundle(doc, catalog=catalog))
    return LedgerSetup(config_root=world["setup"].config_root, bundle=bundle,
                       snapshot=compile_setup_snapshot(bundle, trusted_implementations(),
                                                       catalog=catalog),
                       mappers=role_mapper_registry(), catalog=catalog)


def _first_page(world, setup):
    plan, scoped = backfill.rescope_scope(setup, hw.SOURCE, None, (), whole_source=True)
    frame = next(backfill._scope_pages(world["engine"], plan, scoped, 100))
    preview = preview_selected_cursor_batch(setup, hw.SOURCE, frame, last_cursor(plan, frame),
                                            known_registrations=())
    return frame, sorted(json.dumps(a, sort_keys=True, default=str)
                         for a in preview.candidate_semantics)


pg = pytest.mark.pg


@pg
def test_a_column_only_table_config_names_is_not_read_and_said_once(world, caplog):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    _, expected = _first_page(world, world["setup"])
    assert expected, "canary: the official row is said"
    ghosted = _setup_with(world, copy.deepcopy(hw.LEDGER_SOURCE), {"ghost": "string"})
    assert "ghost" in ghosted.snapshot.source_plans[hw.SOURCE].relation_columns

    with caplog.at_level(logging.WARNING, logger="Ledger.Backfill"):
        frame, said = _first_page(world, ghosted)
        _first_page(world, ghosted)

    assert "ghost" not in frame.columns and "netdie" in frame.columns
    assert said == expected
    lines = [r.getMessage() for r in caplog.records if "ghost" in r.getMessage()]
    assert len(lines) == 1, lines
    assert hw.OFFICIAL in lines[0] and "not read" in lines[0]


@pg
def test_a_binding_naming_a_column_the_table_lacks_still_stops_the_read(world):
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    source["bind"]["mappings"]["counted"]["bind"]["value"]["column"] = "ghost"
    ghosted = _setup_with(world, source, {"ghost": "number"})
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    with pytest.raises(Exception, match="ghost"):
        _first_page(world, ghosted)
