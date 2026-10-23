# -*- coding: utf-8 -*-
"""소유자 2026-09-17: 「각 체인 «선언 종류»별로 잘되는지도 체크해봐」

🔴 THE SUBJECT IS 「돈다」, NOT 「간다」. Every kind already had a test that it RESOLVES, and
resolution is a predicate - it says a name became a callable. This file asks the only
question that cannot be satisfied by a signature: after the seat ran this declaration, are
the rows THERE. 판정 562 was caught exactly here - a template that computed the right answer
and did not write it passed every resolution test in the repository.

⚠️ AND IT IS PER DECLARATION KIND, which the caller×door matrix
(`test_every_caller_and_door_leaves_the_same_envelope`) does not cover: that one varies WHO
runs a rule, this one varies WHAT was declared. The two together are the grid.

The five a declaration can be today, all reaching `dynamic_mappers` or an operator's own
module through the ONE seat (`rule_run.resolve`):
    join            derive: {kind: "join"}                     -> declared:join
    decide 파생행    derive: {kind: "decide"}, the dedup half    -> declared:enrich
    decide 오토컨펌  the same declaration's other half           -> declared:decide
    mapper          mapper_module / mapper_function             -> the operator's module
    report          derive: {kind: "report"}                   -> declared:report (owner 10-22)
(virtual_join retired with its file - 판정 652.)
"""
import json
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import dynamic_mappers                                     # noqa: E402
from chain import report_shape, rule_run, rule_shape                  # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

SRC = "kinds_log"
DST = "kinds_attr"
ROWS = 3

TABLES = {
    SRC: {"business_key": "log_key", "composite_key_source": ["log_key"],
          "column_types": {"log_key": "string", "job": "string",
                           "lot_confirmed": "string", "note": "string",
                           "lot": "string"},
          "display_columns": ["log_key", "job", "lot_confirmed", "note", "lot"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "grade": "string"},
          "display_columns": ["job", "lot", "grade"]},
}

MAPPER_BODY = """
def map_it(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        key = ((p.get("data") or {}).get("log_key") or {}).get("value")
        out.append({"business_key_val": key,
                    "updates": {"log_key": key, "note": "seen"}})
    return {"updates": out}
"""


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.discover()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    # NEW rows only: `is_new` is the one shape `has_changed` cannot suppress, so a cell that
    # stays empty means the rule wrote nothing rather than that nothing changed.
    crud.apply_batch_updates(session, DST, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J", "lot": "LOT"},
                                  source_name="seed", updated_by="kinds")]))
    crud.apply_batch_updates(session, SRC, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "L%d" % n, "job": "J"},
                                  source_name="seed", updated_by="kinds")
        for n in range(ROWS)]))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _events(db, table):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == table).all()


def _values(db, table, column):
    model = models.DYNAMIC_TABLES[table]
    return [v for v in (getattr(r, column) for r in db.query(model).all()) if v]


def _run(db, tag, rules, trigger):
    worker._process_chain_transaction_group_sync(
        "tx-kinds-%s" % tag, _events(db, trigger), db, rules)
    db.commit()


def _door(rule):
    """Where this rule's name resolves - the seat, asked the way every caller asks it."""
    resolved = rule_run.resolve(rule)
    return "%s.%s" % (resolved.call.__module__, resolved.call.__name__)


# ---------------------------------------------------------------------------

def test_a_join_declaration_writes_the_taken_column(db):
    rules = rule_shape.expand_declaration(
        {"name": "kinds_join", "on": {"table": DST}, "into": {"table": SRC},
         "derive": {"kind": "join", "join": {
             "on": [{"left": "job", "right": "job"}],
             "take": [{"from": "lot", "into": "lot_confirmed"}]}}},
        crud.TABLE_CONFIG)[0]

    assert rules[0]["mapper"] == "declared:join"
    assert _door(rules[0]) == "chain.dynamic_mappers._join"

    _run(db, "join", rules, SRC)

    assert _values(db, SRC, "lot_confirmed") == ["LOT"] * ROWS


