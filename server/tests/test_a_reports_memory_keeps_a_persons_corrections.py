"""`derive.report` memory (lead 10-28, A-3's next step): a report declaring `memory` stands the same memory half an ask
does - a person's edit on the report table wakes it and `ask_rule.remember` writes a row for each text cell the
person changed. The AI's cells are the declaration's text slots its `results` names - read off the declaration, the
file column is not one. The row comes back in the next report's prompt by `prompts.memory.scope`; a scope column the
report table's key does not hold matches nothing."""
import pytest

from chain import ask_rule, report_shape, rule_shape
from database import crud, models, schemas
from conftest import retire_dynamic_model

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
        m[name].__table__.create(bind=db_session.get_bind())
    for wafer in ("W1", "W2"):
        db_session.add(m["rm_report"](row_id=wafer, business_key_val=wafer, wafer_id=wafer,
                                      report_file="/r/%s.html" % wafer, summary_text="scratch led"))
        for column, value in (("summary_text", "scratch led"), ("report_file", "/r/%s.html" % wafer)):
            db_session.add(models.CellSource(table_name="rm_report", row_id=wafer, column_name=column,
                                             source_name=crud.CHAIN_SOURCE, value=value, updated_by="eval_summary"))
    db_session.commit()
    yield db_session
    db_session.rollback()
    db_session.query(models.CellSource).filter(models.CellSource.table_name == "rm_report").delete()
    db_session.commit()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


def _person(db, row_id, column, value):
    db.add(models.CellSource(table_name="rm_report", row_id=row_id, column_name=column,
                             source_name=crud.USER_SOURCE, value=value, updated_by="kim"))
    db.commit()


def _half():
    (half,) = rule_shape.companion_rules(_internal())
    return half


def test_a_report_with_memory_stands_the_memory_half_and_one_without_stands_none():
    half = _half()
    assert (half["trigger_table"], half["target_table"], half["mapper"]) == ("rm_report", "rm_memory",
                                                                            ask_rule.ASK_MAPPER)
    assert rule_shape.declaration_of(half) == "eval_summary" and half["name"] != "eval_summary"
    assert ask_rule.written_columns(half) == ["purpose", "situation", "cell", "ai", "right", "who", "at"]
    bare = {k: v for k, v in REPORT.items() if k != "memory"}
    assert rule_shape.companion_rules(_internal(bare)) == []


def test_a_corrected_text_cell_is_remembered_the_file_cell_and_an_agreeing_one_are_not(world):
    _person(world, "W1", "summary_text", "particle led")
    _person(world, "W1", "report_file", "/elsewhere/W1.html")     # not a text slot of the declaration
    _person(world, "W2", "summary_text", "scratch led")            # the AI's own answer - nothing to learn
    out = ask_rule.answer(world, _half(), ["W1", "W2"])
    rows = [u["updates"] for u in out["updates"] if not u.get("gone")]
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
