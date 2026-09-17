# -*- coding: utf-8 -*-
"""S-239 (판정 399·400·401). enrich 를 통합 선언의 `decide` 종류로 — «껍데기»만.

🔴 NOTHING ABOUT HOW ENRICH RUNS MOVES HERE. It is already a chain mapper: dedup on the
ordinary path, auto-confirm on the follow-up lap. What moves is WHERE the declaration may be
written - so this round adds no SQL, and §0-ter ① 「읽기 경로에 새 SQL 을 얹지 않는다」 is
satisfied structurally rather than by care.

🔴 AND THE PROOF OF 「같은 답」 IS ONE EXPANDER, NOT A COMPARISON. Both grammars reach
`enrichment.config.chain_rules_for` through the same normalizer. A second expander would agree
on the day it was written and drift on the first cell added to the vocabulary - so the strong
form of gate ④ is the shared seat, and the census comparison below is what proves the seat is
really shared rather than described as shared.
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_census, rule_shape                            # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from chain.enrichment import config as enrichment_config                   # noqa: E402

SOURCE = "s239_source"
DERIVED = "s239_derived"

#: The same rule, written twice. The point of the file is that these two are one declaration.
OLD_FILE_RULE = {
    "name": "s239_lot_rollup",
    "source_table": SOURCE,
    "derived_table": DERIVED,
    "decision_key": ["lot"],
    "target_fields": ["grade"],
    "auto_confirm": True,
}

UNIFIED = {
    "name": "s239_lot_rollup",
    "on": {"table": SOURCE},
    "into": {"table": DERIVED},
    "derive": {"kind": "decide",
               "decide": {"key": ["lot"], "fields": ["grade"], "auto_confirm": True}},
}


def _from_unified(declaration, known_tables=None):
    internal = rule_shape.from_declaration(declaration)
    rules, refusal = rule_shape.decide_rules(internal, known_tables)
    return rules, refusal


# ---------------------------------------------------------------------------
# 🔴 ⓐ — 동작 0: the two grammars are one declaration (gate ④)
# ---------------------------------------------------------------------------

def test_the_two_grammars_produce_the_same_rules_cell_for_cell():
    """🔴 NOT 「equivalent」 - IDENTICAL. Anything weaker leaves room for a cell that differs
    and nobody looks at, which is how a derived table quietly stops matching."""
    old = enrichment_config.chain_rules_for(
        enrichment_config._validate_rule(OLD_FILE_RULE["name"], OLD_FILE_RULE, None)[0])
    new, refusal = _from_unified(UNIFIED)

    assert refusal is None
    assert new == old


def test_the_census_says_the_same_and_names_which_rules_it_compared():
    """⚠️ THE CENSUS IS THE PRODUCT'S OWN COMPARATOR, so gate ④ asks the product rather than
    inventing a second notion of 「same」 for the test to hold."""
    old = enrichment_config.chain_rules_for(
        enrichment_config._validate_rule(OLD_FILE_RULE["name"], OLD_FILE_RULE, None)[0])
    new, _ = _from_unified(UNIFIED)

    diff = rule_census.census_diff(rule_census.census(old), rule_census.census(new))

    assert not diff.get("removed") and not diff.get("added")
    assert not diff.get("changed"), diff
    assert [r["name"] for r in rule_census.census(new)] == [
        "enrichment_dedup:s239_lot_rollup", "enrichment_auto_confirm:s239_lot_rollup"]


def test_one_declaration_still_makes_the_dedup_rule_and_the_confirm_rule():
    """⚠️ TWO RULES IS THE SHELL'S FACT, NOT THE AUTHOR'S GRAMMAR (판정 400). The author says
    「also confirm」 with one boolean; counting rules is this product's job."""
    rules, _ = _from_unified(UNIFIED)
    dedup, confirm = rules

    assert dedup["trigger_table"] == SOURCE and dedup["target_table"] == DERIVED
    assert dedup["mapper"] == enrichment_config.DEDUP_MAPPER
    assert confirm["trigger_table"] == DERIVED and confirm["target_table"] == DERIVED
    assert confirm["mapper"] == enrichment_config.AUTO_CONFIRM_MAPPER
    # ⚰️ [소유자 정본] the paced lap is gone; the confirm half is woken by the
    #   dedup half's write, which is why it opts into chain triggers.
    assert "follow_up" not in confirm
    assert confirm["allow_chain_trigger"] is True


# ---------------------------------------------------------------------------
# 🔴 ⓑ — 판정 400·401: which cells exist, and which are derived
# ---------------------------------------------------------------------------

def test_auto_confirm_is_a_cell_the_author_writes():
    """판정 400. One boolean, and the shell still emits both rules either way - the
    collector's `.active` is what decides at run time, exactly as before."""
    assert "auto_confirm" in rule_shape.DECIDE_CELLS
    without, _ = _from_unified({**UNIFIED, "derive": {
        "kind": "decide", "decide": {"key": ["lot"], "fields": ["grade"]}}})

    assert len(without) == 2, "the shell's count does not depend on the boolean"
    assert without[0]["params"]["auto_confirm"] is False


def test_whether_auto_confirm_was_written_is_derived_and_never_a_cell():
    """🔴 판정 401. 「was it written」 is the `enabled_written` class: a cell for it would be a
    place for an author to write that they wrote something, and the two could disagree."""
    assert "auto_confirm_declared" not in rule_shape.DECIDE_CELLS

    written, _ = _from_unified(UNIFIED)
    absent, _ = _from_unified({**UNIFIED, "derive": {
        "kind": "decide", "decide": {"key": ["lot"], "fields": ["grade"]}}})

    assert written[0]["params"]["auto_confirm_declared"] is True
    assert absent[0]["params"]["auto_confirm_declared"] is False


