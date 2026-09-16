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
