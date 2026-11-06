# -*- coding: utf-8 -*-
"""The admin help (소유자 10-23 「추천대로」, 총괄 e33713863): a question -> one tool of the catalog, its fields as the
tool's own `validate` reads them, and the tool's own count; it never runs anything.

  the model names a tool and fields          the answer: tool · fields · `retroactive.count`'s answer · help_id · a row
  a required field the question leaves out   not refused (lead 10-29): `unfilled` names it, the count says it cannot count
  a group of which one is needed («one_of»)  the same: «one of: tables, rules, transactions»; the run refuses it in the
                                             tool's own words
  every field given                          the operation's own judgement runs - a rule that does not exist is refused
  the run's doors                            judge whole: validate · count · publish refuse a blank required field
  the tool's name                            its key, its key in another case, its label - nothing else
  an answer that is not JSON                 asked once more with that sentence
  a tool outside the list · a wrong field    asked once more with the refusal in the prompt; no tool -> «named no tool»
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
    assert "doors" not in got, "a tool with no doors carries none"
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
    asked = _model(monkeypatch, {"op": "chain_replay", "params": {"pace": "warp"}},
                   {"op": "set_aside", "params": {"tables": "t", "colour": "red"},
                    "similar": ["withdraw", "no_such_tool", "set_aside", "withdraw"]})
    got = _ask(client, "이거 멈춰").json()
    assert got["op"] is None and got["count"] is None and got["tries"] == 2 and got["unfilled"] == []
    assert "'chain_replay' parameter 'pace' must be one of" in asked[1], "a field given is judged"
    assert "unknown parameter(s) for 'set_aside': ['colour']" in got["refused"]
    assert got["similar"] == [{"op": op, "label": retroactive.OPERATIONS[op]["label"]} for op in ("withdraw", "set_aside")]


def test_a_required_field_the_question_leaves_out_is_left_for_the_form(client, monkeypatch):
    """lead 10-29 - 18 of 19 operations need a field a question seldom says; the help answered «not sure» to them"""
    asked = _model(monkeypatch, {"op": "set_aside", "params": {"tables": "t1"}, "why": "w"})
    got = _ask(client, "이거 멈춰").json()
    assert (got["op"], got["params"], got["unfilled"], got["tries"], got["refused"]) == (
        "set_aside", {"tables": ["t1"]}, ["reason"], 1, None)
    assert (got["count"], got["count_refused"]) == (None, "the count waits for: reason")
    assert len(asked) == 1


def test_a_count_with_blank_fields_is_not_asked_and_says_what_it_waits_for(client, monkeypatch):
    """lead 10-29 - a blank field is expected here; the count is not asked and no code place reaches the operator"""
    monkeypatch.setattr(retroactive, "count", lambda *a, **k: pytest.fail("the count was asked with blank fields"))
    _model(monkeypatch, {"op": "set_aside", "params": {}, "why": "w"})
    got = _ask(client, "이거 멈춰").json()
    assert (got["count"], got["count_refused"]) == (
        None, "the count waits for: reason, one of: tables, rules, transactions")


def test_a_group_of_which_one_is_needed_is_a_blank_field_too(client, monkeypatch):
    _model(monkeypatch, {"op": "rerun_set_aside", "params": {}, "why": "w"})
    got = _ask(client, "치워 둔 사건을 이제 돌려").json()
    assert (got["op"], got["params"], got["unfilled"]) == ("rerun_set_aside", {}, ["one of: tables, rules, transactions"])
    assert got["count_refused"] == "the count waits for: one of: tables, rules, transactions"
    assert retroactive.unfilled("set_aside", {}) == ["reason", "one of: tables, rules, transactions"]
    assert retroactive.unfilled("set_aside", {"rules": ["r"], "reason": "x"}) == []


@pytest.mark.parametrize("op, params, said", [
    ("set_aside", {"reason": "r"}, "'set_aside' needs at least one of tables, rules, transactions - setting aside "
                                   "the whole queue is not something a form should do in one click"),
    ("rerun_set_aside", {}, "'rerun_set_aside' needs at least one of tables, rules, transactions - running every "
                            "set-aside event again is not something a form should do in one click"),
])
def test_the_run_refuses_a_tool_with_none_of_its_group_in_its_own_words(db_session, op, params, said):
    for door in (lambda: retroactive.validate(op, params), lambda: retroactive.count(db_session, op, params),
                 lambda: retroactive.publish(db_session, op, params)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            door()
        assert str(refused.value) == said


def test_every_field_given_is_judged_by_the_operation_itself(client, monkeypatch):
    _model(monkeypatch, {"op": "set_aside", "params": {"rules": "no_such_rule", "reason": "r"}},
           {"op": "set_aside", "params": {"rules": "no_such_rule", "reason": "r"}})
    got = _ask(client, "그 규칙 멈춰").json()
    assert got["op"] is None and "no chain rule is declared under ['no_such_rule']" in got["refused"]


def test_the_runs_own_doors_judge_whole(db_session):
    """the partial judgement is the help's alone: the form's run, its count and the queue refuse a blank required field"""
    import ast
    import pathlib

    said = "'set_aside' requires parameter 'reason'"
    for door in (lambda: retroactive.validate("set_aside", {"tables": "t1"}),
                 lambda: retroactive.count(db_session, "set_aside", {"tables": "t1"}),
                 lambda: retroactive.publish(db_session, "set_aside", {"tables": "t1"})):
        with pytest.raises(retroactive.RetroactiveRefused, match=said):
            door()
    server = pathlib.Path(__file__).resolve().parents[1]
    partial = sorted(str(path.relative_to(server)).replace(os.sep, "/") for path in server.rglob("*.py")
                     if "tests" not in path.parts and "partial=True" in path.read_text(encoding="utf-8")
                     for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                     if isinstance(node, ast.Call) and any(k.arg == "partial" for k in node.keywords)
                     and getattr(node.func, "attr", getattr(node.func, "id", None)) == "validate")
    assert partial == ["admin/help.py"]


@pytest.mark.parametrize("said, named, refused", [
    ("chain_replay", "chain_replay", None),
    ("CHAIN_REPLAY", "chain_replay", None),
    ("Replay chain rules over old data (R1)", "chain_replay", None),
    ("`chain_replay`", None, "'`chain_replay`' is not a tool in the list"),
    (None, None, "the model named no tool"),
    ("", None, "the model named no tool"),
])
def test_the_tool_is_named_by_its_key_its_key_in_any_case_or_its_label(monkeypatch, said, named, refused):
    answers = [{"op": said, "params": {}}] * 2
    got = admin_help.pick("q", lambda prompt, system=None: answers.pop())
    assert (got["op"], got["refused"]) == (named, refused)


def test_an_answer_that_is_not_json_is_asked_again_with_its_sentence(monkeypatch):
    asked = []

    def ask_json(prompt, system=None):
        asked.append(prompt)
        if len(asked) == 1:
            raise llm.LlmNotAnObject('the answer is not JSON: {"op": "chain_re', '{"op": "chain_re')
        return {"op": "fold_withdrawal_events", "params": {}}

    got = admin_help.pick("q", ask_json)
    assert (got["op"], got["tries"], len(got["seconds"])) == ("fold_withdrawal_events", 2, 2)
    assert 'Your last answer was refused: the answer is not JSON: {"op": "chain_re' in asked[1]


def test_a_tool_with_doors_answers_with_them_and_their_pages(client, monkeypatch):
    """lead 10-29: the screen draws the answer's doors, a button where one has `open`; the answer's other cells stay"""
    _model(monkeypatch, {"op": "formula_column", "params": {}, "why": "a formula", "similar": ["read_files_again"]})
    got = _ask(client, "수식은 어디서 적어?").json()
    assert got["doors"] == retroactive.DOORS_OUTSIDE["formula_column"]["doors"]
    assert got["doors"][0]["open"] == {"label": "Open the grid", "href": "index.html"}
    assert [door["name"] for door in got["doors"] if "open" not in door] == ["preview", "save", "remove"]
    assert (got["op"], got["params"], got["why"], got["label"], got["count"], got["count_refused"], got["tries"]) == (
        "formula_column", {}, "a formula", "Compute a column from a formula", None, None, 1)
    assert got["similar"] == [] and got["refused"] is None and got["help_id"]


def test_the_help_runs_nothing(client, monkeypatch):
    def no_run(*a, **k):
        raise AssertionError("the help reached publish")
    monkeypatch.setattr(retroactive, "publish", no_run)
    _model(monkeypatch, {"op": "rerun_set_aside", "params": {"tables": "t1"}, "why": "w"})
    assert _ask(client, "다시 돌려줘").json()["op"] == "rerun_set_aside"
    # the help's one door that is not a read is the ask; its other doors only read (the Guide, owner 11-06 4f55adfe1)
    paths = {route.path: route.methods for route in client.app.routes if route.path.startswith("/admin/help")}
    assert "/admin/help/ask" in paths and len(paths) > 1, paths                      # canary: a read door is seen
    assert {path: methods for path, methods in paths.items() if methods - {"GET", "HEAD"}} == {
        "/admin/help/ask": {"POST"}}, paths


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
    """A fake model naming each question's own tool with no fields - the path, not the model's quality: every
    question is a hit (lead 10-29: 18 -> 56 -> 58 of 58)."""
    from scripts.help_bench import bench

    catalog = admin_help.catalog()
    owner = {question: tool for tool, spec in catalog.items() for question in spec["examples"]}
    said = bench(ask_json=lambda prompt, system=None: {
        "op": owner[prompt.rsplit("Question: ", 1)[1].split("\n\nYour last answer")[0]], "params": {}})
    assert said["asked"] == len(owner) > 20 and len(said["seconds"]) >= said["asked"]
    assert said["misses"] == [] and said["hit"] == said["asked"]


def test_the_bench_counts_a_failed_ask_as_its_miss_and_goes_on_and_stops_at_its_limit():
    from scripts.help_bench import bench

    def ask_json(prompt, system=None):
        raise llm.LlmCallFailed("the language model call failed: 400 context length")

    said = bench(ask_json=ask_json, limit=3)
    assert said["asked"] == 3 and said["hit"] == 0
    assert [picked.split(" (")[0] for _tool, _q, picked in said["misses"]] == [
        "LlmCallFailed: the language model call failed: 400 context length"] * 3


@pytest.fixture(autouse=True)
def _no_token(monkeypatch):
    monkeypatch.delenv(auth.ADMIN_TOKEN_ENV, raising=False)
