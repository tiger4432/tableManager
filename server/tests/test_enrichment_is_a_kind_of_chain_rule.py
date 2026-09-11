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

import chain_graph                                                    # noqa: E402
import enrichment_config as ec                                        # noqa: E402

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


def test_the_auto_confirm_kind_is_a_paced_follow_up_on_a_self_loop(one_rule):
    confirm = ec.load_enrichment_chain_rules()[1]
    assert confirm["mapper"] == ec.AUTO_CONFIRM_MAPPER
    assert confirm["follow_up"] is True
    assert confirm["trigger_table"] == confirm["target_table"] == "s179_derived"


# ---------------------------------------------------------------------------
# Gate ⓔ — the ping-pong guard, which this kind gets for free
# ---------------------------------------------------------------------------

def test_no_synthesized_rule_declares_allow_chain_trigger(one_rule):
    """🔴 THIS IS THE PING-PONG GUARD. The auto-confirm kind is a SELF-LOOP, so the one
    thing that could make its own writes wake it is `allow_chain_trigger` — and the
    load-time cycle validator only walks rules that declare it. Not declaring it makes the
    loop structurally unreachable instead of merely unlikely."""
    for rule in ec.load_enrichment_chain_rules():
        assert not rule.get("allow_chain_trigger")


def test_a_follow_up_rule_is_never_matched_to_a_trigger_event(one_rule):
    """The second half of the same guard: even a hand-written event for its own table
    must not reach it, because its work belongs to the follow-up lap (S-151, 판정 264 —
    inlining cost 0.875 s per group)."""
    import types

    import chain_ingestion_worker as worker

    confirm = ec.load_enrichment_chain_rules()[1]
    for source in ("user", "chain_ingestion"):
        event = types.SimpleNamespace(table_name="s179_derived",
                                      payload={"source_name": source})
        assert worker._rule_accepts_event(confirm, event) is False
    # THE SENSITIVITY CONTROL: an ordinary rule still accepts what it should.
    plain = types.SimpleNamespace(table_name="s179_src", payload={"source_name": "user"})
    assert worker._rule_accepts_event({"name": "plain"}, plain) is True


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
# Gate ⓑ — a name claimed twice is refused BY NAME
# ---------------------------------------------------------------------------

def test_a_name_declared_on_both_sides_is_named(one_rule):
    assert ec.enrichment_name_collisions(["enrichment_dedup:s179_rule"]) == [
        "enrichment_dedup:s179_rule"]
    assert ec.enrichment_name_collisions(["enrichment_auto_confirm:s179_rule"]) == [
        "enrichment_auto_confirm:s179_rule"]


def test_a_clean_declaration_collides_with_nothing(one_rule):
    """The sensitivity control: a checker that named everything would pass the test above
    and refuse every deployment."""
    assert ec.enrichment_name_collisions(["some_other_rule"]) == []
    assert ec.enrichment_name_collisions([]) == []


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
    assert not hasattr(chain_graph, "_chain_rule_file")
    assert hasattr(chain_graph, "_chain_rules")


def test_the_dedup_projection_is_drawn_now(monkeypatch):
    """Gate ⓒ's repair, scored on the edge builders rather than a live database."""
    synthesized = [
        {"name": "enrichment_dedup:r", "trigger_table": "src", "target_table": "drv",
         "enabled": True, "params": {}},
        {"name": "enrichment_auto_confirm:r", "trigger_table": "drv",
         "target_table": "drv", "enabled": True, "follow_up": True, "params": {}},
    ]
    edges = chain_graph._mapper_edges(synthesized)
    pairs = {(e["from"], e["to"]) for e in edges}
    assert ("src", "drv") in pairs, "the dedup projection is still invisible"
    assert ("drv", "drv") in pairs, "the auto-confirm self-loop lost its arrow"
    assert {e["kind"] for e in edges} == {"mapper"}


def test_the_enrich_self_loop_is_no_longer_drawn_twice():
    """The fold's whole claim: the endpoints do not move, only the label. If
    `_enrich_edges` still drew the self-loop it would now be drawn by both builders."""
    edges = chain_graph._enrich_edges([dict(RULE, reference_views=[])])
    assert [e for e in edges if e["from"] == e["to"]] == []


def test_a_reference_view_that_declares_reads_still_draws_its_arrow():
    """⚠️ THE `reads` EDGES ARE NOT FOLDED, and that is deliberate: they are a 「이 표를
    읽는다」 relation that NO chain rule expresses, so folding them would mean inventing a
    rule that does not exist. They keep `kind: "enrich"` — which is why that kind does not
    reach zero, contrary to what 판정 292 assumed when it queued C-78."""
    rule = dict(RULE, reference_views=[{"label": "v", "reads": ["other_table"]}])
    edges = chain_graph._enrich_edges([rule])
    assert ("other_table", "s179_derived") in {(e["from"], e["to"]) for e in edges}
    assert {e["kind"] for e in edges} == {"enrich"}


def test_the_mapper_edge_carries_what_the_self_loop_used_to_say():
    """Dropping the old edge without moving these would make the fold a LOSS of
    information rather than a change of label."""
    rule = {"name": "enrichment_auto_confirm:r", "trigger_table": "drv",
            "target_table": "drv", "enabled": True,
            "params": {"decision_key": ["job"],
                       "reference_views": [{"label": "v", "reads": None}]}}
    edge = chain_graph._mapper_edges([rule])[0]
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
    edges = chain_graph._mapper_edges([written] + synthesized)
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
    edges = (chain_graph._mapper_edges(synthesized)
             + chain_graph._enrich_edges([dict(RULE)]))
    counted = collections.Counter((e["from"], e["to"], e.get("rule")) for e in edges)
    assert [pair for pair, n in counted.items() if n > 1] == []
