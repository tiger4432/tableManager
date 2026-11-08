# -*- coding: utf-8 -*-
"""A report's question goes to its table, never into its file (owner 11-08 «2 ㄴ»), and the report reads a memo as an
ask rule does (owner «3 ㄱ»): one declaration each, one reader each.

  layout slot `file: false`   the model writes it · results may name its column · the page and the template leave it out
  prompts.memo `on`            the situation's column its key is matched with - unsaid: the first (an ask's group value)
  the situation                a row's key columns and the `prompts.memory.scope` columns its table declares - product
                               on a report table keyed by the wafer alone; a memory table declaring product holds it as
                               a column too, so a rule folding it groups by it
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chain import ask_rule, report_html, report_loop, report_shape, report_template, rule_shape
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.database import Base

REPORT_TABLE, MEMORY_TABLE, SUMMARY_TABLE, LESSONS, NAME = "rq_report", "rq_memory", "rq_summary", "rq_lessons", "rq_eval"
TABLES = {
    SUMMARY_TABLE: {"composite_key_source": ["lot_id", "wafer_id", "item"], "column_types": {
        "lot_id": "string", "wafer_id": "string", "item": "string", "fail": "string", "total": "string"}},
    REPORT_TABLE: {"composite_key_source": ["lot_id", "wafer_id"], "column_types": {
        "lot_id": "string", "wafer_id": "string", "product": "string", "report_file": "string",
        "summary_text": "string", "question_text": "string", "reviewer_note": "string"}},
    MEMORY_TABLE: {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
        "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
        "who": "string", "at": "string", "product": "string"}},
    LESSONS: {"composite_key_source": ["product"], "column_types": {"product": "string", "lesson": "string"}},
}
MEMORY = {"table": MEMORY_TABLE, "comment": "reviewer_note",
          "columns": {"purpose": "purpose", "key": "situation", "cell": "cell", "ai": "ai", "right": "right",
                      "who": "who", "when": "at"}}
LAYOUT = [{"kind": "text", "slot": "summary"}, {"kind": "text", "slot": "question", "file": False}]
REPORT = {
    "wafer": {"table": REPORT_TABLE, "key": ["lot_id", "wafer_id"]},
    "summary": {"table": SUMMARY_TABLE, "wafer": ["lot_id", "wafer_id"], "item": "item", "fail": "fail",
                "total": "total"},
    "layout": LAYOUT,
    "results": {"file": "report_file", "summary": "summary_text", "question": "question_text"},
    "prompts": {"memory": {"scope": ["product"], "limit": 3},
                "memo": {"table": LESSONS, "key": "product", "text": "lesson", "on": "product"}},
    "memory": MEMORY,
}
QUESTION, LESSON = "is the scratch a handling mark?", "P1 scratches at the notch are handling marks"


def _rules(report=REPORT):
    stood, refusal, _notes = rule_shape.expand_declaration(
        {"name": NAME, "on": {"table": REPORT_TABLE}, "into": {"table": REPORT_TABLE},
         "derive": {"kind": "report", "report": dict(report)}}, TABLES)
    assert refusal is None, refusal
    by = {r["name"]: r for r in stood}
    return by[NAME], by.get(NAME + rule_shape.COMPANION_SUFFIX)


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    for name, entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    _write(session, REPORT_TABLE, crud.CHAIN_SOURCE, NAME, [
        {"lot_id": "L1", "wafer_id": w, "product": p, "summary_text": "scratch led", "report_file": "/r/%s.html" % w}
        for w, p in (("W1", "P1"), ("W2", "P1"), ("W3", "P2"))])
    _write(session, LESSONS, crud.USER_SOURCE, "kim", [{"product": "P1", "lesson": LESSON}])
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _write(db, table, source, by, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name=source, updated_by=by,
                                  **({"own": [NAME]} if source == crud.CHAIN_SOURCE else {})) for r in rows]))
    db.commit()


def _row_id(db, wafer):
    model = models.DYNAMIC_TABLES[REPORT_TABLE]
    return db.query(model.row_id).filter(model.wafer_id == wafer).scalar()


def _remember(db, half, wafers):
    out = ask_rule.answer(db, half, [_row_id(db, w) for w in wafers])
    crud.apply_batch_updates(db, MEMORY_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in out["updates"] if not u.get("gone")]))
    worker._delete_gone(db, MEMORY_TABLE, [(u["business_key_val"], u["own"]) for u in out["updates"] if u.get("gone")])
    db.commit()
    return db.query(models.DYNAMIC_TABLES[MEMORY_TABLE]).all()


def _asked(db, monkeypatch, report, wafers):
    asked = {}

    def run(_report, _spec, request, ask=None, clock=None, live=None):
        asked[_report] = request
        return {"state": report_loop.STOPPED, "reason": "test", "steps": [], "texts": {}, "tables": {}}

    monkeypatch.setattr(report_loop, "_this_wafer", lambda db_, spec, wafer: (wafer["wafer_id"], None))
    monkeypatch.setattr(report_loop, "run", run)
    report_loop.answer(db, report, [_row_id(db, w) for w in wafers])
    return asked


# --------------------------------------------------------------- a question off the file

def test_the_model_writes_the_question_and_its_column_is_named_but_the_file_leaves_it_out(db):
    assert report_shape.text_slots(REPORT) == ["summary", "question"], "what the model writes · results may name"
    assert report_shape.text_slots(REPORT, shown=True) == ["summary"], "what the file shows"
    assert [cell for cell, _c in report_shape.result_cells(REPORT)] == ["file", "summary", "question"]
    assert report_shape.refusal(REPORT) is None
    assert '"question": "<text>"' in report_loop.WRITE % ", ".join(
        '"%s": "<text>"' % s for s in report_shape.text_slots(REPORT))
    page = report_html.page("W1", "m", REPORT, {}, {}, {"summary": "scratch led", "question": QUESTION})
    assert "scratch led" in page and QUESTION not in page and "question" not in page


def test_a_template_has_no_mark_for_it_and_misses_none_without_it():
    with_mark = dict(REPORT, template="<table><tr><td>{{summary}}</td><td>{{question}}</td></tr></table>")
    without = dict(REPORT, template="<table><tr><td>{{summary}}</td></tr></table>")
    assert "{{question}} is not a mark this report fills" in report_template.refusal(with_mark)
    assert report_template.refusal(without) is None
    shown = dict(without, layout=[{"kind": "text", "slot": "summary"}, {"kind": "text", "slot": "question"}])
    assert "has no {{question}}" in report_template.refusal(shown), "a slot the file shows still needs its mark"


@pytest.mark.parametrize("said", ["false", 0, None])
def test_file_is_false_or_unsaid(db, said):
    spec = dict(REPORT, layout=[{"kind": "text", "slot": "summary"}, {"kind": "text", "slot": "question", "file": said}])
    assert "derive.report.layout[1].file is false" in report_shape.refusal(spec)


# --------------------------------------------------------------- the situation and the memo

def test_the_situation_is_the_key_and_the_scope_its_table_declares(db):
    assert ask_rule.situation_columns(REPORT, REPORT_TABLE) == ["lot_id", "product", "wafer_id"]
    assert ask_rule.situation_columns(REPORT, SUMMARY_TABLE) == ["item", "lot_id", "wafer_id"], "no product there"
    keyed = dict(REPORT, prompts={"memory": {"scope": ["lot_id"]}})
    assert ask_rule.situation_columns(keyed, REPORT_TABLE) == ["lot_id", "wafer_id"], \
        "a scope column already a key: the situation as before"


def test_a_correction_holds_its_product_and_another_wafer_of_it_reads_it_and_the_lesson(db, monkeypatch):
    report, half = _rules()
    _write(db, REPORT_TABLE, crud.USER_SOURCE, "kim", [{"lot_id": "L1", "wafer_id": "W1", "summary_text": "handling"}])
    rows = _remember(db, half, ["W1"])
    assert [(r.cell, r.product, json.loads(r.situation)) for r in rows] == [
        ("summary_text", "P1", {"lot_id": "L1", "product": "P1", "wafer_id": "W1"})]
    assert "product" in ask_rule.written_columns(half)
    asked = _asked(db, monkeypatch, report, ["W2", "W3"])
    assert "you said scratch led; correct: handling" in asked["W2"]["memory"], "the same product reads it"
    assert asked["W3"]["memory"] == "", "another product does not"
    assert asked["W2"]["memo"] == LESSON and asked["W3"]["memo"] == ""
    assert LESSON in report_loop._request(asked["W2"])


def test_an_ask_rules_memo_is_its_first_group_value_unless_on_says_another(db):
    spec = {"input": {"group_by": ["product", "lot_id"]}, "prompts": {"memo": {"table": LESSONS, "key": "product",
                                                                                "text": "lesson"}}}
    request = [(json.dumps(["P1", "L1"]), "a text")]
    assert LESSON in ask_rule.prompt(db, spec, request, "")
    on_lot = {"input": {"group_by": ["lot_id", "product"]}, "prompts": {"memo": dict(spec["prompts"]["memo"], on="product")}}
    assert LESSON in ask_rule.prompt(db, on_lot, [(json.dumps(["L1", "P1"]), "a text")], "")
    unsaid = {"input": {"group_by": ["lot_id", "product"]}, "prompts": {"memo": spec["prompts"]["memo"]}}
    assert LESSON not in ask_rule.prompt(db, unsaid, [(json.dumps(["L1", "P1"]), "a text")], ""), \
        "unsaid: the first group value, as before"
