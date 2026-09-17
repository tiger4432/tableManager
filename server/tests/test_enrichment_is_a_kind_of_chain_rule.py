# -*- coding: utf-8 -*-
"""S-179 ①. Enrichment is a KIND of chain rule, not a second rule language.

BASIS §4.5 states the rule this round implements: 「체인 write ↦ E ↦ walk ; write — 별도
«규칙 언어»가 필요 없다 — 오늘 enrichment 규칙은 «이 꼴로 다시 적혀야» 한다」.

Half of it was already true: `load_enrichment_chain_rules` has synthesized the DEDUP half
as a chain rule since S-178. The auto-confirm half ran as a table-keyed hook on the
follow-up lap — same work, different language — and this round gives it a declaration.

🔴 ONE SYNTHESIZER, TWO KINDS (판정 292: 「두 합성기 금지」). Two would have rebuilt the split
one layer down.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain.graph                                                    # noqa: E402
from chain.enrichment import config as ec                                        # noqa: E402

RULE = {
    "name": "s179_rule",
    "source_table": "s179_src",
    "derived_table": "s179_derived",
    "decision_key": ["job"],
    "target_fields": ["lot"],
    "list_columns": ["hint"],
    "aggregations": {},
    "reference_views": [],
    "auto_confirm": {},
    "auto_confirm_declared": False,
    "alignment": False,
}


@pytest.fixture()
def one_rule(monkeypatch):
    def fake(path=None, known_tables=None, rejections=None, caps=None):
        return [dict(RULE)]
    monkeypatch.setattr(ec, "load_enrichment_rules", fake)
    return RULE


# ---------------------------------------------------------------------------
# The fold itself
# ---------------------------------------------------------------------------

def test_one_rule_becomes_two_kinds_from_one_synthesizer(one_rule):
    out = ec.load_enrichment_chain_rules()
    assert [r["name"] for r in out] == [
        "enrichment_dedup:s179_rule", "enrichment_auto_confirm:s179_rule"]


def test_every_normalized_cell_rides_on_both_kinds(one_rule):
    """🔴 「빠지는 칸 0」 (판정 292). The first order named four params as an EXAMPLE; the
    census found twelve. Asserted as a set difference against the rule itself rather than
    a hand-written list, so a cell added to the enrichment vocabulary tomorrow is covered
    by this test without it being edited — a hand-listed subset goes stale silently and
    the cell it drops is invisible until a declaration stops working."""
    for rule in ec.load_enrichment_chain_rules():
        assert set(rule["params"]) == set(RULE), set(RULE) - set(rule["params"])


def test_the_auto_confirm_rule_is_a_self_loop_that_opts_into_chain_triggers(one_rule):
    confirm = ec.load_enrichment_chain_rules()[1]
    assert confirm["mapper"] == ec.AUTO_CONFIRM_MAPPER
    assert confirm["trigger_table"] == confirm["target_table"] == "s179_derived"
    # ⚰️ [소유자 정본] THIS ASSERTED `follow_up is True` — 「the paced lap runs it」. There is
    #   no paced lap: 소유자 「트랜잭션 - 아웃박스 - 트리거 - 맵퍼 실행 - 페이로드 및 업서트
    #   이거만」. The cell is gone and its absence is asserted here.
    assert "follow_up" not in confirm
    # 🔴 AND WITHOUT THE NEXT CELL THE REMOVAL WOULD BE SILENT. What wakes this rule is the
    #   dedup half's write to the derived table, and that write's `source_name` IS
    #   `chain_ingestion` — so `_rule_accepts_event` would drop it and the rule would sit
    #   enabled, look live, and never run.
    assert confirm["allow_chain_trigger"] is True


# ---------------------------------------------------------------------------
# Gate ⓔ — the ping-pong guard, which this kind gets for free
# ---------------------------------------------------------------------------

def test_only_the_self_loop_opts_into_chain_triggers(one_rule):
    """⚰️ [소유자 정본] THIS SAID 「NO synthesized rule declares `allow_chain_trigger`」 and
    called that the ping-pong guard: the auto-confirm half is a self-loop, so not declaring
    the cell made its own writes structurally unable to wake it.

    🔴 THE GUARD IS NOT FREE ANY MORE, AND THAT IS SAID OUT LOUD RATHER THAN QUIETLY DROPPED.
    With the paced lap gone the only way this rule is reached is a chain-produced event, so it
    must declare the cell. What bounds the loop now is the WORK, not the grammar: a second
    pass finds nothing left to confirm and writes nothing, so no further event is produced.
    That termination is measured — `test_enrichment_candidates` runs the same rows a second
    time and asserts the confirmed count does not move — and the hop ceiling is the backstop.
    소유자 2026-09-17: 「홉수 무시하고 일단 체인 만들라」.

    ⚠️ AND IT IS STILL ONLY THE SELF-LOOP. The dedup half writes to a table it does not watch,
    so it has no reason to opt in and this goes red if it ever does.
    """
    dedup, confirm = ec.load_enrichment_chain_rules()
    assert not dedup.get("allow_chain_trigger"), (
        "the dedup half opted into chain triggers; it is not a self-loop and has no reason to")
    assert confirm["allow_chain_trigger"] is True


def test_the_self_loop_is_reached_by_the_write_that_feeds_it(one_rule):
    """⚰️ [소유자 정본] THIS ASSERTED THE OPPOSITE — 「a follow_up rule is never matched to a
    trigger event ... because its work belongs to the follow-up lap」. The lap is gone, so the
    trigger event is the ONLY way this rule is ever reached, and the event that reaches it is
    the dedup half's write: chain-produced, which is exactly what the old assertion refused.
    """
    import types

    from chain import ingestion_worker as worker

    confirm = ec.load_enrichment_chain_rules()[1]
    for source in ("user", "chain_ingestion"):
        event = types.SimpleNamespace(table_name="s179_derived",
                                      payload={"source_name": source})
        assert worker._rule_accepts_event(confirm, event) is True, (
            "the confirm half no longer hears %s, so nothing wakes it" % source)
    # THE SENSITIVITY CONTROL: a rule that did NOT opt in still refuses the chain's own write.
    plain = {"name": "plain"}
    chain_written = types.SimpleNamespace(table_name="s179_derived",
                                          payload={"source_name": "chain_ingestion"})
    assert worker._rule_accepts_event(plain, chain_written) is False
    by_a_person = types.SimpleNamespace(table_name="s179_src", payload={"source_name": "user"})
    assert worker._rule_accepts_event(plain, by_a_person) is True


# ---------------------------------------------------------------------------
# Gate ⓕ — `enabled` is read, never typed
# ---------------------------------------------------------------------------

def test_a_disabled_rule_does_not_become_an_enabled_chain_rule(monkeypatch):
    """⚰️ IT USED TO READ `"enabled": True`, A LITERAL. That was correct only because
    `_validate_rule` drops disabled rules three functions upstream — move that filter and
    a disabled declaration becomes a running chain rule, which is the class 「가드는 도달
    가능해지는 날 틀린다」. Scored at the synthesizer's own boundary, which is where the
    defect would live: the live loader's filter is not what is being trusted here."""
    disabled = dict(RULE, enabled=False)
    monkeypatch.setattr(ec, "load_enrichment_rules",
                        lambda **kw: [disabled])
    for rule in ec.load_enrichment_chain_rules():
        assert rule["enabled"] is False


