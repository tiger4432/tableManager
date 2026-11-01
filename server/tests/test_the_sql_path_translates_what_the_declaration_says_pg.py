"""Lead 10-31 ② stage 1: the SQL path (`ledger.sql_translate`) and the Python path translate a page into the same
atoms - and both give the atoms written here BY HAND from the declaration and the rows, so the two cannot agree on a
wrong answer unseen (the Python path's front half is now the same functions; a test of «same as each other» alone
would pass if both went wrong together).

  the board   hold_world's official table on PostgreSQL, the ledger source re-declared per cell
  the cells   row (exclude_when blank) · when · constant value · read group x map row · a blank entity key ·
              the same with allow_null · a time read by a declared format · an entity attribute (not a time)
  each cell   SQL atoms == Python atoms == the hand-written atoms; refusals counted alike; the cells both paths read
              are the same values (a time column reaches the format as the text the Python path reads)
  not here    two tables naming one entity - the box board (die from inspection_run and dt_transfer_log, every
              page, both paths alike); worlds - the translation asks no world (a world only names the ledger tables)
"""
import copy
import json

import pytest

from ledger import backfill, runtime_v2, sql_translate
from ledger.setup import preview_selected_cursor_batch
from support import hold_world as hw

pytestmark = pytest.mark.pg

SUBJECT = {"kind": "entity", "entity_type": "dtjob@1", "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}}
BLANK = {"dt_job": None, "dt_x": 3, "dt_y": 1, "netdie": 9, "hold": "agreed"}
ROWS = [{"dt_job": "J1", "dt_x": 1, "dt_y": 1, "netdie": 7, "hold": "agreed"},
        {"dt_job": "J1", "dt_x": 2, "dt_y": 1, "netdie": 5, "hold": "other"},
        {"dt_job": "J2", "dt_x": 1, "dt_y": 1, "netdie": 3, "hold": None}]


def _source(read=None, value=None, when=None, unit=None, entities=None):
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    if entities is not None:
        source["bind"]["entities"] = entities
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
    # a row naming no job: its molecule is refused, the others land
    "blank key": (_source(), ROWS + [BLANK], {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
    # the same row, the entity allowing a null key: it lands keyed by nothing
    "allow_null": (_source(), ROWS + [BLANK],
                   {("J1", "has_netdie", 7), ("J1", "has_netdie", 5), (None, "has_netdie", 9)}),
    # the event time read from a text cell by a declared format, on the declared zone
    "time format": (_source(read={"occurred_at": {"column": "note", "timezone": "Asia/Seoul",
                                                  "format": "%Y/%m/%d %H:%M"},
                                  "exclude_when": [{"column": "hold", "blank": True}]}),
                    [dict(row, note="2026/10/01 09:30") for row in ROWS],
                    {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
    # an attribute of the job, read from a cell - carried by the job's registration
    "attribute": (_source(entities={"dtjob@1": {"attributes": {"dt_eqp": {"kind": "column", "column": "note"}}}}),
                  [dict(row, note="E1") for row in ROWS],
                  {("J1", "has_netdie", 7), ("J1", "has_netdie", 5), ("J1", "register", (("dt_eqp", "E1"),))}),
}
#: the time the «time format» cell's atoms carry, by hand: 09:30 on Asia/Seoul
FORMAT_TIME = "2026-10-01T09:30:00+09:00"
ALLOW_NULL = {"allow_null"}


#: ⚠️ OPEN (asked of the lead 11-01): both paths refuse the allow_null row - `event_frame._read_molecule` refuses a blank
#: entity cell without asking allow_null, and `blank_entity_cells` never excuses one - so the declaration's «a null key
#: is allowed» does not reach `roleframe`'s allow_null branch. Strict: the day that is decided and mended, this reds.
PARAMS = [pytest.param(cell, id=cell, marks=pytest.mark.xfail(strict=True, reason="allow_null blank key refused"))
          if cell in ALLOW_NULL else pytest.param(cell, id=cell) for cell in CELLS]


@pytest.fixture(name="world", params=PARAMS)
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    source, rows, expected = CELLS[request.param]
    monkeypatch.setattr(hw, "LEDGER_SOURCE", source)
    if request.param in ALLOW_NULL:
        sample = hw.sample

        def allowing(name):
            doc = sample(name)
            if name.startswith("ledger_config"):
                doc["entities"]["dtjob@1"]["allow_null"] = True
            return doc
        monkeypatch.setattr(hw, "sample", allowing)
    for world in hw.build(pg_engine, monkeypatch, tmp_path):
        _write(world, rows)
        yield dict(world, expected=expected, cell=request.param)


def _write(world, rows):
    import event_constants
    from database import crud, schemas
    from database.context import channel

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(row), source_name="user", updated_by="t") for row in rows]))
        world["db"].commit()


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
    named = sorted(set(narrow[0]) if narrow else ())
    cells = ({column: [row[column] for row in full] for column in named},
             {column: [row[column] for row in narrow] for column in named})
    return plan, preview, results, context, cells


def _said(records):
    out = set()
    for record in map(json.loads, records):
        payload = record["object_payload"] or {}
        if record["predicate"].startswith("has_netdie"):
            out.add((record["subject_keys"]["dt_job"], "has_netdie", payload.get("value")))
        elif record["predicate"].startswith("register") and payload.get("qualifiers"):
            out.add((record["subject_keys"]["dt_job"], "register", tuple(sorted(payload["qualifiers"].items()))))
    return out


def test_the_sql_path_gives_the_atoms_the_declaration_says(world):
    plan, preview, results, context, (full, narrow) = _both(world)
    python, sql = (sorted(sql_translate.atom_records(plan, preview.event_results)),
                   sorted(sql_translate.atom_records(plan, results)))

    assert narrow == full, "the SQL read hands every named column as the Python read does - a time text included"
    if world["cell"] == "time format":
        assert {json.loads(r)["occurred_at"] for r in sql} == {FORMAT_TIME}
    if world["cell"] == "blank key":
        assert len(context.refusals) == 1, "the blank-keyed row refuses its molecule, counted"

    assert _said(sql) == world["expected"], "the SQL path, against the hand-written atoms"
    assert _said(python) == world["expected"], "the Python path, against the same"
    assert sql == python, "every field of every atom (ids, raw refs, times, basis) the same on both paths"
    assert [r.reason for r in context.refusals] == [r.reason for r in preview.refusals]
