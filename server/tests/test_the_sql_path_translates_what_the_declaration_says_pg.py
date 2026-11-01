"""Lead 10-31 ② stage 1: the SQL path (`ledger.sql_translate`) and the Python path translate a page into the same
atoms - and both give the atoms written here BY HAND from the declaration and the rows, so the two cannot agree on a
wrong answer unseen (the Python path's front half is now the same functions; a test of «same as each other» alone
would pass if both went wrong together).

  the board   hold_world's official table on PostgreSQL, the ledger source re-declared per cell
  the cells   row (exclude_when blank) · when · constant value · read group x map row · a blank entity key ·
              the same with allow_null · a group one row of which leaves the key blank · a time read by a declared
              format · an entity attribute (not a time)
  each cell   SQL atoms == Python atoms == the hand-written atoms; refusals and excluded rows counted alike; the cells
              both paths read are the same values (a time column reaches the format as the text the Python path reads)
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
    # a row naming no job is taken out, counted «blank key dt_job» - the others land (owner 11-01 «빈키행은 무시»)
    "blank key": (_source(), ROWS + [BLANK], {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
    # the same row, the entity writing `allow_null` (read by nothing since 11-01): the same atoms
    "allow_null": (_source(), ROWS + [BLANK], {("J1", "has_netdie", 7), ("J1", "has_netdie", 5)}),
    # a group (dt_x) one row of which names no job: that row is taken out, the group says the rest
    "group, one blank": (_source(read={"unit": "group", "group_by": ["dt_x"], "identity": ["dt_x"],
                                       "order_by": ["dt_x", "dt_job", "dt_y"],
                                       "exclude_when": [{"column": "hold", "blank": True}]}),
                         ROWS + [dict(BLANK, hold="agreed"),
                                 {"dt_job": "J3", "dt_x": 3, "dt_y": 2, "netdie": 4, "hold": "agreed"}],
                         {("J1", "has_netdie", 7), ("J1", "has_netdie", 5), ("J3", "has_netdie", 4)}),
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
#: the rows each cell's read takes out, by cause (`event_frame.excluded_note`) - by hand
EXCLUDED = {"blank key": {"exclude_when": 1, "blank key dt_job": 1},
            "allow_null": {"exclude_when": 1, "blank key dt_job": 1},
            "group, one blank": {"exclude_when": 1, "blank key dt_job": 1}}


@pytest.fixture(name="world", params=list(CELLS))
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
                                            known_registrations=(), translate="python")
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


def setup_notes(world):
    from ledger import setup as ledger_setup

    return ledger_setup._unread_entity_cells(hw.sample("ledger_config.json.sample")["entities"])


def test_the_sql_path_gives_the_atoms_the_declaration_says(world):
    plan, preview, results, context, (full, narrow) = _both(world)
    python, sql = (sorted(sql_translate.atom_records(plan, preview.event_results)),
                   sorted(sql_translate.atom_records(plan, results)))

    assert narrow == full, "the SQL read hands every named column as the Python read does - a time text included"
    if world["cell"] == "time format":
        assert {json.loads(r)["occurred_at"] for r in sql} == {FORMAT_TIME}
    assert context.refusals == [] and preview.refusals == (), "a blank key refuses nothing (owner 11-01)"
    assert context.excluded_rows == preview.excluded_rows == EXCLUDED.get(world["cell"], {"exclude_when": 1})
    if world["cell"] in ALLOW_NULL:
        assert setup_notes(world) == ["ledger_config: entities.dtjob@1 cell this product does not read — allow_null."
                                      " A row whose key is blank is excluded."]

    assert _said(sql) == world["expected"], "the SQL path, against the hand-written atoms"
    assert _said(python) == world["expected"], "the Python path, against the same"
    assert sql == python, "every field of every atom (ids, raw refs, times, basis) the same on both paths"
    assert [r.reason for r in context.refusals] == [r.reason for r in preview.refusals]


def test_the_shadow_compares_the_excluded_rows_by_cause_page_by_page(world):
    said = sql_translate.shadow_source(world["engine"], world["setup"], hw.SOURCE, page_rows=2)
    assert said["pages"] > 1, said
    assert said["excluded"]["python"] == said["excluded"]["sql"] and said["excluded"]["sql"].get("exclude_when"), said
    assert said["excluded_pages_differ"] == 0 and not sql_translate.differs(said), said
    assert sql_translate.differs(dict(said, excluded_pages_differ=1)), "a page whose causes differ is DIFFERENT"
    assert sql_translate.differs(dict(said, refused={"python": 1, "sql": 0})), "so are refusals that differ"


def test_the_switch_parts_the_two_paths_at_one_seat_and_both_answer_alike(world, monkeypatch):
    import ingestion.settings

    engine, setup = world["engine"], world["setup"]
    plan = setup.snapshot.source_plans[hw.SOURCE]
    raw = engine.raw_connection()
    try:
        frame = backfill._v2_frame(backfill._fetch_v2_lineage_rows(raw, plan, backfill._readable_columns(engine, plan)))
    finally:
        raw.close()
    calls = {"sql": 0, "python": 0}
    cells_results, dry_run = sql_translate.cells_results, runtime_v2.dry_run_event_frame

    def counted(name, fn):
        def wrapper(*a, **k):
            calls[name] += 1
            return fn(*a, **k)
        return wrapper
    monkeypatch.setattr(sql_translate, "cells_results", counted("sql", cells_results))
    monkeypatch.setattr(runtime_v2, "dry_run_event_frame", counted("python", dry_run))
    previews = {}
    for setting in ({}, {"ledger_translate": "python"}):
        monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda s=setting: dict(s))
        before = dict(calls)
        previews[setting.get("ledger_translate", "sql")] = preview_selected_cursor_batch(
            setup, hw.SOURCE, frame, runtime_v2.last_cursor(plan, frame), known_registrations=())
        took = {name: calls[name] - before[name] for name in calls}
        assert sql_translate.translate_path(plan) == setting.get("ledger_translate", "sql")
        assert (took["sql"] > 0) == (not setting) and (took["python"] > 0) == bool(setting), (setting, took)
    sql, python = previews["sql"], previews["python"]
    assert sql.candidate_semantics == python.candidate_semantics and sql.candidate_semantics
    assert sql.row_refs == python.row_refs and sql.row_refs, "the withdrawal's index lines, alike"
    assert sql.excluded_rows == python.excluded_rows and sql.refusals == python.refusals


def test_the_line_says_the_path_each_source_goes_by_a_code_mapper_by_python(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace

    import ingestion.settings

    def plan(source, mapper):
        return SimpleNamespace(source_id=source, driver=SimpleNamespace(mapper=SimpleNamespace(
            implementation=SimpleNamespace(implementation_id=mapper))))
    monkeypatch.setattr(sql_translate, "_said_path", {})
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda: {})
    caplog.set_level(logging.WARNING, logger="ledger.sql_translate")
    declared, code = plan("hc_official", "declarative-role"), plan("dt_job", "dt-job-role")
    assert [sql_translate.translate_path(p) for p in (declared, code, declared, code)] == ["sql", "python"] * 2
    said = [r.getMessage() for r in caplog.records if r.name == "ledger.sql_translate"]
    assert said == ["[Ledger] hc_official translated by sql (ingestion_settings.json ledger_translate: 'sql')",
                    "[Ledger] dt_job translated by python (ingestion_settings.json ledger_translate: 'sql'"
                    " - its mapper is code)"], said
