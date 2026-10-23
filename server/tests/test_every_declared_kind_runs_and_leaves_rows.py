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
    "kinds_wafer": {"composite_key_source": ["wafer", "leg"],
                    "column_types": {"wafer": "string", "leg": "string", "ev": "string", "at": "string",
                                     "grp": "string"}},
    "kinds_sum": {"composite_key_source": ["wafer", "leg", "item"],
                  "column_types": {"wafer": "string", "leg": "string", "item": "string", "fail": "number",
                                   "total": "number"}},
    # the operator's report table - one row a wafer, its file path (owner 10-23 «리포트용 표가 따로» · «wafer, 보고서
    # 파일 경로 이 두 개가 최종 출력»)
    "kinds_rep": {"business_key": "wafer", "composite_key_source": ["wafer"],
                  "column_types": {"wafer": "string", "fl": "string"}},
}
SUMMARY_ROWS = [{"wafer": "W1", "leg": "L1", "item": "particle", "fail": 1, "total": 100},
                {"wafer": "W1", "leg": "L2", "item": "particle", "fail": 2, "total": 100},
                {"wafer": "W1", "leg": "L1", "item": "scratch", "fail": 0, "total": 100},
                {"wafer": "W2", "leg": "L1", "item": "particle", "fail": 3, "total": 100}]


def _report_declaration(**over):
    return dict({"name": "kinds_report", "on": {"table": "kinds_rep"}, "into": {"table": "kinds_rep"},
                 "derive": {"kind": "report", "report": {
                     "wafer": {"table": "kinds_wafer", "key": ["wafer", "leg"], "time": "at", "evaluation": "ev"},
                     "summary": {"table": "kinds_sum", "wafer": ["wafer", "leg"], "item": "item", "fail": "fail",
                                 "total": "total"},
                     "results": {"file": "fl"},
                     "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
                     "loop": {"steps": 3, "seconds": 60, "context_tokens": 16000}}}}, **over)


@pytest.fixture(name="reported")
def fixture_reported(db, tmp_path, monkeypatch):
    """The report kind's tables - wafers of two legs (W1: L1 · L2), the summary by (wafer, leg, item), the report table
    by wafer alone, its rows written as a file writes them (one event naming both) - the files kept in `tmp_path`.
    Yields the declaration's rules - one, on the report table."""
    import event_constants
    import paths
    from database.context import outbox_mode
    from conftest import retire_dynamic_model

    models.init_dynamic_models(REPORT_TABLES)
    crud.TABLE_CONFIG.update(REPORT_TABLES)
    for name in REPORT_TABLES:
        models.DYNAMIC_TABLES[name].__table__.create(bind=db.get_bind())
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    for table, rows in (("kinds_wafer", [{"wafer": "W1", "leg": "L1", "ev": "E1", "at": "1"},
                                         {"wafer": "W1", "leg": "L2", "ev": "E1", "at": "1"},
                                         {"wafer": "W2", "leg": "L1", "ev": "E1", "at": "2"}]),
                        ("kinds_sum", SUMMARY_ROWS),
                        ("kinds_rep", [{"wafer": "W1"}, {"wafer": "W2"}])):
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds") for row in rows]))
    db.commit()
    rules = rule_shape.expand_declaration(_report_declaration(), crud.TABLE_CONFIG)[0]
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
    return sorted((r.wafer, r.fl) for r in db.query(models.DYNAMIC_TABLES["kinds_rep"]).all())


def _summary(db):
    db.expire_all()
    model = models.DYNAMIC_TABLES["kinds_sum"]
    return sorted((r.wafer, r.leg, r.item, r.fail, r.total) for r in db.query(model).all())


def _done_model(monkeypatch):
    from utils import llm

    monkeypatch.setattr(llm, "ask_json", lambda prompt, usage=None: (
        {"done": {"summary": "particle is low."}} if "Tables read:" in prompt else {"done": {}}))


