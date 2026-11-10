# -*- coding: utf-8 -*-
"""Lead 11-10 (owner «도우미 ㄴ»): the operator asks the help «why is it slow» - the same help answers it as it answers a
declaration (one tool of the catalog, the same guides answer), with the server's own last readings numbered beside the
guide sections: the last STALL line and its request's [Slow] line, the last slow requests', /health's problems. The
answer cites readings by number as it cites sections by name; one it was not given is dropped and counted. Nothing is
run, nothing is collected for it."""
import json
import os
import shutil

import pytest

import paths
from admin import help as admin_help, help_guides
from database import models
from runtime import health, request_timing, stall_watch
from utils import llm

STALL = {"line": "STALL 12s P /tables/dt_log/data SELECT cell_sources 9s Lock:relation L0 T6/40 G0 D3/9s",
         "at": "2026-11-10T09:00:00+00:00", "slow": "[Slow] GET /tables/dt_log/data 200 - 12.1 s · layers 8.10 s"}


@pytest.fixture(name="guides")
def fixture_guides(tmp_path, monkeypatch):
    """A repository root of its own holding the guides (`help_guides.GUIDES`) as committed."""
    for guide in help_guides.GUIDES:
        os.makedirs(tmp_path / os.path.dirname(guide), exist_ok=True)
        shutil.copyfile(os.path.join(paths.REPO_ROOT, guide), tmp_path / guide)
    monkeypatch.setattr(paths, "REPO_ROOT", str(tmp_path))
    monkeypatch.setitem(help_guides._built, "stamp", None)
    return tmp_path


@pytest.fixture(name="readings")
def fixture_readings(monkeypatch):
    """The server's readings as the test sets them: the last STALL, the slow lines kept, /health's problems."""
    state = {"stall": dict(STALL), "problems": ["worker 'chain' is down (supervisor state: failed)"]}

    class Watch:
        last, last_key = None, None
    monkeypatch.setattr(stall_watch, "last", lambda: state["stall"])
    monkeypatch.setattr(request_timing, "_slow_said", type(request_timing._slow_said)())
    request_timing._slow_said[1] = ("2026-11-10T08:59:00+00:00", "[Slow] GET /admin/x 200 - 3.0 s")
    request_timing._slow_said[2] = ("2026-11-10T09:00:00+00:00", STALL["slow"])
    monkeypatch.setattr(health, "probe_outbox", lambda db: {"status": "ok"})
    monkeypatch.setattr(health, "compute_health", lambda *a, **k: ({"problems": list(state["problems"])}, 200))
    return state


def test_the_readings_are_the_last_stall_its_slow_line_the_last_slow_lines_and_health_s_problems(readings):
    assert admin_help.state_lines(None) == [
        "2026-11-10T09:00:00+00:00 " + STALL["line"], STALL["slow"],
        "2026-11-10T08:59:00+00:00 [Slow] GET /admin/x 200 - 3.0 s",
        "/health: worker 'chain' is down (supervisor state: failed)"]


def test_no_stall_no_slow_line_and_a_healthy_server_give_no_readings(readings):
    readings["stall"], readings["problems"] = None, []
    request_timing._slow_said.clear()
    assert admin_help.state_lines(None) == []


def test_the_operations_tool_is_one_more_entry_of_the_catalog():
    prompt = admin_help.prompt_of("q")
    assert "- operations: Why it is slow - what to do - for when the operator asks why" in prompt
    assert "지금 왜 느려" in prompt
    assert '"search": only for the tools declaration and operations' in admin_help.SYSTEM


def test_the_readings_are_numbered_beside_the_sections_and_a_declaration_carries_none(guides):
    pieces = help_guides.nearest("규칙 끄기")[0]
    asked = help_guides.prompt_of("왜 느려", pieces, ["a", "b"])
    assert "\n\nServer readings:\n[1] a\n[2] b\n\nQuestion: 왜 느려" in asked
    assert "Server readings" not in help_guides.prompt_of("왜 느려", pieces)


def test_a_reading_or_a_section_the_answer_names_that_it_was_not_given_is_dropped(guides):
    given = help_guides.nearest("느려")[0][0]["name"]
    systems = []

    def ask_json(prompt, system=None):
        systems.append(system)
        return {"answer": "dt_log 의 읽기가 자물쇠를 기다림", "lines": [2, 9, 2, True], "why": "w",
                "sections": [given, "Invented"]}
    said = help_guides.answer("왜 느려", "느려", ask_json, form="operations", lines=["one", "two"])
    assert systems == [help_guides.OPERATIONS_SYSTEM]
    assert (said["answer"], said["lines"], said["dropped_lines"]) == ("dt_log 의 읽기가 자물쇠를 기다림", ["two"], 1)
    assert (said["sections"], said["dropped_sections"]) == ([given], 1) and "check" not in said and "declaration" not in said
    [cited] = said["cited_sections"]
    opened = {g["file"]: [s["path"] for s in g["sections"]] for g in help_guides.reader()}
    assert cited["name"] == given and cited["path"] in opened[cited["file"]], "the Guide reader opens it by file and path"


def test_the_help_answers_why_it_is_slow_in_the_tools_envelope(client, db_session, guides, readings, monkeypatch):
    prompts = []

    def ask_json(prompt, system=None):
        prompts.append(prompt)
        if prompt.startswith("Tools:"):
            return {"op": "operations", "params": {"x": 1}, "why": "asks why it is slow", "search": "굳음 STALL"}
        return {"answer": "P 요청이 Lock:relation 을 9 초 기다림", "lines": [1, 2], "sections": [], "why": "w"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    got = client.post("/admin/help/ask", json={"question": "지금 왜 느려"}).json()
    assert (got["op"], got["label"], got["params"], got["count"], got["refused"]) == (
        "operations", "Why it is slow - what to do", {}, None, None)
    assert got["operations"]["lines"] == ["2026-11-10T09:00:00+00:00 " + STALL["line"], STALL["slow"]]
    assert "[1] 2026-11-10T09:00:00+00:00 STALL 12s" in prompts[1] and "[4] /health: worker 'chain'" in prompts[1]
    row = db_session.query(models.AdminHelpAsk).filter(models.AdminHelpAsk.id == got["help_id"]).one()
    assert (row.op, json.loads(row.params), row.refused) == ("operations", {}, None)


def test_with_no_readings_the_answer_is_asked_without_any(client, guides, readings, monkeypatch):
    """«모름» is the model's to say (OPERATIONS_SYSTEM; the box's model is measured on the board) - the prompt must
    not hand it a reading to guess from."""
    readings["stall"], readings["problems"] = None, []
    request_timing._slow_said.clear()
    prompts = []

    def ask_json(prompt, system=None):
        prompts.append(prompt)
        return ({"op": "operations", "params": {}, "search": "느려"} if prompt.startswith("Tools:")
                else {"answer": "not known from the readings", "lines": [1], "sections": []})

    monkeypatch.setattr(llm, "ask_json", ask_json)
    got = client.post("/admin/help/ask", json={"question": "왜 느려"}).json()
    assert "Server readings" not in prompts[1]
    assert (got["operations"]["lines"], got["operations"]["dropped_lines"]) == ([], 1)
