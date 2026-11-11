"""Owner 11-10 «AI 메모리 설정은 내가 해야하나?» - no: an ask or report rule whose `memory` names no table remembers in
the shipped `sys_ai_memory` by its columns (`ask_rule.memory_of`), and a prompt reads it back as `prompts.memory`
would with no scope, five rows, when that is not written. A `memory` naming a table goes as written; one writing only
columns is the shipped table with those columns as written, only `comment` the shipped table and columns. The same
correction makes the same memory row."""
import json
import os

import pytest

from chain import ask_rule, rule_shape
from database import crud, models, schemas
from conftest import retire_dynamic_model

MEMORY_TYPES = {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
    "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
    "memo": "string", "who": "string", "at": "string"}}
TABLES = {
    "am_report": {"business_key": "wafer_id", "column_types": {
        "wafer_id": "string", "report_file": "string", "summary_text": "string", "note_text": "string"}},
    "am_memory": MEMORY_TYPES,
}
WRITTEN = {"table": "am_memory", "columns": dict(ask_rule.MEMORY_COLUMNS)}
REPORT = {
    "wafer": {"table": "am_report", "key": "wafer_id"},
    "summary": {"table": "am_report", "wafer": ["wafer_id"], "item": "summary_text", "fail": "summary_text",
                "total": "summary_text"},
    "layout": [{"kind": "text", "slot": "summary"}],
    "results": {"file": "report_file", "summary": "summary_text"},
}
BRANCHES = {                                   # memory block -> the table it remembers in
    "written": (WRITTEN, "am_memory"),
    "none": (None, ask_rule.MEMORY_TABLE),
    "columns only": ({"columns": dict(ask_rule.MEMORY_COLUMNS)}, ask_rule.MEMORY_TABLE),
    "comment only": ({"comment": "note_text"}, ask_rule.MEMORY_TABLE),
    "table only": ({"table": "am_memory"}, "am_memory"),         # the columns the defaults' (A's NO-GO ②)
}


def _declaration(kind, memory):
    spec = dict(REPORT) if kind == "report" else {"output": {"cells": ["summary_text"]}}
    if memory is not None:
        spec["memory"] = memory
    return rule_shape.from_declaration({"name": "eval_summary", "on": {"table": "am_report"},
                                        "into": {"table": "am_report"}, "derive": {"kind": kind, kind: spec}})


@pytest.fixture
def world(db_session, monkeypatch):
    with open(os.path.join(os.path.dirname(__file__), "..", "declarations", "table_config.json"), encoding="utf-8") as f:
        monkeypatch.setitem(crud.TABLE_CONFIG, ask_rule.MEMORY_TABLE, json.load(f)[ask_rule.MEMORY_TABLE])
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        m[name].__table__.create(bind=db_session.get_bind())
    db_session.add(m["am_report"](row_id="W1", business_key_val="W1", wafer_id="W1", report_file="/r/W1.html",
                                  summary_text="scratch led"))
    db_session.add(models.CellSource(table_name="am_report", row_id="W1", column_name="summary_text",
                                     source_name=crud.CHAIN_SOURCE, value="scratch led", updated_by="eval_summary"))
    db_session.add(models.CellSource(table_name="am_report", row_id="W1", column_name="summary_text",
                                     source_name=crud.USER_SOURCE, value="particle led", updated_by="kim"))
    db_session.commit()
    shipped = m[ask_rule.MEMORY_TABLE]                      # the declarations ship it - every install has it
    yield db_session
    db_session.rollback()
    db_session.query(models.CellSource).filter(models.CellSource.table_name == "am_report").delete()
    db_session.query(shipped).delete()
    db_session.commit()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


@pytest.mark.parametrize("kind", ["ask", "report"])
@pytest.mark.parametrize("branch", list(BRANCHES))
def test_every_ai_rule_stands_its_memory_half_in_the_table_its_memory_names_or_the_shipped_one(kind, branch):
    memory, table = BRANCHES[branch]
    (half,) = rule_shape.companion_rules(_declaration(kind, memory))
    assert (half["trigger_table"], half["target_table"]) == ("am_report", table)
    assert ask_rule.written_columns(half) == ["purpose", "situation", "cell", "ai", "right", "who", "at"]


@pytest.mark.parametrize("branch", list(BRANCHES))
def test_the_same_correction_makes_the_same_memory_row_in_every_branch(world, branch):
    memory, table = BRANCHES[branch]
    (half,) = rule_shape.companion_rules(_declaration("report", memory))
    out = ask_rule.answer(world, half, ["W1"])
    rows = [u["updates"] for u in out["updates"] if not u.get("covers")]
    assert rows == [{"purpose": "eval_summary", "situation": '{"wafer_id": "W1"}', "cell": "summary_text",
                     "ai": "scratch led", "right": "particle led", "who": "kim", "at": rows[0]["at"]}], rows
    crud.apply_batch_updates(world, table, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in out["updates"]]))
    world.commit()
    spec = rule_shape.as_chain_rule(_declaration("report", memory))["params"]
    assert "prompts" not in spec, "canary: no prompts.memory written"
    said = ask_rule.memory_lines(world, spec, "eval_summary", {"wafer_id": "W1"})
    if memory is None:              # no block: the rule's whole memory (owner 11-10)
        assert "you said scratch led; correct: particle led" in said, said
    else:                           # a block written, no prompts.memory: read nothing, as before (A's NO-GO ③)
        assert said == "", said
    read = dict(spec, prompts={"memory": {}})
    assert "you said scratch led; correct: particle led" in ask_rule.memory_lines(
        world, read, "eval_summary", {"wafer_id": "W1"}), "a written prompts.memory reads it in every branch"


