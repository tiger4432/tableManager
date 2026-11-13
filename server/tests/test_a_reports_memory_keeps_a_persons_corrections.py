"""`derive.report` memory (lead 10-28, A-3's next step): a report declaring `memory` stands the same memory half an ask
does - a person's edit on the report table wakes it and `ask_rule.remember` writes a row for each text cell the
person changed. The AI's cells are the declaration's text slots its `results` names - read off the declaration, the
file column is not one. The row comes back in the next report's prompt by `prompts.memory.scope`; a scope column the
report table's key does not hold matches nothing."""
import pytest

from chain import ask_rule, report_shape, rule_shape
from database import crud, models, schemas
from conftest import retire_dynamic_model
from tests.support import line_tables

TABLES = {
    "rm_report": {"business_key": "wafer_id", "column_types": {
        "wafer_id": "string", "report_file": "string", "summary_text": "string"}},
    "rm_memory": {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
        "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
        "memo": "string", "who": "string", "at": "string"}},
}
MEMORY = {"table": "rm_memory", "columns": {"purpose": "purpose", "key": "situation", "cell": "cell", "ai": "ai",
                                            "right": "right", "memo": "memo", "who": "who", "when": "at"}}
REPORT = {
    "wafer": {"table": "rm_report", "key": "wafer_id"},
    "summary": {"table": "rm_report", "wafer": ["wafer_id"], "item": "summary_text", "fail": "summary_text",
                "total": "summary_text"},
    "layout": [{"kind": "text", "slot": "summary"}],
    "results": {"file": "report_file", "summary": "summary_text"},
    "prompts": {"memory": {"scope": ["wafer_id"], "limit": 3}},
    "memory": MEMORY,
}


def _internal(report=REPORT):
    return rule_shape.from_declaration({"name": "eval_summary", "on": {"table": "rm_report"},
                                        "into": {"table": "rm_report"},
                                        "derive": {"kind": "report", "report": dict(report)}})


@pytest.fixture
def world(db_session):
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        line_tables.build(db_session.get_bind(), name)      # its lines - a layer is a line (A 11-11)
    for wafer in ("W1", "W2"):
        db_session.add(m["rm_report"](row_id=wafer, business_key_val=wafer, wafer_id=wafer,
                                      report_file="/r/%s.html" % wafer, summary_text="scratch led"))
        for column, value in (("summary_text", "scratch led"), ("report_file", "/r/%s.html" % wafer)):
            line_tables.line(db_session.connection(), "rm_report", line_tables.bits_of("rm_report"), wafer,
                             source=crud.CHAIN_SOURCE, written_by="eval_summary", values={column: value})
    db_session.commit()
    yield db_session
    db_session.rollback()
    for name in TABLES:
        line_tables.drop(db_session.get_bind(), name)
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


def _person(db, row_id, column, value):
    line_tables.line(db.connection(), "rm_report", line_tables.bits_of("rm_report"), row_id,
                     source=crud.USER_SOURCE, written_by="kim", values={column: value})
    db.commit()


def _half():
    (half,) = rule_shape.companion_rules(_internal())
    return half


def test_a_report_with_memory_stands_the_memory_half_and_one_without_stands_the_shipped_ones():
    half = _half()
    assert (half["trigger_table"], half["target_table"], half["mapper"]) == ("rm_report", "rm_memory",
                                                                            ask_rule.ASK_MAPPER)
    assert rule_shape.declaration_of(half) == "eval_summary" and half["name"] != "eval_summary"
    assert ask_rule.written_columns(half) == ["purpose", "situation", "cell", "ai", "right", "who", "at"]
    bare = {k: v for k, v in REPORT.items() if k != "memory"}
    [shipped] = rule_shape.companion_rules(_internal(bare))
    assert (shipped["trigger_table"], shipped["target_table"]) == (
        "rm_report", ask_rule.MEMORY_TABLE), "owner 11-10: a report without memory remembers in the shipped table"


def test_a_corrected_text_cell_is_remembered_the_file_cell_and_an_agreeing_one_are_not(world):
    _person(world, "W1", "summary_text", "particle led")
    _person(world, "W1", "report_file", "/elsewhere/W1.html")     # not a text slot of the declaration
    _person(world, "W2", "summary_text", "scratch led")            # the AI's own answer - nothing to learn
    out = ask_rule.answer(world, _half(), ["W1", "W2"])
    rows = [u["updates"] for u in out["updates"] if not u.get("covers")]
    assert rows == [{"purpose": "eval_summary", "situation": '{"wafer_id": "W1"}', "cell": "summary_text",
                     "ai": "scratch led", "right": "particle led", "who": "kim", "at": rows[0]["at"]}], rows


def test_the_remembered_row_reaches_the_next_reports_prompt_by_its_scope(world):
    _person(world, "W1", "summary_text", "particle led")
    out = ask_rule.answer(world, _half(), ["W1"])
    crud.apply_batch_updates(world, "rm_memory", schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in out["updates"]]))
    world.commit()
    keys = report_shape.report_key(REPORT, "rm_report")
    assert keys == ["wafer_id"]
    said = ask_rule.memory_lines(world, REPORT, "eval_summary", dict(zip(keys, ("W1",))))
    assert "you said scratch led; correct: particle led" in said, said
    assert ask_rule.memory_lines(world, REPORT, "eval_summary", dict(zip(keys, ("W2",)))) == "", "another wafer's"
    off = dict(REPORT, prompts={"memory": {"scope": ["lot_id"], "limit": 3}})
    assert ask_rule.memory_lines(world, off, "eval_summary", {"wafer_id": "W1", "lot_id": "L1"}) == "", \
        "a scope column the report table's key does not hold matches nothing"
    assert ask_rule.memory_lines(world, off, "eval_summary", dict(zip(keys, ("W1",)))) == "", \
        "held on neither side - the report's own situation has no lot_id - matches nothing either, not everything"


def test_a_memory_half_is_listed_by_its_declarations_word_and_every_other_rule_as_before():
    from chain import dynamic_mappers, rule_run

    import chain_bindings

    assert rule_run.rule_label(_half()) == "report"
    assert chain_bindings.flat_param_cells(_half()) == (), "a routing cell - not read as a mapper argument"
    ask = rule_shape.from_declaration({"name": "step_kind", "on": {"table": "rm_report"},
                                       "into": {"table": "rm_report"},
                                       "derive": {"kind": "ask", "ask": {"memory": MEMORY}}})
    (ask_half,) = rule_shape.companion_rules(ask)
    assert rule_run.rule_label(ask_half) == "ask"
    for name in dynamic_mappers.TEMPLATES:                       # join · decide · report · ask: the cell absent
        assert rule_run.rule_label({"mapper": name}) == dynamic_mappers.label_for(name), name
    assert rule_run.rule_label({"mapper": "mappers.some_file.run"}) == "mapper"
    join = rule_shape.from_declaration({"name": "j", "on": {"table": "rm_report"}, "into": {"table": "rm_memory"},
                                        "derive": {"kind": "join", "join": {}}})
    assert all(rule_shape.COMPANION_MAPPER not in half for half in rule_shape.companion_rules(join)), \
        "the join's half keeps its own mapper - the cell is the memory half's alone"
