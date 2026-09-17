# -*- coding: utf-8 -*-
"""판정 546 ③ · 548. 운영자가 «기존 평면 규칙»을 열어 통합으로 저장하고, «되돌릴» 수 있다.

> 총괄 2026-09-17 판정 548: 「㉡ 입니다 — 서버가 변환합니다. 화면은 «시킵니다».
>  그러면 운영자의 길이 게이트가 재는 그 변환기를 지납니다」

🔴 WHY THIS FILE EXISTS SEPARATELY FROM THE ROUND-TRIP GATE. 판정 539's gate scores
`rule_shape`'s converters directly; this one scores THE PATH AN OPERATOR WALKS - route,
payload keys, the stored file. Every defect between the two is invisible to that gate: a
body key read under another name, a conversion the route re-spells for itself, a save that
rewrites rules nobody asked about.

⚠️ AND IT NEVER TOUCHES THE OWNER'S FILE. `chain_rules.json` is `server/config/**`, which is
gitignored and the owner's; 2026-08-21 is the day a test of mine wrote one. 판정 547 put the
same requirement on today's acceptance walk, and it applies to an automated walk first.
"""
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import admin                                         # noqa: E402
import main                                                      # noqa: E402
from admin.auth import require_admin_token                       # noqa: E402

ROUTE = "/admin/chain/rules/grammar"

#: 🔴 THE RULE THE OPERATOR CONVERTS, and it deliberately carries cells the unified shape had
#: no room for until today: `is_batch` (which decides how it is CALLED, 판정 506) and a cell
#: the grammar cannot name at all (`x_col`, read by the owner's mappers).
FLAT = {"name": "the_one_being_moved", "enabled": True,
        "trigger_table": "dt_log", "trigger_columns": ["dt_job"],
        "target_table": "dt_map", "mapper_module": "m", "mapper_function": "f",
        "is_batch": True, "source_table": "dt_log", "x_col": "inchip_x"}

#: ⚠️ THE BYSTANDERS. 판정 548 규율 ②: converting one rule must leave every other rule's
#: serialization byte for byte what it was.
OTHERS = [
    {"name": "untouched_flat", "trigger_table": "a", "target_table": "b",
     "mapper_module": "m", "mapper_function": "f", "enabled": True},
    {"name": "untouched_unified", "enabled": False,
     "on": {"table": "a", "columns": ["c"]},
     "derive": {"kind": "mapper",
                "mapper": {"mapper_module": "m", "mapper_function": "f"}},
     "into": {"table": "b"}},
]


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [dict(FLAT)] + [dict(r) for r in OTHERS]}),
                    encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return path


@pytest.fixture
def client():
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.add_api_route(ROUTE, main.post_chain_rule_grammar, methods=["POST"])
    return TestClient(app)


def _stored(path, name):
    for rule in json.loads(path.read_text(encoding="utf-8"))["rules"]:
        if rule.get("name") == name:
            return rule
    return None


def _bystanders(path):
    """The other rules, serialized the way 판정 548 규율 ② asks about them."""
    return {rule["name"]: json.dumps(rule, sort_keys=True, ensure_ascii=False)
            for rule in json.loads(path.read_text(encoding="utf-8"))["rules"]
            if rule.get("name") != FLAT["name"]}


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the two presses, and the property between them
# ---------------------------------------------------------------------------

def test_a_stored_flat_rule_can_be_saved_as_unified(client, rules_file):
    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                      "dry_run": False})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["from"], body["to"], body["saved"]) == ("flat", "unified", True)

    saved = _stored(rules_file, FLAT["name"])
    assert admin.grammar_of(saved) == "unified", saved
    # ⚠️ AND THE CELLS THE OLD SHAPE COULD NOT HOLD ARE IN IT. Without this the test would
    #    pass for a converter that produced a valid unified rule and dropped half the rule.
    assert saved["is_batch"] is True, "the axis cell did not survive the save"
    assert saved["extra"]["x_col"] == "inchip_x", "the unnamed cell was dropped"


def test_the_operator_can_take_it_back(client, rules_file):
    """🔵 판정 548: undo is the same door walked the other way, because the round trip is the
    identity. Cell for cell - 「대략 같은 모양」 is what a lossy converter also produces."""
    before = _stored(rules_file, FLAT["name"])

    client.post(ROUTE, json={"name": FLAT["name"], "to": "unified", "dry_run": False})
    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "flat",
                                      "dry_run": False})
    assert answer.status_code == 200, answer.text

    after = _stored(rules_file, FLAT["name"])
    assert after == before, (
        "the trip through the unified grammar changed the rule: lost %s · added %s"
        % (sorted(k for k in before if k not in after),
           sorted(k for k in after if k not in before)))


# ---------------------------------------------------------------------------
# 🔴 ⓑ — what the press must NOT touch
# ---------------------------------------------------------------------------

def test_converting_one_rule_leaves_the_others_byte_for_byte(client, rules_file):
    """🔴 판정 548 규율 ② · 547. The file is the owner's, and a save that rewrote a
    neighbour would be discovered by the neighbour's next run, not by this route."""
    before = _bystanders(rules_file)
    assert len(before) == len(OTHERS), "the fixture lost a bystander before we started"

    client.post(ROUTE, json={"name": FLAT["name"], "to": "unified", "dry_run": False})

    assert _bystanders(rules_file) == before, "a rule nobody asked about was rewritten"