def test_a_report_declaration_writes_a_report_a_wafer_into_its_report_table(db, reported, monkeypatch):
    """The model stands in (no gateway in a test): it reads the summary table, says done, writes - each wafer's report
    row names its own file, one file a wafer whatever its legs (owner 10-23 «리포트는 wafer 하나지, leg 는 리포트
    내용에»), and the file ends with the steps it took (Evidence). The summary table is not written."""
    from utils import llm

    def model(prompt, usage=None):
        if "Tables read:" in prompt:
            return {"done": {"summary": "particle is low."}}
        return {"call": "yield_by", "args": {}} if "This is step 1 of" in prompt else {"done": {}}

    monkeypatch.setattr(llm, "ask_json", model)
    [rule] = reported

    assert rule["mapper"] == "declared:report"
    assert _door(rule) == "chain.dynamic_mappers._report"
    before = _summary(db)

    _run(db, "report", reported, "kinds_rep")

    rows = _report_rows(db)
    assert [w for w, _fl in rows] == ["W1", "W2"] and all(fl for _w, fl in rows), rows
    assert [os.path.basename(fl) for _w, fl in rows] == ["W1.html", "W2.html"], "a file a wafer, not a leg"
    w1, w2 = (open(fl, encoding="utf-8").read() for _w, fl in rows)
    assert "L1" in w1 and "L2" in w1 and "L2" not in w2, "W1's report holds both its legs as columns"
    assert "particle is low." in w1
    evidence = w1[w1.index('<details class="evidence">'):]
    assert "1 yield_by" in evidence and "2 done" in evidence and "3 write" in evidence, evidence
    assert '\n    particle | 1.0% (1/100) | 2.0% (2/100)' in evidence, \
        "each step's read under its line, not its head alone (lead 10-23)"
    assert _summary(db) == before, "the summary table is read, never written"


def test_a_report_without_a_model_writes_its_file_and_says_why_in_it(db, reported, monkeypatch):
    from utils import llm

    def refused(prompt, usage=None):
        raise llm.LlmRefused("no gateway in this test")

    monkeypatch.setattr(llm, "ask_json", refused)
    _run(db, "report-refused", reported, "kinds_rep")

    rows = _report_rows(db)
    why = "the language model call was refused: no gateway in this test"
    assert [w for w, _fl in rows] == ["W1", "W2"]
    assert all(why in open(fl, encoding="utf-8").read() for _w, fl in rows), "the file says why it stopped"


def _sent_reports(db, reported, monkeypatch, answers):
    """Both wafers' reports made with `send_to`, then the upkeep's sweep run once a list of answers: the post
    answers each in turn (None: taken). -> (the marker files after each sweep, the files posted)."""
    from chain import report_loop

    _done_model(monkeypatch)
    [rule] = reported
    rule["params"]["send_to"] = "http://relay.test/reports"
    _run(db, "report-send", reported, "kinds_rep")
    posted, after = [], [_marks(db)]
    for said in answers:
        def post(send_to, file_, said=said):
            posted.append((send_to, os.path.basename(file_)))
            return said
        report_loop.send_waiting([rule], post=post)
        after.append(_marks(db))
    return after, posted


def _marks(db):
    folder = os.path.dirname(_report_rows(db)[0][1])
    return sorted(name for name in os.listdir(folder) if not name.endswith(".html"))


def test_a_made_report_is_sent_to_its_address_by_the_upkeep(db, reported, monkeypatch):
    after, posted = _sent_reports(db, reported, monkeypatch, [None])
    assert after[0] == ["W1.html.send", "W2.html.send"], "made, not sent yet"
    assert after[1] == []
    assert sorted(posted) == [("http://relay.test/reports", "W1.html"), ("http://relay.test/reports", "W2.html")]


def test_a_send_that_fails_three_times_leaves_its_failure_beside_the_file(db, reported, monkeypatch):
    import json

    from chain import report_loop

    after, posted = _sent_reports(db, reported, monkeypatch, ["relay down"] * report_loop.SEND_TRIES)
    assert after[report_loop.SEND_TRIES - 1] == ["W1.html.send", "W2.html.send"], "tried again"
    assert after[-1] == ["W1.html.send_failed", "W2.html.send_failed"]
    folder = os.path.dirname(_report_rows(db)[0][1])
    assert json.load(open(os.path.join(folder, "W1.html.send_failed"), encoding="utf-8")) == {
        "rule": "kinds_report", "why": "relay down"}
    assert len(posted) == 2 * report_loop.SEND_TRIES
    _run_again = report_loop._mark                                   # a replay remakes the report: its marker again
    _run_again(os.path.join(folder, "W1.html"), "kinds_report")
    assert sorted(n for n in os.listdir(folder) if n.startswith("W1.html.")) == ["W1.html.send"]


