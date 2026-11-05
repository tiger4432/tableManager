# -*- coding: utf-8 -*-
"""Owner 11-05 «리포트 짓는 중 상태가 보이게» (총괄 ㄱ): the AI report a chain group builds now rides its group's claim -
nothing is written to a table - and /health's chain state says it (`chain_state.why.report`).

  steps    `run` says it as it moves: asking the model, reading <call>, each step as it ends (n, call, why, result,
           seconds, refused), writing the report - the beat file written at once each time (`WRITTEN_AT_ONCE`)
  wafers   `answer`: the wafers after this one queued; the next wafer its own; the batch over - none
  read     `runtime.running.work_facts` -> `chain_state_of`'s why: the report, its seconds as of the read
  log      each step's line the moment it ends - `step_line`, «[Report] <rule> wafer <w> step n/cap <call> - why …»
"""
import json
import logging
import time

import pytest

import event_constants
from chain import report_loop
from runtime import running
from test_a_report_loop_hands_the_model_its_context_and_stops import REQUEST, SPEC, Clock, FakeReport, Model
from utils import heartbeat


@pytest.fixture(name="claim")
def fixture_claim():
    """A chain group's claim - its beat file in the session's own beat directory (conftest), never the live tree."""
    cm = heartbeat.work_claim("chain", "tx report", acted_on=True)
    cm.__enter__()
    try:
        yield
    finally:
        cm.__exit__(None, None, None)


def _on_file():
    """The report as the chain's beat file holds it now - read from disk."""
    with open(heartbeat.heartbeat_path("chain"), encoding="utf-8") as handle:
        return (json.load(handle)["work"].get("oldest_facts") or {}).get("report")


def _live(wafer="L1/W1", queued=()):
    return {"rule": "rc_eval", "table": "eval_report", "wafer": wafer, "keys": ["lot", "wafer"],
            "wafer_key": {"lot": wafer.split("/")[0], "wafer": wafer.split("/")[1]},
            "queued": list(queued), "queued_more": 0, "started": time.time(), "step": None, "doing": None}


#: The call as the steps spell it (`report_loop._said`).
CALL = report_loop._said("yield_by", {"wafers": "all"})


class Watching(FakeReport):
    """A read that looks at the beat file while it runs."""

    def __init__(self):
        super().__init__()
        self.during = None

    def yield_by(self, wafers=None, by=None):
        self.during = self.during or _on_file()                     # the model's read - the product's comes after
        return super().yield_by(wafers, by)


class WatchingModel(Model):
    """A model that looks at the beat file each time it is asked."""

    def __init__(self, *answers):
        super().__init__(*answers)
        self.seen = []

    def __call__(self, prompt, usage=None):
        self.seen.append(_on_file())
        return super().__call__(prompt, usage)


def test_each_step_is_on_the_claim_as_it_moves_and_its_line_logged_as_it_ends(claim, caplog):
    report, model = Watching(), WatchingModel(
        {"call": "yield_by", "args": {"wafers": "all"}, "why": "the rates by split"}, {"done": {}},
        {"done": {"summary": "Particle rose."}})
    live = _live()
    with caplog.at_level(logging.INFO, logger="Chain"):
        out = report_loop.run(report, SPEC, REQUEST, ask=model, clock=Clock(), live=live)
    assert out["state"] == report_loop.DONE and len(model.seen) == 3, "CANARY: two read steps and the write call"

    first, second, write = model.seen
    assert (first["step"], first["cap"], first["doing"], first["steps"]) == (1, 4, "asking the model", [])
    assert (first["seconds_cap"], first["tokens_cap"], first["wafer"], first["wafer_key"]) == (
        300, 16000, "L1/W1", {"lot": "L1", "wafer": "W1"})
    assert report.during["doing"] == "reading " + CALL and report.during["step"] == 1
    assert second["doing"] == "asking the model" and second["step"] == 2
    [one] = second["steps"]
    assert (one["n"], one["call"], one["why"], one["refused"]) == (1, CALL, "the rates by split", False)
    assert one["result"] == "[E1] W1 | W2" and one["seconds"] > 0 and second["tokens"] > 0
    assert write["doing"] == "writing the report" and [s["call"] for s in write["steps"]] == [
        CALL, "done", "product yield_by()"], "the product's own reads after the model's are steps too"
    assert [s["call"] for s in _on_file()["steps"]][-1] == "write", "the write call is a step on the claim too"

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Report] rc_eval wafer L1/W1 step")]
    assert lines[0] == ("[Report] rc_eval wafer L1/W1 step 1/4 " + CALL + " - why the rates by split -> "
                        "[E1] W1 | W2 (%.1f s)" % out["steps"][0]["seconds"])
    assert len(lines) == len(out["steps"]) and lines[-1].startswith("[Report] rc_eval wafer L1/W1 step 4 write - why - -> ")


def test_a_refused_read_is_a_refused_step_on_the_claim(claim):
    model = Model({"call": "pareto", "args": {}, "why": "fails"}, {"done": {}})
    report_loop.run(FakeReport(), SPEC, REQUEST, ask=model, clock=Clock(), live=_live())
    refused = _on_file()["steps"][0]
    assert refused["refused"] is True and refused["result"].startswith("refused: a pareto adds fail chips")