def test_a_decide_declaration_writes_one_derived_row_per_key(db):
    """파생행 — 「키당 한 행」 is the whole of what the dedup half does, so N source rows
    collapsing to ONE derived identity is the assertion. A per-row count would pass for a
    mapper that never grouped."""
    rules = rule_shape.expand_declaration(
        {"name": "kinds_decide", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}},
        crud.TABLE_CONFIG)[0]
    dedup = [r for r in rules if r["name"].startswith("enrichment_dedup:")][0]

    assert dedup["mapper"] == "declared:enrich"
    assert _door(dedup) == "chain.dynamic_mappers._enrich"

    # 🔴 [2026-09-24, 게이트 ㉡] AN IDENTITY THE FIXTURE DID NOT SEED. The fixture writes
    #    「J」 into the derived table before anything runs, so asserting 「J」 alone was
    #    satisfied by the seed - measured: replacing the chain seat with a no-op left this
    #    test green while its four siblings went red. 「K」 exists only in the source, so it
    #    can only reach the derived table by the declaration running.
    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "LK%d" % n, "job": "K"},
                                  source_name="seed", updated_by="kinds")
        for n in range(ROWS)]))
    db.commit()
    before = sorted(_values(db, DST, "job"))

    _run(db, "enrich", [dedup], SRC)

    # ROWS source rows per 「job」, so each job is ONE derived identity - and K is new.
    assert before == ["J"], "the fixture changed what it seeds, so K no longer means 'ran'"
    assert sorted(_values(db, DST, "job")) == ["J", "K"]


def test_an_auto_confirm_declaration_writes_the_single_candidate(db):
    """오토컨펌 «과» 참조뷰를 같이 잰다. The candidate comes out of a REFERENCE VIEW running
    real SQL, so this is also the proof that the reference-view capability survives - 소유자
    「인리치는 참조뷰 기능은 «보존»해야 해」 - measured by the value it wrote, not by a name."""
    rules = rule_shape.expand_declaration(
        {"name": "kinds_confirm", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {
             "key": ["job"], "fields": ["grade"], "auto_confirm": True,
             "reference_views": [{
                 "label": "후보",
                 "query": "SELECT lot AS grade FROM %s WHERE job = :job" % DST,
                 "candidate_for": {"grade": "grade"}}]}}},
        crud.TABLE_CONFIG)[0]
    dedup = [r for r in rules if r["name"].startswith("enrichment_dedup:")][0]
    confirm = [r for r in rules if r["name"].startswith("enrichment_auto_confirm:")][0]

    assert confirm["mapper"] == "declared:decide"
    assert _door(confirm) == "chain.dynamic_mappers._auto_confirm"

    _run(db, "ac-derive", [dedup], SRC)
    assert _values(db, DST, "grade") == [], "nothing may be confirmed before the probe runs"

    _run(db, "ac-confirm", [confirm], DST)

    assert _values(db, DST, "grade") == ["LOT"]