def test_a_stopped_report_is_not_sent(db, reported, monkeypatch):
    from chain import report_loop
    from utils import llm

    def refused(prompt, usage=None):
        raise llm.LlmRefused("no gateway in this test")

    monkeypatch.setattr(llm, "ask_json", refused)
    [rule] = reported
    rule["params"]["send_to"] = "http://relay.test/reports"
    _run(db, "report-stopped", reported, "kinds_rep")
    posted = []
    report_loop.send_waiting([rule], post=lambda *a: posted.append(a))
    assert posted == [] and _marks(db) == []


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
    """Owner 10-23 «자동 시작은 막고 리플레이로» · «막아»: `enabled: false` is «nothing wakes it» - the report rows'
    event makes no report; a replay naming the rule (its events carry `only_rule`) makes one a wafer."""
    from database.database import stage_collapsed_event

    _done_model(monkeypatch)
    declaration = _report_declaration(enabled=False)
    declaration["derive"]["report"] = reported[0]["params"]
    stood, refusal, notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
    assert refusal is None and [r["enabled"] for r in stood] == [False], (refusal, notes)
    assert "nothing wakes it" in notes[0]

    _run(db, "report-off", stood, "kinds_rep")
    assert {fl for _w, fl in _report_rows(db)} == {None}

    model = models.DYNAMIC_TABLES["kinds_rep"]
    for event in _events(db, "kinds_rep"):
        db.delete(event)
    stage_collapsed_event(db, "EDIT", "kinds_rep", [r.row_id for r in db.query(model).all()],
                          only_rule="kinds_report", replay=True)
    db.commit()
    _run(db, "report-replayed", stood, "kinds_rep")
    assert [(w, os.path.basename(fl or "")) for w, fl in _report_rows(db)] == [("W1", "W1.html"), ("W2", "W2.html")]


def test_control_same_keeps_the_candidates_that_share_those_columns(db, reported):
    """Owner 10-23 «제품군도 필터링»: `control.same` names wafer-table columns a control candidate shares with the
    report's wafer - another value's evaluation leaves the candidates; empty filters nothing."""
    from chain import report_reads

    model = models.DYNAMIC_TABLES["kinds_wafer"]
    crud.apply_batch_updates(db, "kinds_wafer", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds")
        for row in ({"wafer": "W1", "leg": "L1", "at": "2026-10-20 10:00:00", "grp": "A"},
                    {"wafer": "W1", "leg": "L2", "at": "2026-10-20 10:00:00", "grp": "A"},
                    {"wafer": "W2", "leg": "L1", "at": "2026-10-20 11:00:00", "grp": "A"},
                    {"wafer": "P1", "leg": "L1", "ev": "E0", "at": "2026-10-10 10:00:00", "grp": "A"},
                    {"wafer": "Q1", "leg": "L1", "ev": "E9", "at": "2026-10-11 10:00:00", "grp": "B"})]))
    db.commit()
    assert db.query(model).count() == 5
    spec = dict(reported[0]["params"], control={"recent": {"evaluations": 5}})
    lines = report_reads.Report(db, spec, None, only={"wafer": "W1"}).candidates()["context"]
    assert "E0" in lines and "E9" in lines                            # canary: both are candidates unfiltered
    spec["control"]["same"] = ["grp"]
    assert report_shape.refusal(spec, "kinds_rep", "kinds_rep") is None
    lines = report_reads.Report(db, spec, None, only={"wafer": "W1"}).candidates()["context"]
    assert "E0" in lines and "E9" not in lines
    assert "not a column" in report_shape.refusal(dict(spec, control={"recent": {"days": 1}, "same": ["nope"]}),
                                                  "kinds_rep", "kinds_rep")


def test_a_wafer_in_two_evaluations_is_refused_by_name(db, reported):
    from chain import report_reads

    crud.apply_batch_updates(db, "kinds_wafer", schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"wafer": "W1", "leg": "L2", "ev": "E2"}, source_name="seed", updated_by="kinds")]))
    db.commit()
    with pytest.raises(report_reads.ReadRefused, match=r"wafer W1 is in 2 evaluations \(E1, E2\)"):
        report_reads.Report(db, reported[0]["params"], None, only={"wafer": "W1"})


