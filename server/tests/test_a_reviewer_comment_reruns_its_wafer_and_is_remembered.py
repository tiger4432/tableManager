# -*- coding: utf-8 -*-
"""A report's reviewer comment (owner 10-29 «summary 는 comment 칸 달아서 사람 코멘트 보고 다시 하게» · «주요 내용은
메모리로 저장하고», lead ㄱ): `derive.report.memory.comment` names a report table column. A person's comment there wakes
that wafer's report through the trigger path every person edit of the table takes, and the report's prompt says it
(«Reviewer comment: …»); the memory half keeps it as written - `cell` the comment column, no AI value - and every
report its `prompts.memory.scope` reaches reads it beside the past corrections. Real writes, the outbox events they
leave, and the worker's own `fires`:

  branch                       report woken (keys)   memory rows
  a person writes it                  1                  1
  a person changes it                 1                  1 (its new text)
  a person clears it                  1                  0
  the chain writes that column        0                  as before
  the report rewrites its summary     0                  as before
  no memory.comment                   the prompt and the memory as before
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chain import ask_rule, report_loop, rule_shape
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.database import Base

REPORT_TABLE, MEMORY_TABLE, SUMMARY_TABLE, NAME = "rc_report", "rc_memory", "rc_summary", "rc_eval"
TABLES = {
    SUMMARY_TABLE: {"composite_key_source": ["lot_id", "wafer_id", "item"], "column_types": {
        "lot_id": "string", "wafer_id": "string", "item": "string", "fail": "string", "total": "string"}},
    REPORT_TABLE: {"composite_key_source": ["lot_id", "wafer_id"], "column_types": {
        "lot_id": "string", "wafer_id": "string", "report_file": "string", "summary_text": "string",
        "reviewer_note": "string"}},
    MEMORY_TABLE: {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
        "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
        "who": "string", "at": "string"}},
}
MEMORY = {"table": MEMORY_TABLE, "comment": "reviewer_note",
          "columns": {"purpose": "purpose", "key": "situation", "cell": "cell", "ai": "ai", "right": "right",
                      "who": "who", "when": "at"}}
REPORT = {
    "wafer": {"table": REPORT_TABLE, "key": ["lot_id", "wafer_id"]},
    "summary": {"table": SUMMARY_TABLE, "wafer": ["lot_id", "wafer_id"], "item": "item", "fail": "fail",
                "total": "total"},
    "layout": [{"kind": "text", "slot": "summary"}],
    "results": {"file": "report_file", "summary": "summary_text"},
    "prompts": {"memory": {"scope": ["lot_id"], "limit": 3}},
    "memory": MEMORY,
}
COMMENT = "the scratch is a handling mark - say so"


def _rules(report=REPORT):
    stood, refusal, _notes = rule_shape.expand_declaration(
        {"name": NAME, "on": {"table": REPORT_TABLE}, "into": {"table": REPORT_TABLE},
         "derive": {"kind": "report", "report": dict(report)}}, TABLES)
    assert refusal is None
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
    _write(session, crud.CHAIN_SOURCE, NAME, [{"lot_id": "L1", "wafer_id": w, "summary_text": "scratch led",
                                               "report_file": "/r/%s.html" % w} for w in ("W1", "W2")])
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _write(db, source, by, rows):
    """-> the outbox events these writes left."""
    before = db.query(models.DatabaseOutbox.id).count()
    crud.apply_batch_updates(db, REPORT_TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name=source, updated_by=by,
                                  **({"own": [NAME]} if source == crud.CHAIN_SOURCE else {})) for r in rows]))
    db.commit()
    return db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id).all()[before:]


def _row_id(db, wafer):
    model = models.DYNAMIC_TABLES[REPORT_TABLE]
    return db.query(model.row_id).filter(model.wafer_id == wafer).scalar()


def _remember(db, half, wafers):
    """The memory half's answer written as the worker writes it - its rows, then its gone keys (`_delete_gone`)."""
    out = ask_rule.answer(db, half, [_row_id(db, w) for w in wafers])
    crud.apply_batch_updates(db, MEMORY_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in out["updates"] if not u.get("gone")]))
    worker._delete_gone(db, MEMORY_TABLE, [(u["business_key_val"], u["own"]) for u in out["updates"] if u.get("gone")])
    db.commit()
    model = models.DYNAMIC_TABLES[MEMORY_TABLE]
    return [(r.cell, r.ai, r.right) for r in db.query(model).all()]