# ---------------------------------------------------------------------------
# 🪦 Gate ⓑ — a name claimed twice is refused BY NAME — moved (S-234 ①, 판정 409)
# ---------------------------------------------------------------------------
# `enrichment_name_collisions` is gone: the three rule files are ONE namespace, judged once
# at the loader's set-aware seat. The refusal and its sensitivity control are scored in
# `test_three_files_declare_one_chain_namespace.py`.


# ---------------------------------------------------------------------------
# Gate ⓒ — the graph reads the loader the worker runs
# ---------------------------------------------------------------------------

def test_the_graph_reads_the_product_loader_not_the_file():
    """🔴 CODE_MAP D-10 ①: 「모든 노드·엣지는 «제품이 쓰는 로더»로 읽는다」 (판정 293). This
    seat read `chain_rules.json` directly, so the picture could not see a synthesized rule
    — the dedup projection was missing from the graph entirely while the worker ran it on
    every event. A file read and a loader are 「같은 기능 두 경로」.

    ⚰️ The old function is gone by NAME, not merely unused: a dormant second reader is
    what the next person restores by accident."""
    assert not hasattr(chain.graph, "_chain_rule_file")
    assert hasattr(chain.graph, "_chain_rules")


def test_the_dedup_projection_is_drawn_now(monkeypatch):
    """Gate ⓒ's repair, scored on the edge builders rather than a live database."""
    synthesized = [
        {"name": "enrichment_dedup:r", "trigger_table": "src", "target_table": "drv",
         "enabled": True, "params": {}},
        {"name": "enrichment_auto_confirm:r", "trigger_table": "drv",
         "target_table": "drv", "enabled": True, "follow_up": True, "params": {}},
    ]
    edges = chain.graph._mapper_edges(synthesized)
    pairs = {(e["from"], e["to"]) for e in edges}
    assert ("src", "drv") in pairs, "the dedup projection is still invisible"
    assert ("drv", "drv") in pairs, "the auto-confirm self-loop lost its arrow"
    assert {e["kind"] for e in edges} == {"mapper"}


