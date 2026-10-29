# -*- coding: utf-8 -*-
"""The admin help's declaration answer (owner 10-29 «선언법도 도우미에», lead): the guides cut into sections, the
nearest three to the model's guide-worded search, one declaration written from them, and the save's own judgement of
it with nothing written.

    seat                         gate
    cut                          headings · numbered items · a long table split with its header; the Status line and
                                 the retired SENTENCES out, the current rule on their line kept
    index                        cut again only when a guide changed (stat); a missing guide said by name
    nearest · prompts            the owner's question finds the pair; the declaration prompt and the first ask's
                                 growth under their caps
    answer                       a section the pieces do not name is dropped and counted
    check                        chain rule · table: judged, the file unchanged; refused in the save's words; a kind
                                 outside the three or no name -> not checked; ledger: an existing path judged, an
                                 absent one not checked, no draft written
    /admin/help/ask              the declaration in the tools' envelope; its row
    help_bench --part declarations   cited · checked counted; a right section the guides lost said first
"""
import json
import os
import shutil

import pytest

import paths
from admin import help as admin_help, help_guides
from database import models
from utils import llm

PAIR = '{"<파생 칸>": "<원본 칸>"}'


@pytest.fixture(name="guides")
def fixture_guides(tmp_path, monkeypatch):
    """A repository root of its own holding the five guides as committed."""
    for guide in help_guides.GUIDES:
        os.makedirs(tmp_path / os.path.dirname(guide), exist_ok=True)
        shutil.copyfile(os.path.join(paths.REPO_ROOT, guide), tmp_path / guide)
    monkeypatch.setattr(paths, "REPO_ROOT", str(tmp_path))
    monkeypatch.setitem(help_guides._built, "stamp", None)
    return tmp_path


def test_a_guide_is_cut_at_its_headings_and_items_and_only_retired_sentences_go():
    table = "\n".join(["| cell | what |", "|---|---|"] + ["| `c%d` | %s |" % (n, "x" * 300) for n in range(12)])
    text = "\n".join(["# Guide", "> **Status:** Living · 직전 2026-09-01 (old)", "## 1. Rules",
                      "A current rule stays. ⚰️ The retired one goes. Another current one.",
                      "**① first item**", "item body", "## 2. Keys", table])
    pieces = help_guides.cut("docs/g.md", text)
    names = [p["name"] for p in pieces]
    assert names[:2] == ["g.md: Guide > 1. Rules", "g.md: Guide > 1. Rules > ① first item"]
    assert pieces[0]["text"] == "A current rule stays. Another current one."
    assert not any("Status" in p["text"] or "직전" in p["text"] for p in pieces)
    parts = [p for p in pieces if p["name"].startswith("g.md: Guide > 2. Keys")]
    assert len(parts) > 1 and all(p["text"].startswith("| cell | what |\n|---|---|") for p in parts)
    assert parts[-1]["name"] == "g.md: Guide > 2. Keys (part %d)" % len(parts)


def test_the_committed_guides_keep_their_current_rules_and_no_retired_sentence(guides):
    pieces = help_guides.index().pieces
    assert len(pieces) > 100
    assert not [p["name"] for p in pieces if help_guides._RETIRED.search(p["text"])]
    assert any("`derive.join` / `derive.decide`" in p["text"] for p in pieces), "the decide row is a current rule"
    assert any(PAIR in p["text"] and p["name"].startswith("enrichment_rules.md") for p in pieces)


def test_the_sections_are_cut_again_only_when_a_guide_changes(guides, monkeypatch):
    cuts, real = [], help_guides.cut
    monkeypatch.setattr(help_guides, "cut", lambda guide, text: cuts.append(guide) or real(guide, text))
    help_guides.index()
    help_guides.index()
    assert len(cuts) == len(help_guides.GUIDES)
    path = guides / help_guides.GUIDES[0]
    path.write_text(path.read_text(encoding="utf-8") + "\n## 99. New\nnew text\n", encoding="utf-8")
    assert any(p["name"].endswith("99. New") for p in help_guides.index().pieces)
    assert len(cuts) == 2 * len(help_guides.GUIDES)


def test_a_missing_guide_is_said_by_name_and_nothing_is_checked(guides):
    os.remove(guides / help_guides.GUIDES[1])
    said = help_guides.answer("q", "q", lambda *a, **k: pytest.fail("no ask without the guides"))
    assert said["refused"].startswith("guide not found: ") and help_guides.GUIDES[1].split("/")[-1] in said["refused"]
    assert "not_checked" in said["check"]