def _person(db, wafer, text):
    return _write(db, crud.USER_SOURCE, "kim", [{"lot_id": "L1", "wafer_id": wafer, "reviewer_note": text}])


def test_each_branch_wakes_the_report_and_keeps_the_memory_as_the_table_says(db):
    report, half = _rules()
    table = {}
    for branch, events, wafers in (
            ("writes", lambda: _person(db, "W1", "a handling mark?"), ["W1"]),
            ("changes", lambda: _person(db, "W1", COMMENT), ["W1"]),
            ("chain writes the column", lambda: _write(db, crud.CHAIN_SOURCE, NAME, [
                {"lot_id": "L1", "wafer_id": "W2", "reviewer_note": "the chain's"}]), ["W2"]),
            ("summary rewritten", lambda: _write(db, crud.CHAIN_SOURCE, NAME, [
                {"lot_id": "L1", "wafer_id": "W1", "summary_text": "scratch, handling"}]), ["W1"]),
            ("clears", lambda: _person(db, "W1", ""), ["W1"])):
        left = events()
        assert left, "CANARY: %s left no event" % branch
        woken = [e for e in left if worker.wakes(report, e)]
        remembered = _remember(db, half, ["W1", "W2"]) if any(worker.wakes(half, e) for e in left) else None
        table[branch] = (len(woken), remembered)
    assert table == {
        "writes": (1, [("reviewer_note", None, "a handling mark?")]),
        "changes": (1, [("reviewer_note", None, COMMENT)]),
        "chain writes the column": (0, None),
        "summary rewritten": (0, None),
        "clears": (1, []),
    }, table


def test_the_wafers_report_says_its_comment_and_its_lot_reads_it_beside_the_corrections(db, monkeypatch):
    report, half = _rules()
    _person(db, "W1", COMMENT)
    _remember(db, half, ["W1"])
    asked = {}

    def run(_report, _spec, request, ask=None, clock=None):
        asked[_report] = request
        return {"state": report_loop.STOPPED, "reason": "test", "steps": [], "texts": {}, "tables": {}}

    monkeypatch.setattr(report_loop, "_this_wafer", lambda db_, spec, wafer: (wafer["wafer_id"], None))
    monkeypatch.setattr(report_loop, "run", run)
    report_loop.answer(db, report, [_row_id(db, "W1"), _row_id(db, "W2")])
    assert asked["W1"]["comment"] == COMMENT and asked["W2"]["comment"] == ""
    w1, w2 = report_loop._request(asked["W1"]), report_loop._request(asked["W2"])
    assert w1[2:4] == ["Note: none", "Reviewer comment: " + COMMENT]
    assert "Reviewer comment" not in "\n".join(w2), "a wafer with no comment: its prompt as before"
    assert '- {"lot_id": "L1", "wafer_id": "W1"} reviewer comment: ' + COMMENT in asked["W2"]["memory"], \
        "another wafer of the lot reads it where the corrections are read"


def test_without_memory_comment_the_column_is_neither_remembered_nor_said(db, monkeypatch):
    bare = dict(REPORT, memory={k: v for k, v in MEMORY.items() if k != "comment"})
    report, half = _rules(bare)
    _person(db, "W1", COMMENT)
    assert _remember(db, half, ["W1"]) == []
    asked = []
    monkeypatch.setattr(report_loop, "_this_wafer", lambda db_, spec, wafer: (wafer["wafer_id"], None))
    monkeypatch.setattr(report_loop, "run", lambda r, s, request, ask=None, clock=None: asked.append(request) or {
        "state": report_loop.STOPPED, "reason": "t", "steps": [], "texts": {}, "tables": {}})
    report_loop.answer(db, report, [_row_id(db, "W1")])
    assert asked[0]["comment"] == "" and "Reviewer comment" not in "\n".join(report_loop._request(asked[0]))
