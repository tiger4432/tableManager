# -*- coding: utf-8 -*-
"""The admin help (소유자 10-23 「추천대로」, 총괄 e33713863): a question -> one tool of the catalog, its fields as the
tool's own `validate` reads them, and the tool's own count; it never runs anything.

  the model names a tool and fields          the answer: tool · fields · `retroactive.count`'s answer · help_id · a row
  a tool outside the list · a wrong field    asked once more with the refusal in the prompt
  still refused                              op None, the refusal, up to three tools of the list it named near
  the help                                   no route under /admin/help runs, and `publish` is never reached
  a run the form opened with help_id         its run_id on that ask's row; without help_id the same answer as before
  the bench (scripts/help_bench.py)          every example asked, the hits counted - a fake model here, the path only
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import auth, help as admin_help, retroactive  # noqa: E402
from database import models  # noqa: E402
from utils import llm  # noqa: E402

TOKEN = "correct-horse-battery-staple"


def _model(monkeypatch, *answers):
    """The model answers these, in turn; -> the prompts it was asked."""
    asked, left = [], list(answers)

    def ask_json(prompt, *, system=None, usage=None):
        asked.append(prompt)
        return left.pop(0)
    monkeypatch.setattr(llm, "ask_json", ask_json)
    return asked


def _ask(client, question):
    return client.post("/admin/help/ask", json={"question": question})


def test_a_question_gets_one_tool_its_fields_and_its_own_count(client, db_session, monkeypatch):
    asked = _model(monkeypatch, {"op": "rerun_set_aside", "params": {"tables": "t1"}, "why": "set aside earlier"})
    r = _ask(client, "어제 옆으로 뺀 거 다시 돌려줘")
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["op"], got["params"], got["tries"], got["refused"]) == ("rerun_set_aside", {"tables": ["t1"]}, 1, None)
    own = retroactive.count(db_session, "rerun_set_aside", {"tables": "t1"})
    assert got["count"]["affected"] == own["affected"] and got["count"]["detail"] == own["detail"]
    assert "Tools:" in asked[0] and "- rerun_set_aside:" in asked[0] and "read_files_again" in asked[0]
    row = db_session.query(models.AdminHelpAsk).filter(models.AdminHelpAsk.id == got["help_id"]).one()
    assert (row.op, row.tries, row.asked_by, row.run_id, row.question) == (
        "rerun_set_aside", 1, None, None, "어제 옆으로 뺀 거 다시 돌려줘")


def test_a_tool_outside_the_list_is_asked_again_with_its_refusal(client, monkeypatch):
    asked = _model(monkeypatch, {"op": "drop_everything", "params": {}},
                   {"op": "rerun_set_aside", "params": {"tables": "t1"}, "why": "w"})
    got = _ask(client, "다 날려줘").json()
    assert (got["op"], got["tries"]) == ("rerun_set_aside", 2)
    assert "'drop_everything' is not a tool in the list" in asked[1] and "Your last answer" not in asked[0]


def test_a_wrong_field_twice_is_not_sure_and_names_tools_of_the_list_only(client, monkeypatch):
    asked = _model(monkeypatch, {"op": "set_aside", "params": {"tables": "t"}},
                   {"op": "set_aside", "params": {"tables": "t", "colour": "red"},
                    "similar": ["withdraw", "no_such_tool", "set_aside", "withdraw"]})
    got = _ask(client, "이거 멈춰").json()
    assert got["op"] is None and got["count"] is None and got["tries"] == 2
    assert "requires parameter 'reason'" in asked[1]
    assert "unknown parameter(s) for 'set_aside': ['colour']" in got["refused"]
    assert got["similar"] == ["withdraw", "set_aside"]


def test_the_help_runs_nothing(client, monkeypatch):
    def no_run(*a, **k):
        raise AssertionError("the help reached publish")
    monkeypatch.setattr(retroactive, "publish", no_run)
    _model(monkeypatch, {"op": "rerun_set_aside", "params": {"tables": "t1"}, "why": "w"})
    assert _ask(client, "다시 돌려줘").json()["op"] == "rerun_set_aside"
    paths = {route.path: route.methods for route in client.app.routes if route.path.startswith("/admin/help")}
    assert paths == {"/admin/help/ask": {"POST"}}


def test_a_run_opened_from_an_answer_is_written_on_its_ask(client, db_session, monkeypatch):
    monkeypatch.setenv(auth.ADMIN_TOKEN_ENV, TOKEN)
    headers = {auth.ADMIN_TOKEN_HEADER: TOKEN}
    _model(monkeypatch, {"op": "rerun_set_aside", "params": {"tables": "t1"}, "why": "w"})
    help_id = client.post("/admin/help/ask", json={"question": "q"}, headers=headers).json()["help_id"]

    params = {"tables": "t1"}
    with_help = client.post("/admin/retroactive/rerun_set_aside/run", json={"params": params, "help_id": help_id},
                            headers=headers)
    without = client.post("/admin/retroactive/rerun_set_aside/run", json={"params": params}, headers=headers)

    assert with_help.status_code == without.status_code == 200
    assert set(with_help.json()) == set(without.json()) and with_help.json()["status"] == "queued"
    db_session.expire_all()
    runs = {row.id: row.run_id for row in db_session.query(models.AdminHelpAsk)}
    assert runs == {help_id: with_help.json()["run_id"]}


def test_the_bench_asks_every_example_and_counts_the_hits():
    """A fake model naming each question's own tool with no fields: the tools that need no field are hits, the rest
    are refused by their own validate and counted as misses - the path, not the model's quality."""
    from scripts.help_bench import bench

    catalog = admin_help.catalog()
    owner = {question: tool for tool, spec in catalog.items() for question in spec["examples"]}

    def named(tool):
        try:
            return tool in retroactive.DOORS_OUTSIDE or retroactive.validate(tool, {}) is not None
        except retroactive.RetroactiveRefused:
            return False

    said = bench(ask_json=lambda prompt, system=None: {
        "op": owner[prompt.rsplit("Question: ", 1)[1].split("\n\nYour last answer")[0]], "params": {}})
    assert said["asked"] == len(owner) > 20 and len(said["seconds"]) >= said["asked"]
    assert said["hit"] == sum(1 for tool in owner.values() if named(tool)) > 0
    assert {tool for tool, _q, _picked in said["misses"]} == {tool for tool in owner.values() if not named(tool)}


@pytest.fixture(autouse=True)
def _no_token(monkeypatch):
    monkeypatch.delenv(auth.ADMIN_TOKEN_ENV, raising=False)