def _bench():
    with open(os.path.join(paths.SERVER_DIR, "scripts", "help_declaration_bench.json"), encoding="utf-8") as handle:
        return json.load(handle)["questions"]


def test_the_owners_question_finds_the_pair_and_every_prompt_stays_under_its_cap(guides):
    picked = help_guides.nearest("decide 판단 키 칸 이름이 원본 표와 파생 표에서 다를 때 짝")
    assert any(PAIR in p["text"] for p in picked)
    worst = 0
    for ask in _bench():
        pieces = help_guides.nearest(ask["question"])
        assert pieces and sum(help_guides.estimated_tokens(p["name"] + "\n" + p["text"]) for p in pieces) <= \
            help_guides.SECTION_TOKENS
        worst = max(worst, help_guides.estimated_tokens(help_guides.SYSTEM + help_guides.prompt_of(ask["question"], pieces)))
    assert worst <= 5000, worst


def test_the_first_ask_grows_by_the_declaration_entry_only():
    prompt = admin_help.prompt_of("q")
    mine = [line for line in prompt.split("\n") if line.startswith("- declaration:") or "디사이드 키" in line]
    assert len(mine) == 2 and sum(len(line) for line in mine) <= 700
    assert '"search": only for the tool declaration' in admin_help.SYSTEM


def _answering(sections, kind="chain_rule", name="help_probe", declaration=None):
    return lambda prompt, system=None: {"kind": kind, "name": name, "why": "w", "sections": sections,
                                        "declaration": declaration or {"enabled": False, "derive": {"kind": "banana"}}}


def test_a_section_the_model_names_that_was_not_given_is_dropped(guides, monkeypatch):
    monkeypatch.setattr(help_guides, "check", lambda *a: {"not_checked": "stub"})
    given = help_guides.nearest("규칙 끄기")[0]["name"]
    said = help_guides.answer("규칙 끄기", "규칙 끄기", _answering([given, "chain_rules.md: 9. Invented", given]))
    assert (said["sections"], said["dropped_sections"]) == ([given], 1)


@pytest.fixture(name="config_files")
def fixture_config_files(tmp_path, monkeypatch):
    from chain import ingestion_worker
    from tests.support.declaration import use_committed_declaration

    root = use_committed_declaration(monkeypatch, tmp_path)
    rules = root / "chain_rules.json"
    rules.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(ingestion_worker, "RULES_PATH", str(rules))
    return root


def _unchanged(root):
    return {name: (root / name).read_bytes() for name in ("chain_rules.json", "table_config.json")}


@pytest.mark.parametrize("kind, name, declaration, said", [
    ("chain_rule", "help_probe", {"enabled": False, "on": {"table": "nope"}, "derive": {"kind": "banana"}},
     "unknown derive kind 'banana'"),
    ("table", "help_probe_table", {"column_types": ["not", "an", "object"]}, "column_types must be a JSON object"),
])
def test_a_declaration_is_refused_in_the_saves_words_and_nothing_is_written(config_files, kind, name, declaration,
                                                                            said):
    before = _unchanged(config_files)
    got = help_guides.check(kind, name, declaration)
    assert got["ok"] is False and said in got["said"]
    assert _unchanged(config_files) == before


def test_a_declaration_the_save_takes_is_checked_ok_and_nothing_is_written(config_files, monkeypatch):
    from chain import formula
    from tests.support.declaration import use_committed_catalogue

    use_committed_catalogue(monkeypatch)
    before = _unchanged(config_files)
    files = sorted(os.listdir(config_files))
    assert help_guides.check("table", "help_probe_table", {"column_types": {"k": "string"}, "business_key": "k"}) == {
        "ok": True, "said": None}
    rule = formula.to_declaration("dt_log", "c_wx", "=[b_wx]*2")
    assert help_guides.check("chain_rule", rule["name"], rule)["ok"] is True
    assert _unchanged(config_files) == before and sorted(os.listdir(config_files)) == files, "no backup either"


@pytest.fixture(name="ledger")
def fixture_ledger(config_files, monkeypatch):
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger_api import ontology_config_explorer_router as explorer_router

    service = OntologyExplorerService(config_root=paths.config_path("ontology"))
    monkeypatch.setitem(explorer_router._services, None, service)
    return service


