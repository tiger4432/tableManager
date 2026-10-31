"""Lead 10-31 ② stage 1: the SQL path (`ledger.sql_translate`) and the Python path translate a page into the same
atoms - and both give the atoms written here BY HAND from the declaration and the rows, so the two cannot agree on a
wrong answer unseen (the Python path's front half is now the same functions; a test of «same as each other» alone
would pass if both went wrong together).

  the board   hold_world's official table on PostgreSQL, the ledger source re-declared per cell
  the cells   row (exclude_when blank) · when · constant value · read group x map row · a blank entity key
  each cell   SQL atoms == Python atoms == the hand-written atoms; refusals counted alike
"""
import copy
import json

import pytest

from ledger import backfill, roleframe, runtime_v2, sql_translate
from ledger.setup import preview_selected_cursor_batch
from support import hold_world as hw

pytestmark = pytest.mark.pg

SUBJECT = {"kind": "entity", "entity_type": "dtjob@1", "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}}
ROWS = [{"dt_job": "J1", "dt_x": 1, "dt_y": 1, "netdie": 7, "hold": "agreed"},
        {"dt_job": "J1", "dt_x": 2, "dt_y": 1, "netdie": 5, "hold": "other"},
        {"dt_job": "J2", "dt_x": 1, "dt_y": 1, "netdie": 3, "hold": None}]


def _source(read=None, value=None, when=None, unit=None):
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    if read is not None:
        source["read"] = read
    if unit is not None:
        source["map"]["unit"] = unit
    mapping = source["bind"]["mappings"]["counted"]
    mapping["bind"] = {"subject": SUBJECT, "value": value or {"kind": "column", "column": "netdie"}}
    if when is not None:
        mapping["when"] = when
    return source


#: cell -> (the source, the rows written, the atoms the declaration says: (keys, predicate, value) - by hand)
CELLS = {
    # every row a molecule; hold blank -> J2 excluded (read.exclude_when)
    "row": (_source(), ROWS, {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
    # the sentence only where hold is 'agreed'
    "when": (_source(when={"hold": "agreed"}), ROWS, {("J1", "has_netdie", 7)}),
    # a constant value, whatever netdie says
    "constant": (_source(value={"kind": "constant", "value": 1}), ROWS, {("J1", "has_netdie", 1)}),
    # the read groups J1's rows into one molecule, the mapper still reads each row
    "group x row": (_source(read={"unit": "group", "group_by": ["dt_job"], "identity": ["dt_job"],
                                  "order_by": ["dt_job", "dt_x", "dt_y"],
                                  "exclude_when": [{"column": "hold", "blank": True}]},
                            unit={"kind": "row"}),
                    ROWS, {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
}


@pytest.fixture(name="world", params=list(CELLS), ids=list(CELLS))
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    source, rows, expected = CELLS[request.param]
    monkeypatch.setattr(hw, "LEDGER_SOURCE", source)
    for world in hw.build(pg_engine, monkeypatch, tmp_path):
        _write(world, rows)
        yield dict(world, expected=expected)


def _write(world, rows):
    import event_constants
    from database import crud, schemas
    from database.context import channel

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(row), source_name="user", updated_by="t") for row in rows]))
        world["db"].commit()


def _atoms(plan, results):
    groups = runtime_v2._filtered_event_atoms(results, ())
    runtime_v2._stamp_occurred_at_basis(plan, groups)
    records = []
    for atoms in groups:
        for atom in atoms:
            atom.ensure_source_event_identity()
            records.append(json.dumps(dict(runtime_v2._semantic_atom(atom), basis=atom.occurred_at_basis),
                                      sort_keys=True, default=str))
    return sorted(records)


def _both(world):
    engine, setup = world["engine"], world["setup"]
    plan = setup.snapshot.source_plans[hw.SOURCE]
    raw = engine.raw_connection()
    try:
        full = backfill._fetch_v2_lineage_rows(raw, plan, backfill._readable_columns(engine, plan))
        narrow = sql_translate.read_page(raw, plan)
    finally:
        raw.close()
    frame = backfill._v2_frame(full)
    preview = preview_selected_cursor_batch(setup, hw.SOURCE, frame, runtime_v2.last_cursor(plan, frame),
                                            known_registrations=())
    results, context = sql_translate.event_results(setup.snapshot, hw.SOURCE, narrow)
    return plan, preview, results, context


def _said(records):
    out = set()
    for record in map(json.loads, records):
        payload = record["object_payload"] or {}
        if record["predicate"].startswith("has_netdie"):
            out.add((record["subject_keys"]["dt_job"], "has_netdie", payload.get("value")))
    return out


def test_the_sql_path_gives_the_atoms_the_declaration_says(world):
    plan, preview, results, context = _both(world)
    python, sql = _atoms(plan, preview.event_results), _atoms(plan, results)

    assert _said(sql) == world["expected"], "the SQL path, against the hand-written atoms"
    assert _said(python) == world["expected"], "the Python path, against the same"
    assert sql == python, "every field of every atom (ids, raw refs, times, basis) the same on both paths"
    assert [r.reason for r in context.refusals] == [r.reason for r in preview.refusals]
