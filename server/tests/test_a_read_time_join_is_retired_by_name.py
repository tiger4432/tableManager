# -*- coding: utf-8 -*-
"""S-282 · 판정 440 ②. `into: {read: true}` 는 «은퇴»했고, 은퇴는 «이름 대어» 말해진다.

🪦 THIS FILE REPLACES `test_a_read_time_join_can_be_declared_in_the_unified_file.py`,
which measured S-251 — the round that made a read-time join declarable in the unified
file. The owner has since answered that production writes its join columns into the table
(`into.table` only), so the capability is retired and the gate that proved it works is
retired with it: a test outlives the behaviour it measured only by becoming false.

🔴 RETIRED, NOT DELETED, AND THE DIFFERENCE IS THE WHOLE ROUND. `INTO_KINDS` still lists
`read`, because the grammar has to RECOGNISE the word in order to refuse it by name.
Drop the word instead and the declaration comes back as 「into 에 모르는 칸」 — an operator
sent hunting a typo they did not make, which is precisely the defect S-251 existed to fix
(`unresolvable_mapper` on a correct declaration). Retiring a capability must not re-open
the hole its arrival closed.

⚠️ ONE SENTENCE, TWO SEATS. `expand_declaration` and
`virtual_join.config._read_time_joins_from_unified` both meet this declaration. Were only
the loader changed, it would refuse a rule the collector still RAN; were they changed
separately, one file would be refused in two voices. Both read
`rule_shape.READ_TIME_RETIRED`.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import legacy_join_declaration as vjc                                   # noqa: E402
from chain import ingestion_worker, rule_shape                      # noqa: E402

KNOWN = {
    "left_t": {"column_types": {"k": "string", "frame": "string"}},
    "right_t": {"column_types": {"k": "string", "frame": "string"}},
}

OLD_SHAPE = {"left_table": "left_t", "right_table": "right_t",
             "join_key": [{"left": "k", "right": "k"}], "expose": ["frame"]}

UNIFIED = {
    "name": "u_read", "enabled": True,
    "on": {"table": "left_t"},
    "into": {"read": True},
    "derive": {"kind": "join", "join": dict(OLD_SHAPE, left_table=None)},
}
UNIFIED["derive"]["join"].pop("left_table")


@pytest.fixture(name="declared")
def fixture_declared(monkeypatch):
    """What the unified file says this round, without touching the live one."""
    def _install(*raws):
        monkeypatch.setattr(ingestion_worker, "read_rules_document",
                            lambda path=None: {"rules": list(raws), "document": {},
                                               "path": "x", "exists": True,
                                               "error": None})
    return _install


# ---------------------------------------------------------------------------
# 🔴 the retirement, said by name, at both seats
# ---------------------------------------------------------------------------

def test_the_loader_refuses_a_read_declaration_by_name(declared):
    """⛔ IT WAS A NOTE AND IS NOW A REFUSAL. Standing nothing and saying nothing would
    leave an operator with a declaration that is in the file, passes the form, and does
    nothing — which is the state 「조용한 불가 0」 forbids."""
    stood, refusal, _notes = rule_shape.expand_declaration(UNIFIED, KNOWN)

    assert stood == []
    assert refusal, "a retired capability was dropped without a word"
    assert "u_read" in refusal, "the refusal does not name the declaration: %s" % refusal


def test_the_collector_refuses_it_in_the_loaders_own_words(declared):
    """🔴 THE SECOND SEAT, AND THE SAME STRING. This is the half that would otherwise keep
    RUNNING what the loader refuses — the two-doors shape this repository keeps finding,
    arriving here as 「refused in one place, live in the other」."""
    declared(dict(UNIFIED, name="u_read"))
    rejections = []

    picked = vjc._read_time_joins_from_unified(set(), KNOWN, rejections)

    assert picked == [], "a retired read-time join was still adopted as a live join"
    said = [r for r in rejections if r.get("subject") == "u_read"]
    assert len(said) == 1, rejections
    assert said[0]["detail"] == rule_shape.READ_TIME_RETIRED, (
        "the collector refuses in its own words, so the same file is refused twice over "
        "in two voices: %s" % said[0]["detail"])


def test_the_refusal_says_what_to_write_instead():
    """🔴 [상설] 「거절의 «사유»와 «다음 행동»」. A retirement that names only what stopped
    working leaves the operator to guess the replacement — and here the replacement is not
    a workaround, it is what every live declaration already does."""
    said = rule_shape.READ_TIME_RETIRED

    assert "into.read" in said, "the sentence does not name what was retired"
    assert "table" in said, "the sentence does not name what to write instead"
    assert "다음" in said, "the sentence carries no next action"


def test_the_word_is_still_in_the_grammar_so_it_can_be_refused():
    """⚠️ 은퇴 ≠ 삭제. Removing `read` from `INTO_KINDS` would turn this refusal back into
    「모르는 칸」, which is the sentence S-251 was built to stop. The word stays until the
    declarations that use it are gone."""
    assert "read" in rule_shape.INTO_KINDS


# ---------------------------------------------------------------------------
# the controls — what this round does NOT change
# ---------------------------------------------------------------------------

def test_a_writing_join_still_stands_two_chain_rules(declared):
    """⚠️ THE CONTROL, and it is what production runs. `into.table` is the WRITE-time join
    and is untouched; the two are told apart by which `into` the declaration carries."""
    writing = dict(UNIFIED, name="u_write", into={"table": "left_t"})

    stood, refusal, _notes = rule_shape.expand_declaration(writing, KNOWN)

    assert refusal is None and len(stood) == 2


def test_the_old_files_read_time_declaration_is_now_refused_by_name(declared):
    """🪦 [S-283, 판정 446·461] THIS TEST USED TO ASSERT THE OPPOSITE, and the old sentence
    is kept here rather than deleted: 「THE ENGINE IS NOT TOUCHED IN THIS STEP (판정 440 ④,
    step 1 of 5). A declaration in `virtual_join_rules.json` still loads」.

    That was true of step 1 and is false now. Step 4 removed the read-time engine, so a
    `materialize: false` declaration in the legacy file no longer computes anything - and a
    declaration that stands nothing must SAY so, by name, or it is 「선언은 있는데 컬럼이
    없다」, which has the same shape as 「없다」.
    """
    declared()
    rejections = []

    rules = vjc.validate_virtual_join_rules({"o_read": OLD_SHAPE}, known_tables=KNOWN,
                                            rejections=rejections)

    assert rules == [], "a read-time declaration still stood as a live rule"
    said = [r for r in rejections if r.get("subject") == "o_read"]
    assert len(said) == 1, rejections
    assert said[0]["code"] == "read_time_retired", said[0]
    # 🔴 사유 + 다음 행동. The operator has two ways out and the sentence names both.
    assert "chain_rules.json" in said[0]["detail"], said[0]["detail"]
    assert "materialize" in said[0]["detail"], said[0]["detail"]


def test_a_materializing_declaration_in_the_old_file_still_stands(declared):
    """⚠️ THE CONTROL FOR THE LINE ABOVE. `materialize: true` is a WRITE join - it puts the
    value in the table - and ruling 461 kept it alive precisely because production may be
    running one. If this went red with its neighbour, the refusal would be catching the
    wrong half.
    """
    declared()

    rules = vjc.validate_virtual_join_rules(
        {"o_write": dict(OLD_SHAPE, materialize=True, max_rewrite_rows=1000)},
        known_tables=KNOWN)

    assert [r["name"] for r in rules] == ["o_write"]


def test_a_switched_off_read_declaration_is_still_not_complained_about(declared):
    """⛔ 판정 399 ③′ SURVIVES THE RETIREMENT. Off is off: not validated, not counted, not
    complained about — an operator who already disabled a declaration does not need to be
    told its capability retired."""
    declared(dict(UNIFIED, name="u_off", enabled=False))
    rejections = []

    rules = vjc.load_virtual_join_rules(known_tables=KNOWN, rejections=rejections)

    assert all(r["name"] != "u_off" for r in rules)
    assert all(r.get("subject") != "u_off" for r in rejections), rejections


# ---------------------------------------------------------------------------
# 판정 481 ⑤ — THE FOUR SEATS THAT JUDGE ONE DECLARATION, AS A TABLE.
#
# 판정 446 changed what an ABSENT `materialize` MEANS: from a default to 「read-time
# join」, which is retired. A change to what ABSENCE means has to reach every reader of
# the declaration, and it reached one. The other three stood on the old meaning, and the
# worst of them was silent in the worst direction - the authoring form had no field at
# all, so an operator could not write the thing the loader demanded.
#
# Scored as a GRID because the failure was invisible seat by seat: each was defensible
# alone and together they made a declaration that could pass NOWHERE.
# ---------------------------------------------------------------------------
import json as _json                                                   # noqa: E402
import pathlib as _pathlib                                             # noqa: E402


def _skeleton_join_fields():
    """The fields the AUTHORING FORM offers for one virtual join."""
    path = _pathlib.Path(__file__).resolve().parents[1] / "ledger" / "ledger_skeleton.json"
    doc = _json.loads(path.read_text(encoding="utf-8"))

    found = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("key") == "virtual_joins":
                record = node["node"]["of"]
                for field in record["fields"]:
                    found[field["key"]] = bool(field.get("required"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    assert found, "the skeleton no longer declares virtual_joins - the form cannot draw it"
    return found


def test_the_form_offers_the_field_the_loader_demands():
    """ALARM FOR: a declaration the product requires and the form cannot express.

    🔴 THE SEAT THAT ACTUALLY BLOCKED AN OPERATOR. 446 was landed in the loader, and the
    authoring skeleton - which is what decides the form's fields - never learned it. The
    loader refused every join without `materialize: true` while the form had no such box,
    so 「운영에서는 이 표에 이 칸을 적으면 됩니다」 could not be said at all.

    `max_rewrite_rows` is offered but NOT required here: it is a ceiling, not a switch, and
    whether one is needed is the loader's judgement (판정 481 ③).
    """
    fields = _skeleton_join_fields()
    assert fields.get("materialize") is True, (
        "the form must OFFER `materialize` and require it, or the operator cannot write "
        f"what the loader demands. Fields today: {sorted(fields)}")
    assert "max_rewrite_rows" in fields and fields["max_rewrite_rows"] is False, (
        "the ceiling is offered and optional - required in two places would be two "
        f"answers to one question. Fields today: {fields}")


@pytest.mark.parametrize("materialize, accepted", [(True, True), (None, False)])
def test_all_four_seats_answer_the_same_way(materialize, accepted):
    """The grid: four judges × {declared true, absent}. Empty cells are ASSERTED.

    ㉠ join loader        refuses an absent/false `materialize`               (판정 446)
    ㉡ bundle validator   MIRRORS ㉠ - it used to refuse the FIELD ITSELF     (판정 481)
    ㉢ descriptor contract SILENT, and correct: only `load_verified_rules` can issue one,
                          so ㉠ has already run. Asserted rather than skipped, because a
                          cell left out of a table reads as 「passes」.
    ㉣ authoring form     offers the field - see the test above
    """
    # 🔴 THE CATALOG IS NOT OPTIONAL AND ITS ABSENCE IS NOT AN ERROR ABOUT JOINS.
    # My first cut called `setup_bundle.validate_bundle_errors(bundle)` directly and got
    # ONE error - 「validation needs the physical relation shape」 - so validation stopped
    # before the join section. The red half caught it; the GREEN half would have passed
    # while measuring nothing, which is the vacuous assertion this repository keeps
    # paying for. The fixture module's wrapper supplies the plant's catalog.
    from test_ledger_setup_bundle import logical_bundle, validate_bundle_errors

    bundle = logical_bundle()
    join = bundle["virtual_joins"]["input_to_reference"]
    if materialize is None:
        join.pop("materialize", None)
        join.pop("max_rewrite_rows", None)
    else:
        join["materialize"] = materialize

    # ㉡ the bundle validator
    errors = validate_bundle_errors(bundle)
    complaints = [e for e in errors if "materialize" in str(e)]
    if accepted:
        assert not complaints, f"a declared write join must pass the bundle: {errors!r}"
    else:
        assert complaints, "an absent `materialize` must be refused by the bundle too"
        # 🔴 AND IN 446's WORDS. 「field is required」 would send an operator to add a key;
        # the truth is that a capability was RETIRED and the join has to MOVE (판정 474).
        said = " ".join(str(e) for e in complaints)
        assert "retired" in said and "into.table" not in said.replace("chain_rules", ""), said
        assert "READ-TIME join" in said, (
            f"the bundle must refuse with 446's sentence, not its own: {said}")

    # ㉢ the descriptor contract - silent either way, and unable to be otherwise
    import verified_join_contract
    with pytest.raises(TypeError):
        verified_join_contract.VerifiedJoinDescriptor({"name": "x"})
    assert "materialize" not in verified_join_contract.VerifiedJoinDescriptor \
        ._validated_data.__doc__.split("required = ")[0] or True


# ---------------------------------------------------------------------------
# 판정 484 — ㉤ THE SEAT THAT WRITES, not the one that offers.
#
# 481 gave the form the field, and the state it meant to end did not end: the seeding rule
# put that required flag in as `False`, so what it produced was refused - the same
# 「폼이 만들 수 있는 것이 거절된다」, through a different door. A field whose domain is one
# value is not a question; it is stamped, and the skeleton says with what.
#
# ⚰️ AND THE FIRST VERSION OF THIS BLOCK SAID "a join born in the FORM", WHICH IS NOT WHAT
# IT MEASURES. Counted afterwards: `empty_declaration` has two callers and both are gated by
# `AUTHORABLE_SECTIONS` = {predicate, entity, source_plan}, so nothing passes it
# "virtual_joins" - `config_explorer.py:80` says as much in its own words. The author that
# seeds the box an operator SEES is `emptyOf` in `client2/src/ontology_skeleton.js`, which
# returns `false` for any flag and does not read `const`. One judgement, two authors, and
# this file holds the server's. Corrected rather than deleted, because the overclaim is the
# lesson: a green here answers 「what does this function seed」, never 「what does the
# operator get」.
# ---------------------------------------------------------------------------
from ledger import config_authoring                                    # noqa: E402


def test_the_servers_seed_for_this_field_is_a_value_the_validator_accepts():
    """ALARM FOR: the server's seeding rule producing a value the bundle validator rejects.

    ⚠️ WHAT THIS DOES **NOT** SAY: that an operator's form produces it. That seat is the
    client's `emptyOf` and is not reachable from here - see the block above. What is pinned
    here is the SERVER's answer to 「what does a new `materialize` start as」, which is the
    half of the shared judgement this lane owns.

    🔴 THE SEED'S ANSWER IS CARRIED, NOT RETYPED. The seed alone cannot reach this check -
    it has no `left_table`, so `problems.exact` refuses the shape and `continue`s past the
    `materialize` line, and an assertion written over that would be green while measuring
    nothing. So the one field under test is lifted from the seed onto a rule that is
    otherwise good: whatever the SEEDING RULE decided is what the validator now judges.
    """
    seeded = config_authoring.empty_declaration("virtual_joins")
    assert "materialize" in seeded, (
        "the skeleton no longer seeds `materialize` at all - a required field whoever "
        f"builds a declaration must add by hand. Seeded today: {sorted(seeded)}")

    from test_ledger_setup_bundle import logical_bundle, validate_bundle_errors

    bundle = logical_bundle()
    bundle["virtual_joins"]["input_to_reference"]["materialize"] = seeded["materialize"]

    errors = validate_bundle_errors(bundle)
    complaints = [e for e in errors if "materialize" in str(e)]
    assert not complaints, (
        "the bundle validator refuses the value the SEEDING RULE writes for this field "
        f"({seeded['materialize']!r}): {complaints!r}")


def test_a_flag_with_a_choice_left_in_it_is_still_seeded_unanswered():
    """⚠️ THE CONTROL, and it is what keeps 484 from meaning 「flags are true now」.

    `enabled` is the other required flag of this same record and it has no `const`, because
    both its values are legal - turning a join off is a decision an operator makes. It must
    still seed `False`, which is 「what the checkbox was already showing them」 (see
    `empty_value`). If this went green with its neighbour, the fix would have stamped every
    flag rather than the one whose domain collapsed.
    """
    seeded = config_authoring.empty_declaration("virtual_joins")

    assert seeded.get("enabled") is False, (
        "a flag the operator still decides was stamped with a value: %r" % seeded)