@pytest.mark.parametrize("kind, name, declaration, why", [
    ("csv", "x", {}, "unknown declaration kind 'csv'"),
    (None, "x", {}, "unknown declaration kind None"),
    ("chain_rule", "", {}, "the answer gave no name and declaration object to check"),
    ("table", "t", "not an object", "the answer gave no name and declaration object to check"),
    ("ledger", "sources.no_such_source", {}, "the ledger declaration has no 'sources.no_such_source' to check"),
])
def test_what_cannot_be_checked_is_said_not_checked(ledger, kind, name, declaration, why):
    got = help_guides.check(kind, name, declaration)
    assert set(got) == {"not_checked"} and why in got["not_checked"]


def test_a_ledger_declaration_at_an_existing_path_is_judged_by_the_draft_preview_and_no_draft_is_written(ledger):
    setup, index, _hash = ledger.active()
    node = next(n for n in index.nodes.values() if n.bundle_path and n.bundle_path[0] == "sources")
    path = ".".join(str(part) for part in node.bundle_path)
    raw = setup.bundle.to_mapping()
    for part in node.bundle_path:
        raw = raw[part]
    drafts = lambda: sorted(os.listdir(ledger.draft_store.root)) if ledger.draft_store.root.exists() else []  # noqa
    before = drafts()
    assert help_guides.check("ledger", path, raw)["ok"] is True
    broken = help_guides.check("ledger", path, dict(raw, read="not a read"))
    assert broken["ok"] is False and broken["said"]
    assert drafts() == before, "the preview judges; no draft is written"


def test_the_help_answers_a_declaration_in_the_tools_envelope(client, db_session, guides, monkeypatch):
    answers = [{"op": "declaration", "params": {}, "why": "asks how to write a rule",
                "search": "decide 판단 키 칸 이름이 원본 표와 파생 표에서 다를 때 짝"}]
    sections = []

    def ask_json(prompt, system=None):
        if answers:
            return answers.pop(0)
        sections.extend(line[3:] for line in prompt.split("\n") if line.startswith("## "))
        return {"kind": "csv", "name": "x", "declaration": {}, "why": "w", "sections": sections[:1]}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    got = client.post("/admin/help/ask", json={"question": "디사이드 키 다른거 어케하더라"}).json()
    assert (got["op"], got["label"], got["count"], got["unfilled"], got["refused"]) == (
        "declaration", "Write a declaration", None, [], None)
    said = got["declaration"]
    search = "decide 판단 키 칸 이름이 원본 표와 파생 표에서 다를 때 짝"
    assert sections == [p["name"] for p in help_guides.nearest(search)], "the model's search picks the sections"
    assert sections != [p["name"] for p in help_guides.nearest("디사이드 키 다른거 어케하더라")], "canary"
    assert said["sections"] == sections[:1] and said["dropped_sections"] == 0
    assert said["check"] == {"not_checked": "unknown declaration kind 'csv' - one of chain_rule, table, ledger"}
    assert got["params"] == {"kind": "csv", "name": "x"} and "search" not in got
    row = db_session.query(models.AdminHelpAsk).filter(models.AdminHelpAsk.id == got["help_id"]).one()
    assert (row.op, json.loads(row.params)) == ("declaration", {"kind": "csv", "name": "x"})


def test_the_bench_counts_cited_sections_and_says_a_right_section_the_guides_lost(guides, monkeypatch, tmp_path):
    from scripts import help_bench

    asks = _bench()
    lost = dict(asks[0], section="a section no guide has")
    bench_file = tmp_path / "bench.json"
    bench_file.write_text(json.dumps({"questions": [lost] + asks[1:4]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(help_bench, "DECLARATIONS", str(bench_file))
    state = {}

    def ask_json(prompt, system=None):
        if prompt.startswith("Tools:"):
            state["q"] = prompt.rsplit("Question: ", 1)[1]
            return {"op": "declaration", "params": {}, "search": state["q"]}
        given = [line[3:] for line in prompt.split("\n") if line.startswith("## ")]
        right = next(a["section"] for a in asks if a["question"] == state["q"])
        cited = [name for name in given if right in name or right in prompt.split("## " + name, 1)[1][:3000]]
        return {"kind": "table", "name": "t", "declaration": "no", "sections": cited[:1]}

    said = help_bench.bench_declarations(ask_json)
    assert said["absent"] == [(lost["question"], "a section no guide has")]
    assert said["asked"] == 3 and said["not_checked"] == 3 and said["ok"] == said["refused"] == 0
    assert said["cited"] + len(said["misses"]) == 3 and said["cited"] >= 1
