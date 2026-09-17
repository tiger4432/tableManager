# -*- coding: utf-8 -*-
"""S-250. 그리드의 «다시 돌리기» 목록 = 소급이 «실제로 도는» 집합, 이 표로 걸러서.

> 소유자 2026-09-15: 「그리드 상단 리플레이 버튼에 **조인도 달아줘. 같은 체인문이면
> 보여야지**. 누를 시 목록은 **해당 테이블이 트리거인** 체인 규칙만」

🔴 배너가 쓰던 것은 `GET /admin/chain/rules` — 파일 «원문»이다. 원문이라 ① 통합 join 은 안
보이고(`on.table` 을 쓰지 `trigger_table` 이 없다) ② 합성 규칙(enrichment·가상 조인)은 아예
없고 ③ 어느 표의 규칙인지 «거를 수 없다». 소급이 실제로 도는 집합은 로더가 번역·합성한
`replay.load_rules()` 이고, 참조 쪽은 `is_reference_side` 가 거절한다.

⛔ 목록과 실행은 «같은 함수»를 지나야 한다. 두 번째 철자였다면 화면이 내미는 이름을 소급이
거절할 수 있고, 그 어긋남은 운영자가 «누른 뒤에» 안다.

⚠️ WHAT THIS FILE SCORES: the ROUTE, called - not the banner. The client half is C-109.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import replay, rule_shape                                # noqa: E402
from enrichment import config as enrichment_config                 # noqa: E402

LEFT = "s250_left"
RIGHT = "s250_right"

JOIN = {
    "name": "s250_join", "enabled": True,
    "on": {"table": LEFT}, "into": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
}


def _stood(declaration):
    stood, refusal, _notes = rule_shape.expand_declaration(declaration, {})
    assert refusal is None, refusal
    return stood


@pytest.fixture(name="loaded")
def fixture_loaded(monkeypatch):
    """The loader's OUTPUT, stubbed - so the subject stays 「what does the filter do with
    the loaded set」 rather than 「does the loader load」, which is its own file's gate."""
    def _install(rules):
        monkeypatch.setattr(replay, "load_rules", lambda: list(rules))
    return _install


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the filter: this table, replayable, joins included
# ---------------------------------------------------------------------------

def test_a_unified_join_appears_for_the_table_it_writes(loaded):
    """🔴 THE OWNER'S ASK. A unified join was invisible to the banner because the FILE says
    `on.table` and the banner read the file."""
    loaded(_stood(JOIN))

    found = replay.replayable_rules_for(LEFT)

    assert [entry["name"] for entry in found] == ["s250_join"]
    assert found[0]["kind"] == "join"
    assert (found[0]["trigger_table"], found[0]["target_table"]) == (LEFT, LEFT)


def test_the_reference_half_is_not_offered_for_a_replay_of_the_whole_table(loaded):
    """⛔ THE SAME DISCRIMINATOR THE BACKFILL REFUSES WITH (S-242). Replaying the follow-up
    half redoes, once per reference row, what the target half does for every row - so a
    list that offered it would be a screen inviting a refusal."""
    stood = _stood(JOIN)
    assert any(r["name"].endswith(":reference") for r in stood), "fixture lost its half"
    loaded(stood)

    assert replay.replayable_rules_for(RIGHT) == []


def test_the_reference_half_IS_offered_when_the_caller_will_pick_rows(loaded):
    """🔴 [S-270] ONE FIXTURE, BOTH ANSWERS — the axis is the SCOPE and nothing else.
    S-242's cost argument is about replaying a whole table; the grid's banner always sends
    `row_ids`, and with rows picked this is the only rule that can do what was asked (the
    target-side rule triggers on a table that grid cannot select). The same predicate
    decides here and in `find_rule`, so the list cannot offer a name the backfill refuses."""
    loaded(_stood(JOIN))

    scoped = replay.replayable_rules_for(RIGHT, row_scoped=True)

    assert [entry["name"] for entry in scoped] == ["s250_join:reference"]
    assert scoped[0]["kind"] == "join"
    assert replay.replayable_rules_for(RIGHT) == [], "the whole-table answer must not move"


def test_another_tables_rules_are_not_on_this_tables_list(loaded):
    loaded(_stood(JOIN) + [{"name": "elsewhere", "trigger_table": "other_t",
                            "target_table": "other_t",
                            "mapper_module": "m", "mapper_function": "f"}])

    assert [entry["name"] for entry in replay.replayable_rules_for(LEFT)] == ["s250_join"]


def test_a_switched_off_declaration_never_reaches_the_list(loaded):
    """⚠️ DECIDED UPSTREAM, AND THAT IS WHY THIS ASSERTS ON `load_rules`. `load_rules`
    keeps only enabled rules, so re-asking here would be a second answer to 「is it on」."""
    import inspect

    assert _stood(dict(JOIN, enabled=False)) == [], "an off declaration stands no rule"
    assert 'get("enabled"' in inspect.getsource(replay.load_rules)


def test_a_synthesized_enrichment_rule_is_on_its_trigger_tables_list(loaded):
    """🔴 「같은 체인문이면 보여야지」. These rules exist only in the loader's output - the
    file the banner was reading has never contained them."""
    loaded([{"name": "enrichment_dedup:x", "trigger_table": LEFT,
             "target_table": "dt_inventory",
             "mapper": enrichment_config.DEDUP_MAPPER}])

    found = replay.replayable_rules_for(LEFT)

    assert [entry["name"] for entry in found] == ["enrichment_dedup:x"]
    assert found[0]["kind"] == "decide"