def test_a_decide_cell_nobody_reads_is_named_and_the_rule_still_runs():
    """⚠️ YESTERDAY'S POSTURE. A cell the product does not know may be a live argument it has
    not learned yet; refusing it would stop a declaration that works."""
    odd = {**UNIFIED, "derive": {"kind": "decide", "decide": {
        "key": ["lot"], "fields": ["grade"], "wobble": 1}}}

    assert rule_shape.unknown_decide_cells(rule_shape.from_declaration(odd)) == ["wobble"]


def test_a_declaration_that_cannot_be_normalized_is_refused_by_name():
    """⛔ THE NORMALIZER'S OWN SENTENCE, NOT A SECOND ONE. `decision_key` and `target_fields`
    may not overlap, and the reason an author reads should be the reason the old file gives."""
    bad = {**UNIFIED, "derive": {"kind": "decide", "decide": {
        "key": ["lot"], "fields": ["lot"]}}}

    rules, refusal = _from_unified(bad)

    assert rules == []
    assert refusal and "overlap" in refusal


# ---------------------------------------------------------------------------
# 🔴 ⓒ — 판정 399 ③′: OFF means nothing happens (and it is the ONE off switch — S-234 ②)
# ---------------------------------------------------------------------------

@pytest.fixture(name="load")
def fixture_load(tmp_path, monkeypatch):
    from chain import synthesis
    from database import crud

    monkeypatch.setattr(synthesis, "synthesize_chain_rules", lambda **kwargs: [])
    # ⚠️ THE TABLES ARE REGISTERED, or the normalizer refuses the declaration for a reason
    # that has nothing to do with what these cases are about - and the two OFF cases would
    # then pass for the wrong reason, which is worse than failing.
    monkeypatch.setitem(crud.TABLE_CONFIG, SOURCE,
                        {"column_types": {"lot": "string", "grade": "string"}})
    # ⚠️ AND THE DERIVED TABLE DECLARES ITS KEY. The normalizer requires the upsert key to
    # cover `decision_key`; without it these cases would be refused for a reason that is
    # correct and has nothing to do with the switch.
    monkeypatch.setitem(crud.TABLE_CONFIG, DERIVED,
                        {"business_key": "lot",
                         "column_types": {"lot": "string", "grade": "string"}})

    def run(declarations):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": declarations}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        return worker.load_chain_rules()

    return run


def test_only_a_written_false_switches_a_declaration_off():
    """🔴 「OFF」 IS `false`, NOT 「not exactly true」. The old shell reads `bool(enabled)`, so a
    declaration written `enabled: 1` is ON there - and a switch that read it as OFF would turn
    off a rule that has been running, which is the loudest possible way to be wrong about a
    switch. Absent is ON too: 「안 적음」 and 「false」 are different declarations.

    ⚠️ SCORED ON THE PREDICATE, because the loader cannot show the difference: both readings
    stand the rule for every value this file's other cases use."""
    def off(raw):
        return rule_shape.is_switched_off(rule_shape.from_declaration(raw))

    assert off({**UNIFIED, "enabled": False}) is True
    assert not off(UNIFIED), "absent means ON"
    assert not off({**UNIFIED, "enabled": True})
    assert not off({**UNIFIED, "enabled": 1}), "truthy is ON, as the old shell reads it"


def test_a_disabled_declaration_stands_no_rule_and_touches_no_database(load, monkeypatch):
    """⛔ 판정 399 ③′, AND THE DIFFERENCE BETWEEN A SWITCH AND A FILTER. 「stands it and drops
    it later」 is what let an operator turn everything off and watch it keep erroring - the
    switch has to stop the work, not label it.

    🔴 SCORED BY CALL COUNT, NOT BY LOG. A log line saying OFF is exactly what a half-switch
    also prints (ASSY_VJOIN_AUTO_INDEX printed one while still probing the database)."""
    from chain import unique_key

    touched = []
    monkeypatch.setattr(unique_key, "ensure_once",
                        lambda *a, **k: touched.append(a) or {"created": False})

    kept = load([{**UNIFIED, "enabled": False}])

    assert [r.get("name") for r in kept if "s239" in str(r.get("name"))] == []
    assert touched == [], "the loader reached the database for a declaration that is OFF"


def test_a_disabled_join_declaration_also_stands_no_rule(load):
    """⚠️ THE SAME RULING COVERS BOTH KINDS (판정 399). S-237's join was written before ③′
    existed, so it is scored here rather than left to be discovered."""
    join = {"name": "s239_off_join", "on": {"table": SOURCE}, "into": {"table": DERIVED},
            "enabled": False,
            "derive": {"kind": "join", "join": {"right_table": DERIVED,
                                                "on": [{"left": "lot", "right": "lot"}],
                                                "take": [{"from": "grade"}]}}}

    assert [r.get("name") for r in load([join])
            if "s239_off_join" in str(r.get("name"))] == []


# 🪦 `test_the_synthesis_switch_does_not_reach_a_unified_declaration` (판정 399 ㉡) died with
#    the switch it scored (S-234 ②, 판정 408). `enabled: false` in the file a rule was written
#    in is the one off switch for one rule; the absence of the old name is asserted in
#    `test_three_files_declare_one_chain_namespace.py`.