def test_the_chain_state_says_the_report_and_its_seconds_as_of_the_read(claim):
    live = _live(queued=[{"lot": "L1", "wafer": "W2"}])
    live["started"] = time.time() - 42
    report_loop._doing(live, "asking the model", 3)
    work = heartbeat.read_all()["chain"]["work"]
    said = event_constants.chain_state_of(False, None, running=running.work_facts(work))
    assert said["state"] == event_constants.CHAIN_STATE_RUNNING
    report = said["why"]["report"]
    assert (report["wafer"], report["step"], report["doing"], report["queued"]) == (
        "L1/W1", 3, "asking the model", [{"lot": "L1", "wafer": "W2"}])
    assert 42 <= report["elapsed_seconds"] < 60
    report_loop._tell(None)
    assert event_constants.chain_state_of(False, None, running=running.work_facts(
        heartbeat.read_all()["chain"]["work"]))["why"]["report"] is None


def test_answer_queues_the_wafers_after_this_one_and_clears_when_the_batch_is_over(claim, monkeypatch):
    seen = []

    def run(report, spec, request, ask=None, clock=None, live=None):
        seen.append(_on_file())
        return {"state": report_loop.STOPPED, "reason": "test", "steps": [], "texts": {}, "tables": {}}

    class Model_:
        pass

    rows = {"a": ("L1", "W1"), "b": ("L1", "W2"), "c": ("L1", "W2")}

    class Row:
        def __init__(self, row_id):
            self.row_id, (self.lot, self.wafer) = row_id, rows[row_id]

    class Query:
        def filter(self, *_):
            return self

        def all(self):
            return [Row(r) for r in rows]

    class Db:
        def query(self, _model):
            return Query()

    class Column:
        def in_(self, _ids):
            return None

    from chain import ask_rule, report_shape
    from database import models

    Model_.row_id = Column()
    monkeypatch.setitem(models.DYNAMIC_TABLES, "eval_report", Model_)
    monkeypatch.setattr(report_shape, "report_key", lambda spec, table: ["lot", "wafer"])
    monkeypatch.setattr(report_loop, "_this_wafer", lambda db, spec, wafer: (None, None))
    monkeypatch.setattr(ask_rule, "memory_lines", lambda *args: [])
    monkeypatch.setattr(report_loop, "run", run)
    report_loop.answer(Db(), {"name": "rc_eval", "trigger_table": "eval_report", "params": {}}, ["a", "b", "c"])

    first, second = seen
    assert (first["wafer"], first["keys"], first["wafer_key"], first["queued"], first["queued_more"]) == (
        "L1/W1", ["lot", "wafer"], {"lot": "L1", "wafer": "W1"}, [{"lot": "L1", "wafer": "W2"}], 0)
    assert (second["wafer_key"], second["queued"], second["queued_more"]) == ({"lot": "L1", "wafer": "W2"}, [], 0)
    assert "rows" not in first, "the screen finds the wafer's rows by keys and wafer_key (client 11-05)"


def test_the_claim_names_at_most_queued_shown_wafers_and_counts_the_rest(claim, monkeypatch):
    seen = []

    def run(report, spec, request, ask=None, clock=None, live=None):
        seen.append(_on_file())
        return {"state": report_loop.STOPPED, "reason": "test", "steps": [], "texts": {}, "tables": {}}

    rows = {"r%d" % n: ("L1", n) for n in range(4)}

    class Row:
        def __init__(self, row_id):
            self.row_id, (self.lot, self.wafer) = row_id, rows[row_id]

    class Query:
        def filter(self, *_):
            return self

        def all(self):
            return [Row(r) for r in rows]

    class Db:
        def query(self, _model):
            return Query()

    class Column:
        def in_(self, _ids):
            return None

    class Model_:
        row_id = Column()

    from chain import ask_rule, report_shape
    from database import models

    monkeypatch.setitem(models.DYNAMIC_TABLES, "eval_report", Model_)
    monkeypatch.setattr(report_shape, "report_key", lambda spec, table: ["lot", "wafer"])
    monkeypatch.setattr(report_loop, "_this_wafer", lambda db, spec, wafer: (None, None))
    monkeypatch.setattr(ask_rule, "memory_lines", lambda *args: [])
    monkeypatch.setattr(report_loop, "run", run)
    monkeypatch.setattr(report_loop, "QUEUED_SHOWN", 2)
    report_loop.answer(Db(), {"name": "rc_eval", "trigger_table": "eval_report", "params": {}}, list(rows))

    assert [(each["queued"], each["queued_more"]) for each in seen] == [
        ([{"lot": "L1", "wafer": 1}, {"lot": "L1", "wafer": 2}], 1),
        ([{"lot": "L1", "wafer": 2}, {"lot": "L1", "wafer": 3}], 0),
        ([{"lot": "L1", "wafer": 3}], 0), ([], 0)], "a number key stays a number - the grid's cell spelling"
    assert _on_file() is None, "the batch is over - no report building"


def test_a_date_or_decimal_key_rides_the_claim_as_its_text(claim):
    """A key the beat's JSON cannot carry (a date, a Decimal) goes as its text - else the claim's write fails and only
    a log line says so (C 11-05: the «else str» survived a mutant)."""
    import datetime
    import decimal

    class Row:
        day, lot = datetime.date(2026, 11, 5), decimal.Decimal("9.50")

    key = report_loop._key_of(Row(), ["day", "lot"])
    report_loop._tell(dict(_live(), keys=["day", "lot"], wafer_key=key, queued=[key]))
    on = _on_file()
    assert on is not None and (on["wafer_key"], on["queued"]) == (
        {"day": "2026-11-05", "lot": "9.50"}, [{"day": "2026-11-05", "lot": "9.50"}])