def test_the_enrich_self_loop_is_no_longer_drawn_twice():
    """The fold's whole claim: the endpoints do not move, only the label. If
    `_enrich_edges` still drew the self-loop it would now be drawn by both builders."""
    edges = chain.graph._enrich_edges([dict(RULE, reference_views=[])])
    assert [e for e in edges if e["from"] == e["to"]] == []


def test_a_reference_view_that_declares_reads_still_draws_its_arrow():
    """⚠️ THE `reads` EDGES ARE NOT FOLDED, and that is deliberate: they are a 「이 표를
    읽는다」 relation that NO chain rule expresses, so folding them would mean inventing a
    rule that does not exist. They keep `kind: "enrich"` — which is why that kind does not
    reach zero, contrary to what 판정 292 assumed when it queued C-78."""
    rule = dict(RULE, reference_views=[{"label": "v", "reads": ["other_table"]}])
    edges = chain.graph._enrich_edges([rule])
    assert ("other_table", "s179_derived") in {(e["from"], e["to"]) for e in edges}
    assert {e["kind"] for e in edges} == {"enrich"}


def test_the_mapper_edge_carries_what_the_self_loop_used_to_say():
    """Dropping the old edge without moving these would make the fold a LOSS of
    information rather than a change of label."""
    rule = {"name": "enrichment_auto_confirm:r", "trigger_table": "drv",
            "target_table": "drv", "enabled": True,
            "params": {"decision_key": ["job"],
                       "reference_views": [{"label": "v", "reads": None}]}}
    edge = chain.graph._mapper_edges([rule])[0]
    assert edge["decision_key"] == ["job"]
    assert edge["reference_views"] == [
        {"label": "v", "required_binds": [], "reads": None}]
    assert edge["reads_unknown"] == 1


# ---------------------------------------------------------------------------
# 판정 293-b — one reader, and an `origin` cell instead of a second one
# ---------------------------------------------------------------------------

def test_every_chain_edge_says_which_file_it_came_from(one_rule):
    """🔴 THE CELL THAT REPLACED THE SECOND READER. The graph kept a raw-file reader purely
    so it could tell a written rule from a synthesized one — 「같은 기능 두 경로」. Per-file
    counts come from this cell now, and a second loader is forbidden."""
    written = {"name": "written_rule", "trigger_table": "a", "target_table": "b"}
    synthesized = ec.load_enrichment_chain_rules()
    edges = chain.graph._mapper_edges([written] + synthesized)
    by_origin = {}
    for edge in edges:
        by_origin.setdefault(edge["origin"], []).append(edge["rule"])
    assert by_origin["file"] == ["written_rule"]
    assert set(by_origin) == {"file", "synthesized:s179_rule"}
    assert len(by_origin["synthesized:s179_rule"]) == 2


def test_no_rule_is_drawn_twice(one_rule):
    """⚰️ THE DUPLICATE THIS ROUND COULD HAVE CREATED. Before the fold, `_enrich_edges`
    drew the derived table's self-loop and `_mapper_edges` could not see the synthesized
    rule at all. Feeding both builders the same declarations must still yield each
    (from, to, rule) exactly once — drawing it in both places is the defect the single
    reader exists to prevent."""
    import collections

    synthesized = ec.load_enrichment_chain_rules()
    edges = (chain.graph._mapper_edges(synthesized)
             + chain.graph._enrich_edges([dict(RULE)]))
    counted = collections.Counter((e["from"], e["to"], e.get("rule")) for e in edges)
    assert [pair for pair, n in counted.items() if n > 1] == []