def test_a_dry_run_writes_nothing(client, rules_file):
    """⚠️ 「이렇게 바뀝니다」 must be readable without committing to it — 판정 548."""
    before = rules_file.read_bytes()

    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                      "dry_run": True})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["saved"] is False and body["changed"] is True
    assert admin.grammar_of(body["declaration"]) == "unified"
    assert rules_file.read_bytes() == before, "a dry run wrote the file"


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the three states of 「무엇이 다시 도나」 (판정 549)
# ---------------------------------------------------------------------------

def test_the_rerun_count_is_a_measured_zero_not_a_silence(client, rules_file):
    """🔴 판정 549. 「0 행」 and 「안 세어 봤다」 must not look the same, and a grammar change
    that expands to the same rules genuinely re-runs nothing - which is a fact this seat can
    MEASURE rather than assume."""
    body = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                    "dry_run": True}).json()

    assert body["reruns"]["rows"] == 0, body["reruns"]
    assert body["reruns"]["why"], "a zero with no sentence reads as the absence of a look"


def test_when_the_count_is_unknown_the_cell_is_absent_not_zero(
        client, rules_file, monkeypatch):
    """🔴 판정 549 의 «셋째» 상태, and the one an assertion is easiest to forget.

    A 0 that means 「I did not look」 is worse than no answer: the operator reads it as
    safe. The cell must be GONE. Reached by making the expansion refuse - the honest way to
    say that today's converters never move an expansion, so the file cannot produce this.
    """
    from chain import rule_shape

    monkeypatch.setattr(rule_shape, "expand_declaration",
                        lambda declaration, table_config=None: ([], "펼치지 못했습니다", []))

    body = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                    "dry_run": True}).json()

    assert "rows" not in body["reruns"], (
        "an uncounted re-run was reported as a number, which reads as 「safe」: %r"
        % (body["reruns"],))
    assert body["reruns"]["why"], "the cell was dropped without saying why it is unknown"


# ---------------------------------------------------------------------------
# ⚠️ ⓓ — the two answers that are not saves
# ---------------------------------------------------------------------------

def test_a_rule_already_in_that_grammar_is_told_so_not_refused(client, rules_file):
    """판정 548 규율 ③: a statement of fact. An error here would teach the operator to fear
    a button that is idempotent."""
    answer = client.post(ROUTE, json={"name": "untouched_unified", "to": "unified",
                                      "dry_run": False})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["changed"], body["saved"]) == (False, False)
    assert "declaration" not in body, "nothing was converted, so nothing is on offer"


def test_a_rule_whose_grammar_cannot_be_read_is_refused_by_name(
        client, rules_file, monkeypatch):
    """판정 548 규율 ④ — 추측해서 변환하지 않습니다.

    🔴 REACHED BY PATCHING THE READER, AND THAT IS THE HONEST WAY TO SAY IT: today
    `grammar_of` answers 「unified」 or 「flat」 for every dict, so no file can produce this
    case. The branch is the seat that must not guess ON THE DAY the reader learns to say
    「모른다」 - writing it without saying it is unreachable would be a test claiming to
    cover a path the product cannot take. 「이 갈래를 누가 타나」는 오늘 «아무도»입니다.
    """
    monkeypatch.setattr(admin, "grammar_of", lambda rule: None)

    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                      "dry_run": False})
    assert answer.status_code == 400, answer.text
    assert FLAT["name"] in answer.json()["detail"]["message"]


def test_an_unknown_grammar_name_is_refused(client, rules_file):
    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "compact"})
    assert answer.status_code == 400, answer.text
    assert answer.json()["detail"]["path"] == "to"


def test_a_name_claimed_twice_is_refused_rather_than_picked(client, tmp_path, monkeypatch):
    """🔴 [판정 554 · 409] 겹친 이름은 «어느 쪽도» 고르지 않습니다.

    MEASURED BY THE APPLICATION LANE: three seats answered 「which rule is called X」
    differently - the list keyed a dict (LAST wins) while the save and the conversion each
    wrote their own `next(...)` (FIRST wins). So an operator read one rule and converted
    another, silently.

    ⚠️ AND THE ANSWER NEEDED NO NEW JUDGEMENT. `ingestion_worker` already refuses a
    twice-claimed name and runs NEITHER copy, because which one was meant is not something
    this product can know. Picking either here would have this file quietly deciding what
    the loader deliberately refuses to decide.
    """
    path = tmp_path / "chain_rules.json"
    twin = dict(FLAT)
    path.write_text(json.dumps({"rules": [dict(FLAT), twin]}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    before = path.read_bytes()

    answer = client.post(ROUTE, json={"name": FLAT["name"], "to": "unified",
                                      "dry_run": False})

    assert answer.status_code == 400, answer.text
    assert answer.json()["detail"]["code"] == "name_claimed_twice"
    assert path.read_bytes() == before, "a rule was converted despite the ambiguity"
