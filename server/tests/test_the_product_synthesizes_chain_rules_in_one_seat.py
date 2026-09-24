# -*- coding: utf-8 -*-
"""S-189 ⓒ — the three properties that OUTLIVED the synthesis seat this file was named for.

⚰️ [2026-09-24, 소유자 「enrich.json 아예 삭제」] This file measured the ONE synthesis seat
(판정 304): `synthesize_chain_rules`, its halves, and the report naming a dead half. The
flat enrich file it synthesised from is retired and the seat with it, so those tests went
in the same commit. One of them had already gone hollow - it scored the loader's SOURCE
for the word `synthesize_chain_rules`, and after the retirement that word survived only in
the tombstone comment, so the tombstone kept it green.

What is left is not about synthesis and keeps the name only because moving three tests is
not this round's work:
    an unknown kind is refused BY NAME, never ignored
    the drain has no rule loop left
    the auto-confirm collector is HANDED its rule rather than re-reading a file
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from chain import enrichment                                              # noqa: E402


# ---------------------------------------------------------------------------
# 🔴 the seat, and the move that must change nothing
# ---------------------------------------------------------------------------


# ⚰️ [판정 652 3걸음] 이 매개변수에 「virtual join」이 있었다. 합성되는 반쪽이 하나라
#    남은 값도 하나이고, 표의 «모양»은 그대로여서 둘째가 생기면 그 자리로 들어온다.


# ⚰️ [판정 652 3걸음] `test_one_half_failing_does_not_take_the_other_down` 이 여기 있었다 —
#    판정 452 ②의 대조군으로, 조인 반쪽이 던져도 인리치 반쪽이 산다는 것을 쟀다. 합성되는
#    반쪽이 하나가 되어 「다른 하나」가 없다. 🔴 감싸는 «모양»은 안 지웠다(`_SYNTHESIS_HALVES`
#    를 도는 try/except 그대로): 둘째 반쪽이 생기는 날 그 대조군이 다시 설 자리가 있다.
#    그리고 그 하나가 던져도 좌석이 안 터진다는 것은 바로 위 시험이 잰다.


# 🪦 `test_the_boot_line_counts_the_three_kinds_apart` died with `synthesized_kind_counts`
#    (S-234 ③): the 「Synthesized N (a · b · c)」 line folded into the loader's set line, which
#    names every rule with its origin and kind. That line is scored in
#    `test_one_chain_namespace_across_its_files.py`.


# ---------------------------------------------------------------------------
# the join half
# ---------------------------------------------------------------------------

KNOWN = {"left_t": {"column_types": {"k": "string", "frame": "string"}},
         "right_t": {"column_types": {"k": "string", "frame": "string"}}}


# 🪦 `test_a_name_claimed_by_both_files_is_refused_by_name` died with `join_name_collisions`
#    (S-234 ①, 판정 409): the three files are one namespace, judged once at the loader. That
#    refusal is scored in `test_one_chain_namespace_across_its_files.py`.


# ---------------------------------------------------------------------------
# 🔴 the `builtin:` table
# ---------------------------------------------------------------------------

def test_an_unknown_kind_is_refused_by_name_not_ignored():
    """⛔ SILENCE IS THE DEFECT. A rule naming a kind nothing implements would sit enabled,
    look live, and never run — the same silence `_report_unwatchable_trigger_columns` breaks
    for a mistyped trigger column.

    ⚰️ [판정 498] THE REFUSER MOVED FROM `synthesis.run_builtin` TO THE SEAT, and the SENTENCE
    is what this scores rather than the class. An unregistered `builtin:` name is no longer
    recognised as a builtin at all - it falls through to the arm that resolves a file mapper -
    so the exception type had to change. What must not change is that the operator is told the
    spelling they typed AND the kinds that exist; a refusal naming only the bad spelling leaves
    them guessing at the good one.
    """
    from chain import rule_run

    with pytest.raises(rule_run.UnresolvableRule) as caught:
        rule_run.resolve({"name": "r", "mapper": "builtin:no_such_kind"})
    assert "builtin:no_such_kind" in str(caught.value)
    assert "declared:join" in str(caught.value), "it must say what IS known"


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------

# ⚰️ [판정 652 3걸음] 그래프의 «두 화살표» 대조군이 여기 있었다 — 실물화된 규칙을
#    `_mapper_edges` 와 `_vjoin_edges` 양쪽이 그리면 한 선언에 화살표가 둘이 된다는 것.
#    `_vjoin_edges` 가 그 문법과 같이 걷혀 그릴 수 있는 자리가 하나다.


def test_the_drain_has_no_rule_loop_left():
    """⛔ THE ASSERTION THAT CLOSES 「두 경로 금지」, NOW ONE STEP FURTHER.

    ⚰️ It used to require `_run_the_follow_up_pass(db, done)` to appear EXACTLY ONCE in the
    drain - one route rather than two. 소유자 정본 removed the route itself: the drain follows
    the ledger and nothing else, and chain rules are woken by their trigger.

    🔴 WHAT IS ASSERTED IS THE ABSENCE OF A RULE LOOP, not the absence of a name. A second
    route wearing a different spelling is the defect; a drain that runs no rules cannot have
    one. The DELETE withdrawal stays and is named, because it is not the lap (판정 608).
    ⚠️ SUBJECT (608): this is about the CHAIN. `ledger/followup.py`'s own queue is a different
    subsystem and still stands.
    """
    import inspect

    from chain import ingestion_worker as worker

    assert not hasattr(worker, "_auto_confirm_followed_rows"), "the second route is back"
    assert not hasattr(worker, "_run_the_follow_up_pass"), "the lap is back"
    body = inspect.getsource(worker._drain_ledger_followup_sync)
    assert "auto_confirm" not in body, "the drain names a kind again"
    assert "for rule in" not in body, "the drain is running rules again"
    assert "_retract_what_those_rows_fed" in body, (
        "the DELETE withdrawal left with the lap; it is not the lap")


def test_the_collector_is_handed_its_rule_rather_than_finding_it(monkeypatch):
    """🔴 THE SECOND READER, DELETED. `AutoConfirmCollector` already accepted `rules`; left to
    itself it called `load_enrichment_rules` and re-found what the synthesised rule carries in
    `params`. Two readers of one fact is how they come to disagree — and this one also re-read
    a file on a paced path."""
    from chain import enrichment

    seen = {}

    class _Collector:
        active = False

        def __init__(self, table, rules=None, settings=None):
            seen["table"] = table
            seen["rules"] = rules

    monkeypatch.setattr(enrichment.candidates, "AutoConfirmCollector", _Collector)
    rule = {"name": "enrichment_auto_confirm:x", "target_table": "derived_t",
            "params": {"name": "x", "auto_confirm": True}}
    # ⚰️ [판정 498] THE MAPPER, NOT THE DELETED DOOR. What is under test is which rules the
    #    collector is handed, and routing that through the seat would add a resolution step
    #    this assertion says nothing about.
    # ⚰️ [판정 562 · 소유자 정본] THIS CALLED `synthesis.BUILTIN_KINDS["declared:decide"]` with
    #   `row_ids=` and a `done={"table": ...}` note. The table is gone and so is the note —
    #   the template reads the target off `rule["target_table"]`, which is the cell the
    #   declaration already carries, so the rule above gained it and the note went.
    from chain import dynamic_mappers
    from chain.enrichment import config as enrichment_config

    dynamic_mappers.TEMPLATES[enrichment_config.AUTO_CONFIRM_MAPPER](
        None, [{"row_id": "r1"}], rule=rule)
    assert seen["table"] == "derived_t"
    assert seen["rules"] == [rule["params"]], (
        "the collector was left to load the rules itself")