def test_the_owners_long_conditions_and_chip_images_are_read_as_they_are(db, reported, tmp_path, monkeypatch):
    """Owner 10-23 box sample: conditions a row a condition (written only when out of the ordinary), a chip image row
    naming its defects «a, b», no evaluation column - the model reads each wafer's conditions or «default conditions»,
    a candidate is a wafer of the report table (its legs together), and a chip image is shown for each defect it holds."""
    from chain import report_html, report_reads
    from conftest import retire_dynamic_model

    more = {"kinds_cond": {"composite_key_source": ["wafer", "leg", "condition_id"],
                           "column_types": {"date": "string", "title": "string", "wafer": "string", "leg": "string",
                                            "condition_id": "string", "value": "string"}},
            "kinds_img": {"composite_key_source": ["wafer", "leg", "x", "y"],
                          "column_types": {"wafer": "string", "leg": "string", "x": "string", "y": "string",
                                           "img_path": "string", "including_defects": "string"}}}
    models.init_dynamic_models(more)
    crud.TABLE_CONFIG.update(more)
    for name in more:
        models.DYNAMIC_TABLES[name].__table__.create(bind=db.get_bind())
    try:
        # W2/L1: a condition named, its value not written (the owner's trap wafer), on a date written with its offset
        for table, rows in (("kinds_cond", [{"date": "2026-10-22 10:00:00", "title": "split eval", "wafer": "W1",
                                             "leg": "L1", "condition_id": "anneal", "value": "450C"},
                                            {"date": "2026-10-22T00:00:00+09:00", "title": "trap", "wafer": "W2",
                                             "leg": "L1", "condition_id": "bond", "value": ""},
                                            # W3/L1 later than W1, W3/L2 of no row: W3 one candidate, whole
                                            {"date": "2026-10-23 09:00:00", "title": "later", "wafer": "W3",
                                             "leg": "L1", "condition_id": "bond", "value": "300"}]),
                            ("kinds_img", [{"wafer": "W1", "leg": "L1", "x": "3", "y": "4", "img_path": "c.png",
                                            "including_defects": "particle, scratch"},
                                           {"wafer": "W1", "leg": "L1", "x": "5", "y": "5", "img_path": "d.png",
                                            "including_defects": "particle"},
                                           {"wafer": "W1", "leg": "L2", "x": "1", "y": "1", "img_path": "e.png",
                                            "including_defects": "particle"}]),
                            # both defects occurred on W1/L1 (a defect of no failing chip gets no image)
                            ("kinds_sum", [{"wafer": "W1", "leg": "L1", "item": "scratch", "fail": 2},
                                           {"wafer": "W2", "leg": "L2", "item": "scratch", "fail": 1},
                                           {"wafer": "W3", "leg": "L1", "item": "scratch", "fail": 1},
                                           {"wafer": "W3", "leg": "L2", "item": "scratch", "fail": 1}])):
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds") for row in rows]))
        db.commit()
        spec = dict(reported[0]["params"], wafer={"table": "kinds_sum", "key": ["wafer", "leg"]},
                    conditions={"table": "kinds_cond", "wafer": ["wafer", "leg"], "name": "condition_id",
                                "value": "value", "time": "date", "title": "title"},
                    images={"table": "kinds_img", "wafer": ["wafer", "leg"], "item": "including_defects",
                            "image": "img_path", "item_sep": ",", "source": "nowhere"},
                    control={"recent": {"evaluations": 5}})
        assert report_shape.refusal(spec, "kinds_rep", "kinds_rep") is None
        report = report_reads.Report(db, spec, None, only={"wafer": "W1"})
        assert report.evaluation == "W1", "no evaluation column: the report's own group is named by its wafer"
        said = report.conditions()["context"]
        assert "anneal: 450C 1" in said and "default conditions (no condition row): 1 wafers" in said, said
        lines = report.candidates()["context"].splitlines()
        assert lines[1:] == ["W3 · 2026-10-23 · 2 rows · title later · W3/L1: bond=300 · W3/L2: default conditions",
                             "W2 · 2026-10-22 · 2 rows · title trap · W2/L1: bond=(empty) · "
                             "W2/L2: default conditions"], \
            "a candidate is the report table's wafer, its legs together; its day the product zone's; a blank value " \
            "said; W3 later than W1 a candidate too (owner «빼지 마»), its legs one row of one date (lead 10-23)"
        assert report.candidates()["html"] is None and "candidates" not in report_shape.TABLE_FILLS, \
            "the candidates list table retired (owner 10-23 «CANDIDATE, DATE 이거»): the model's and the Evidence's"
        head = report_html._summary_table(report.yield_by()["html"], spec)
        assert head.count(">W1</th>") == 1 and '<th class="rpt-head">L1</th>' in head, \
            "a report of one wafer names it once over its legs (lead 10-23)"
        chosen = report.images()["html"]
        assert sorted(chosen) == ["particle", "scratch"], "the chip's image under each defect it holds"
        assert "image source 'nowhere' is not declared" in chosen["particle"][0]["refused"], \
            "read through the declared source - «<source>:<path>»"
        monkeypatch.setattr(report_reads, "_picture", lambda ref, px: {"src": ref})
        spec["images"] = dict(spec["images"], per_item=1)
        shown = report_reads.Report(db, spec, None, only={"wafer": "W1"}).images()["html"]
        assert [p["wafer"] for p in shown["particle"]] == ["W1/L1", "W1/L2"], \
            "per_item a leg - L2's chip too (lead 10-23: all three were L1's)"
    finally:
        db.rollback()
        for name in more:
            models.DYNAMIC_TABLES[name].__table__.drop(bind=db.get_bind())
            crud.TABLE_CONFIG.pop(name, None)
            retire_dynamic_model(name)