# ---------------------------------------------------------------------------
# ⚠️ ⓑ — the word the operator reads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule,expected", [
    ({"name": "a", "mapper": "declared:join"}, "join"),
    ({"name": "b", "mapper": "declared:virtual_join"}, "join"),
    ({"name": "enrichment_dedup:c", "mapper": "declared:enrich"}, "decide"),
    ({"name": "enrichment_auto_confirm:c", "mapper": "declared:decide"}, "decide"),
    ({"name": "d", "mapper_module": "mappers.x", "mapper_function": "y"}, "mapper"),
    # 🔴 THE CONTROL GROUP FOR A RETIRED MECHANISM. This label used to be reached by a
    #   branch that read the rule's NAME (`startswith("enrichment_dedup:")`), so a rule
    #   called this while naming a file mapper was labelled 「decide」 on the strength of
    #   its spelling. It must read 「mapper」 now - if this row ever says 「decide」 again,
    #   the label is being derived from an ADDRESS and the branch is back.
    ({"name": "enrichment_dedup:not_synthesized",
      "mapper_module": "mappers.x", "mapper_function": "y"}, "mapper"),
])
def test_the_kind_is_the_declarations_word_not_the_plumbings(rule, expected):
    """🔴 A SCREEN THAT SAYS `builtin:join_into` ASKS THE READER TO KNOW OUR INTERNALS.
    That is the COLLECT dropdown's defect (2026-08-27: 「사용자가 claim, point, collection
    이런 걸 어케 암」), and the vocabulary that answers it is the declaration's own."""
    assert rule_shape.declared_kind(rule) == expected
    assert rule_shape.declared_kind(rule) in rule_shape.DECLARED_KINDS


def test_both_halves_of_one_decide_declaration_read_as_decide():
    """⚠️ ONE DECLARATION, AND THE OPERATOR DID NOT CHOOSE WHICH HALF THEY GOT."""
    kinds = {rule_shape.declared_kind(rule)
             for rule in ({"name": "enrichment_dedup:z",
                           "mapper": "declared:enrich"},
                          {"name": "enrichment_auto_confirm:z",
                           "mapper": "declared:decide"})}

    assert kinds == {"decide"}


# ---------------------------------------------------------------------------
# 🔴 ⓒ — the route, actually called
# ---------------------------------------------------------------------------

def test_the_route_answers_with_the_filtered_set(client, monkeypatch):
    """🔴 CALLED, NOT INSPECTED. A signature assertion is true of a route nobody can
    reach - this round's list has to arrive through the door the banner knocks on."""
    import main

    monkeypatch.setitem(main.crud.TABLE_CONFIG, LEFT, {"column_types": {}})
    monkeypatch.setattr(replay, "load_rules", lambda: _stood(JOIN))

    answer = client.get("/admin/chain/rules/replayable?table=%s" % LEFT)

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["status"] == "success"
    assert [entry["name"] for entry in body["data"]] == ["s250_join"]


def test_the_route_carries_the_scope_the_caller_asked_for(client, monkeypatch):
    """🔴 [S-270] THROUGH THE DOOR, BOTH WAYS. The banner asks with `row_scoped=true`; a
    caller that does not gets the whole-table answer. A parameter the route accepted and
    ignored would be 「폼이 그리는데 읽는 쪽이 없다」 with a query string instead of a form."""
    import main

    monkeypatch.setitem(main.crud.TABLE_CONFIG, RIGHT, {"column_types": {}})
    monkeypatch.setattr(replay, "load_rules", lambda: _stood(JOIN))

    whole = client.get("/admin/chain/rules/replayable?table=%s" % RIGHT)
    scoped = client.get("/admin/chain/rules/replayable?table=%s&row_scoped=true" % RIGHT)

    assert whole.status_code == scoped.status_code == 200, (whole.text, scoped.text)
    assert whole.json()["data"] == []
    assert [e["name"] for e in scoped.json()["data"]] == ["s250_join:reference"]


def test_a_table_nobody_declared_is_refused_by_name_rather_than_answered_empty(client):
    """⚠️ 「이 표엔 규칙이 없다」 AND 「그런 표가 없다」 ARE DIFFERENT FACTS. Folded into an
    empty list, an operator who mistyped reads 「규칙이 없구나」 and stops looking."""
    answer = client.get("/admin/chain/rules/replayable?table=no_such_table_here")

    assert answer.status_code == 404
    assert "no_such_table_here" in answer.json()["detail"]
    assert "table_config" in answer.json()["detail"]


def test_asking_without_a_table_is_refused_rather_than_answered_for_all(client):
    """⛔ THE WHOLE POINT IS THE FILTER. A missing table must not fall back to 「every
    rule」 - that is the list this round exists to replace."""
    answer = client.get("/admin/chain/rules/replayable")

    assert answer.status_code == 422


def test_the_file_route_beside_it_is_untouched(client):
    """⚠️ THE CHAIN TAB STILL READS THE FILE, and it should: editing a declaration needs
    the raw text, not the loader's translation of it."""
    answer = client.get("/admin/chain/rules")

    assert answer.status_code == 200