def test_a_written_prompts_memory_goes_as_written(world):
    (half,) = rule_shape.companion_rules(_declaration("report", None))
    out = ask_rule.answer(world, half, ["W1"])
    crud.apply_batch_updates(world, ask_rule.MEMORY_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in out["updates"]]))
    world.commit()
    spec = dict(REPORT, prompts={"memory": {"scope": ["lot_id"], "limit": 3}})
    assert ask_rule.memory_lines(world, spec, "eval_summary", {"wafer_id": "W1"}) == "", "its scope, not the default"
    assert ask_rule.memory_lines(world, spec, "another_rule", {"wafer_id": "W1"}) == ""
    assert ask_rule.memory_lines(world, REPORT, "another_rule", {"wafer_id": "W1"}) == "", \
        "one rule's memory is not another's - purpose is the rule's name"


@pytest.mark.parametrize("memory,said", [
    ({"columns": {"who": "editor"}}, "memory.columns: editor not in sys_ai_memory"),
    ({"table": "am_memory", "columns": {"memo": "note"}}, "memory.columns: note not in am_memory"),
    ({"table": "no_such_table"}, "memory.table 'no_such_table' is not a declared table"),
])
def test_a_memory_naming_what_its_table_does_not_hold_is_refused_at_save(world, memory, said):
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration("ask", memory))
    assert rules == [] and said in refusal, refusal


def test_a_rule_name_ending_in_the_halfs_tail_is_refused_at_save(world):
    declaration = _declaration("ask", None)
    declaration["name"] = "eval" + rule_shape.COMPANION_SUFFIX
    rules, refusal, _notes = rule_shape.expand_declaration(declaration)
    assert rules == [] and "may not end in ':target'" in refusal, refusal
    assert rule_shape.expand_declaration(_declaration("ask", None))[1] is None, "canary: the same, named plainly"


def test_a_memory_writing_some_columns_keeps_those_and_stands(world):
    """A rule declared before the defaults: its columns go as written - no default role is added, so a memory table
    without `memo` still stands (the reviewer-comment rule's shape)."""
    columns = {key: column for key, column in ask_rule.MEMORY_COLUMNS.items() if key != "memo"}
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration("ask", {"table": "am_memory", "columns": columns}))
    assert refusal is None and len(rules) == 2, refusal
    assert ask_rule.memory_of({"memory": {"columns": columns}})["columns"] == columns


def _ask(name, memory):
    spec = {"output": {"cells": ["summary_text"]}}
    if memory is not None:
        spec["memory"] = memory
    return {"name": name, "on": {"table": "am_report"}, "into": {"table": "am_report"},
            "derive": {"kind": "ask", "ask": spec}}


BAD = {                                        # a memory block -> the role its refusal names
    "null": ({"table": "am_memory", "columns": dict(WRITTEN["columns"], who=None)}, "who=null"),
    "a number": ({"table": "am_memory", "columns": dict(WRITTEN["columns"], who=5)}, "who=5"),
    "a list": ({"table": "am_memory", "columns": dict(WRITTEN["columns"], who=["who"])}, 'who=["who"]'),
    "columns as text": ({"columns": "situation"}, 'not "situation"'),
    "no key": ({"table": "am_memory", "columns": {"purpose": "purpose", "cell": "cell"}}, "key not named"),
}


@pytest.mark.parametrize("bad", list(BAD))
def test_one_bad_memory_block_drops_only_its_rule_at_load(world, tmp_path, monkeypatch, bad):
    """QA 11-11 ①: a column not text raised out of `memory_refusal` into the loader's «unified grammar unreadable» -
    every unified rule of the file fell, not the bad one. ③: a `columns` without purpose or key stood and raised at
    the first correction."""
    import logging
    from chain import ingestion_worker as worker

    memory, said = BAD[bad]
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_ask("eval_a", None), _ask("eval_bad", memory),
                                          _ask("eval_b", WRITTEN)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    lines = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    worker.logger.addHandler(handler)
    try:
        stood = {r.get("name"): r for r in worker.load_chain_rules()}
    finally:
        worker.logger.removeHandler(handler)
    assert not [l for l in lines if "unified grammar unreadable" in l], lines
    assert "eval_bad" not in stood and "eval_bad" + rule_shape.COMPANION_SUFFIX not in stood, sorted(stood)
    assert [l for l in lines if "[ChainRules] eval_bad: memory" in l and said in l], lines
    for name in ("eval_a", "eval_b"):                       # the others stand, translated
        assert stood[name]["mapper"] == ask_rule.ASK_MAPPER, stood[name]
        assert name + rule_shape.COMPANION_SUFFIX in stood, sorted(stood)
    rules, refusal, _notes = rule_shape.expand_declaration(_ask("eval_bad", memory))
    assert rules == [] and said in refusal, refusal         # the save's judgement is the loader's


def test_a_blank_memory_column_is_its_roles_default_at_save_and_load(world, tmp_path, monkeypatch):
    """QA 11-11 ②: the form's emptied box writes "" - it was refused as «memory.columns:  not in …», no name."""
    from chain import ingestion_worker as worker

    blank = {"table": "am_memory", "columns": dict(WRITTEN["columns"], who="", memo="  ")}
    rules, refusal, _notes = rule_shape.expand_declaration(_ask("eval_blank", blank))
    assert refusal is None and len(rules) == 2, refusal
    assert ask_rule.memory_of({"memory": blank})["columns"] == ask_rule.MEMORY_COLUMNS
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_ask("eval_blank", blank)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    half = {r.get("name"): r for r in worker.load_chain_rules()}["eval_blank" + rule_shape.COMPANION_SUFFIX]
    assert ask_rule.written_columns(half) == ["purpose", "situation", "cell", "ai", "right", "who", "at"]