def test_a_file_mapper_declaration_writes_what_it_returned(db, tmp_path, monkeypatch):
    """The operator's own door, on the SAME arguments - 소유자 「체인 프로세스에 다 같은
    맵퍼 메소드로 인식되어서 움직이면됨. 같은 io를 가지고」."""
    (tmp_path / "kinds_probe_mapper.py").write_text(
        textwrap.dedent(MAPPER_BODY), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("kinds_probe_mapper", None)
    rule = {"name": "kinds_mapper", "enabled": True, "is_batch": True,
            "trigger_table": SRC, "target_table": SRC,
            "mapper_module": "kinds_probe_mapper", "mapper_function": "map_it"}
    try:
        assert _door(rule) == "kinds_probe_mapper.map_it"

        _run(db, "mapper", [rule], SRC)

        assert _values(db, SRC, "note") == ["seen"] * ROWS
    finally:
        sys.modules.pop("kinds_probe_mapper", None)


# ⚰️ [판정 652 3걸음] `test_a_materialized_virtual_join_writes_the_exposed_column` 이 여기
#    있었습니다. 그 종류(`declared:virtual_join`)는 «선언 파일»이 사라져 더는 지어지지
#    않습니다 — 조인은 `chain_rules.json` 의 `derive: {kind: "join"}` 하나로 선언되고 위의
#    `test_a_join_declaration_writes_the_taken_column` 이 그것을 잽니다.


REPORT_TABLES = {
    "kinds_wafer": {"business_key": "wafer", "composite_key_source": ["wafer"],
                    "column_types": {"wafer": "string", "ev": "string", "at": "string", "grp": "string"}},
    "kinds_sum": {"composite_key_source": ["wafer", "item"],
                  "column_types": {"wafer": "string", "item": "string", "fail": "number", "total": "number",
                                   "st": "string", "fl": "string", "why": "string"}},
}


@pytest.fixture(name="reported")
def fixture_reported(db, tmp_path, monkeypatch):
    """The report kind's two tables, the summary rows written as a file writes them - one event naming them all,
    W1 with two items - the files kept in `tmp_path`. Yields the declaration's rules - one, on the summary table
    (owner 10-23)."""
    import event_constants
    import paths
    from database.context import outbox_mode
    from conftest import retire_dynamic_model

    models.init_dynamic_models(REPORT_TABLES)
    crud.TABLE_CONFIG.update(REPORT_TABLES)
    for name in REPORT_TABLES:
        models.DYNAMIC_TABLES[name].__table__.create(bind=db.get_bind())
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    for table, rows in (("kinds_wafer", [{"wafer": "W1", "ev": "E1", "at": "1"}, {"wafer": "W2", "ev": "E1", "at": "2"}]),
                        ("kinds_sum", [{"wafer": "W1", "item": "particle", "fail": 1, "total": 100},
                                       {"wafer": "W1", "item": "scratch", "fail": 0, "total": 100},
                                       {"wafer": "W2", "item": "particle", "fail": 3, "total": 100}])):
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds") for row in rows]))
    db.commit()
    rules = rule_shape.expand_declaration(
        {"name": "kinds_report", "on": {"table": "kinds_sum"}, "into": {"table": "kinds_sum"},
         "derive": {"kind": "report", "report": {
             "wafer": {"table": "kinds_wafer", "key": "wafer", "time": "at", "evaluation": "ev"},
             "summary": {"table": "kinds_sum", "wafer": "wafer", "item": "item", "fail": "fail", "total": "total"},
             "results": {"state": "st", "file": "fl", "reason": "why"},
             "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
             "loop": {"steps": 3, "seconds": 60, "context_tokens": 16000}}}},
        crud.TABLE_CONFIG)[0]
    try:
        yield rules
    finally:
        db.rollback()
        for name in REPORT_TABLES:
            models.DYNAMIC_TABLES[name].__table__.drop(bind=db.get_bind())
            crud.TABLE_CONFIG.pop(name, None)
            retire_dynamic_model(name)


def _report_rows(db):
    db.expire_all()
    return sorted((r.wafer, r.st, r.why, r.fl) for r in db.query(models.DYNAMIC_TABLES["kinds_sum"]).all())


def test_a_report_declaration_writes_a_report_a_wafer_into_its_summary_rows(db, reported, monkeypatch):
    """The model stands in (no gateway in a test): it reads the summary table, says done, writes - each wafer's
    summary rows say done and name their own file, and the file ends with the steps it took (Evidence)."""
    from utils import llm

    def model(prompt, usage=None):
        if "Tables read:" in prompt:
            return {"done": {"summary": "particle is low."}}
        return {"call": "yield_by", "args": {}} if "This is step 1 of" in prompt else {"done": {}}

    monkeypatch.setattr(llm, "ask_json", model)
    [rule] = reported

    assert rule["mapper"] == "declared:report"
    assert _door(rule) == "chain.dynamic_mappers._report"

    _run(db, "report", reported, "kinds_sum")

    rows = _report_rows(db)
    assert [(w, st, why) for w, st, why, _fl in rows] == [("W1", "done", None)] * 2 + [("W2", "done", None)]
    assert len({fl for *_rest, fl in rows}) == 2, "a file a wafer - one event named both wafers' rows"
    for wafer, _st, _why, fl in rows:
        text = open(fl, encoding="utf-8").read()
        assert wafer in text and "particle is low." in text
        evidence = text[text.index('<details class="evidence">'):]
        assert "1 yield_by" in evidence and "2 done" in evidence and "3 write" in evidence, evidence


def test_a_report_without_a_model_leaves_its_rows_stopped_with_why(db, reported, monkeypatch):
    from utils import llm

    def refused(prompt, usage=None):
        raise llm.LlmRefused("no gateway in this test")

    monkeypatch.setattr(llm, "ask_json", refused)
    _run(db, "report-refused", reported, "kinds_sum")

    rows = _report_rows(db)
    why = "the language model call was refused: no gateway in this test"
    assert [(w, st, r) for w, st, r, _fl in rows] == [("W1", "stopped", why)] * 2 + [("W2", "stopped", why)]


def _sent_reports(db, reported, monkeypatch, answers):
    """Both wafers' reports made with `send_to`, then the upkeep's sweep run once a list of answers: the post
    answers each in turn (None: taken). -> (the rows after each sweep, the files posted)."""
    from chain import report_loop
    from utils import llm

    def model(prompt, usage=None):
        return {"done": {"summary": "ok"}} if "Tables read:" in prompt else {"done": {}}

    monkeypatch.setattr(llm, "ask_json", model)
    [rule] = reported
    rule["params"]["send_to"] = "http://relay.test/reports"
    _run(db, "report-send", reported, "kinds_sum")
    posted, tries, after = [], {}, [_report_rows(db)]
    for said in answers:
        def post(send_to, file_, said=said):
            posted.append((send_to, os.path.basename(file_)))
            return said
        report_loop.send_waiting([rule], lambda: _Kept(db), tries, post=post)
        after.append(_report_rows(db))
    return after, posted


class _Kept:
    """The test's one session, handed to the sweep as its own - closing it is not the sweep's to do here."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


def test_a_made_report_is_sent_to_its_address_by_the_upkeep(db, reported, monkeypatch):
    after, posted = _sent_reports(db, reported, monkeypatch, [None])
    assert [st for _w, st, _why, _fl in after[0]] == ["sending"] * 3, "made, not sent yet"
    assert [(st, why) for _w, st, why, _fl in after[1]] == [("done", None)] * 3
    assert sorted(posted) == [("http://relay.test/reports", "W1.html"), ("http://relay.test/reports", "W2.html")]
    sends = [e for e in _events(db, "kinds_sum") if "st" in json.dumps(e.payload)][-1:]
    [rule] = reported
    assert sends and worker.fire_refusal(rule, sends[0]) == worker.FIRE_REFUSED_CHAIN, \
        "the sweep writes on the chain's channel - the report rule is not woken by its own state"


def test_a_send_that_fails_three_times_says_send_failed_and_why(db, reported, monkeypatch):
    from chain import report_loop

    after, posted = _sent_reports(db, reported, monkeypatch, ["relay down"] * report_loop.SEND_TRIES)
    assert [st for _w, st, _why, _fl in after[report_loop.SEND_TRIES - 1]] == ["sending"] * 3, "tried again"
    assert [(st, why) for _w, st, why, _fl in after[-1]] == [("send failed", "relay down")] * 3
    assert len(posted) == 2 * report_loop.SEND_TRIES


def test_a_stopped_report_is_not_sent(db, reported, monkeypatch):
    from chain import report_loop
    from utils import llm

    def refused(prompt, usage=None):
        raise llm.LlmRefused("no gateway in this test")

    monkeypatch.setattr(llm, "ask_json", refused)
    [rule] = reported
    rule["params"]["send_to"] = "http://relay.test/reports"
    _run(db, "report-stopped", reported, "kinds_sum")
    posted = []
    report_loop.send_waiting([rule], lambda: _Kept(db), {}, post=lambda *a: posted.append(a))
    assert posted == [] and {st for _w, st, _why, _fl in _report_rows(db)} == {"stopped"}


def test_the_five_kinds_are_the_whole_of_what_the_product_builds():
    """⚠️ THE CONTROL ON THIS FILE ITSELF. The names above are built by
    `dynamic_mappers`; if a fifth template appears, the tests above still pass and this file
    has quietly stopped being 「종류별로」. The remaining kind is an operator's own module,
    which has no name here to count."""
    mapper_sdk.discover()

    assert sorted(dynamic_mappers.TEMPLATES) == [
        "declared:decide", "declared:enrich", "declared:join", "declared:report"]


def test_a_switched_off_report_makes_nothing_by_itself_and_one_report_a_wafer_by_a_replay_naming_it(
        db, reported, monkeypatch):
    """Owner 10-23 «자동 시작은 막고 리플레이로» · «막아»: `enabled: false` is «nothing wakes it» - the summary rows'
    event makes no report; a replay naming the rule (its events carry `only_rule`) makes one a wafer."""
    from utils import llm
    from database.database import stage_collapsed_event

    monkeypatch.setattr(llm, "ask_json", lambda prompt, usage=None: (
        {"done": {"summary": "particle is low."}} if "Tables read:" in prompt else {"done": {}}))
    declaration = {"name": "kinds_report", "enabled": False, "on": {"table": "kinds_sum"},
                   "into": {"table": "kinds_sum"}, "derive": {"kind": "report", "report": reported[0]["params"]}}
    stood, refusal, notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
    assert refusal is None and [r["enabled"] for r in stood] == [False], (refusal, notes)
    assert "nothing wakes it" in notes[0]

    _run(db, "report-off", stood, "kinds_sum")
    assert {st for _w, st, _why, _fl in _report_rows(db)} == {None}

    model = models.DYNAMIC_TABLES["kinds_sum"]
    for event in _events(db, "kinds_sum"):
        db.delete(event)
    stage_collapsed_event(db, "EDIT", "kinds_sum", [r.row_id for r in db.query(model).all()],
                          only_rule="kinds_report", replay=True)
    db.commit()
    _run(db, "report-replayed", stood, "kinds_sum")
    rows = _report_rows(db)
    assert [(w, st) for w, st, _why, _fl in rows] == [("W1", "done")] * 2 + [("W2", "done")]


def test_control_same_keeps_the_candidates_that_share_those_columns(db, reported):
    """Owner 10-23 «제품군도 필터링»: `control.same` names wafer-table columns a control candidate shares with the
    report's wafer - another value's evaluation leaves the candidates; empty filters nothing."""
    from chain import report_reads

    model = models.DYNAMIC_TABLES["kinds_wafer"]
    crud.apply_batch_updates(db, "kinds_wafer", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds")
        for row in ({"wafer": "W1", "at": "2026-10-20 10:00:00", "grp": "A"},
                    {"wafer": "W2", "at": "2026-10-20 11:00:00", "grp": "A"},
                    {"wafer": "P1", "ev": "E0", "at": "2026-10-10 10:00:00", "grp": "A"},
                    {"wafer": "Q1", "ev": "E9", "at": "2026-10-11 10:00:00", "grp": "B"})]))
    db.commit()
    assert db.query(model).count() == 4
    spec = dict(reported[0]["params"], control={"recent": {"evaluations": 5}})
    lines = report_reads.Report(db, spec, None, only=("W1",)).candidates()["context"]
    assert "E0" in lines and "E9" in lines                            # canary: both are candidates unfiltered
    spec["control"]["same"] = ["grp"]
    assert report_shape.refusal(spec, "kinds_sum", "kinds_sum") is None
    lines = report_reads.Report(db, spec, None, only=("W1",)).candidates()["context"]
    assert "E0" in lines and "E9" not in lines
    assert "not a column" in report_shape.refusal(dict(spec, control={"recent": {"days": 1}, "same": ["nope"]}),
                                                  "kinds_sum", "kinds_sum")
