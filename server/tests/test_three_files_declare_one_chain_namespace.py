# -*- coding: utf-8 -*-
"""S-234 ①②③ (판정 408 · 409). Three rule files, one namespace, one off switch, one boot line.

🔴 THE THREE FILES ARE THREE WAYS OF WRITING A CHAIN RULE. `chain_rules.json` (flat and
unified), `enrichment_rules.json` and `virtual_join_rules.json` all end in the same loaded
set, so their names are ONE set. A name that appears twice is refused BY NAME, ONCE, at the
one seat that sees the whole set - not per file. Two per-file checkers were the evidence of
two namespaces, and they are gone.

🪦 THE PROCESS SWITCH FOR 「THE DERIVED RULES」 IS GONE (판정 408). Its subject - rules the
product derived, that the operator could not see - no longer exists: the set line names every
rule whichever file wrote it. The remaining levers are `enabled: false` in the file a rule was
written in, and `ASSY_CHAIN_WORKER=0` for the whole chain. The drift oracle below has the TEXT
as its subject, which is the one shape the no-cut-and-run rule permits - and it assembles the
retired name from two halves, because the day this file spelled it out, the oracle turned red
on its own docstring the moment the file was tracked.

⚠️ EVERY CASE RUNS THE REAL LOADER OVER FILES THIS TEST WROTE. 「임시로 박스에 설정한 케이스로
재서 대답 금지」 - the live files are the owner's and are never read here.
"""
import json
import logging
import os
import subprocess
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from chain import ingestion_worker as worker                          # noqa: E402

SRC, DST = "s234_src", "s234_dst"
TABLE = {"business_key": "lot",
         "column_types": {"lot": "string", "grade": "string", "k": "string"}}

FLAT = {"name": "s234_flat", "trigger_table": SRC, "trigger_columns": ["grade"],
        "target_table": DST, "mapper": "s234_mapper", "max_group_rows": 500}
UNIFIED = {"name": "s234_unified", "on": {"table": SRC, "columns": ["grade"]},
           "derive": {"kind": "mapper", "mapper": {"mapper": "s234_mapper"}},
           "into": {"table": DST}, "limits": {"max_group_rows": 500}}
ENRICH = {"source_table": SRC, "derived_table": DST, "decision_key": ["lot"],
          "target_fields": ["grade"], "list_columns": [], "aggregations": {},
          "reference_views": [], "enabled": True}
JOIN = {"left_table": SRC, "right_table": DST, "join_key": [{"left": "k", "right": "k"}],
        "expose": ["grade"], "materialize": True, "max_rewrite_rows": 10}


@pytest.fixture()
def load(tmp_path, monkeypatch):
    """The real `load_chain_rules` over three files we wrote, returning the loaded names and
    every `[ChainRules]` line it printed."""
    import mapper_sdk
    from database import crud
    from chain.enrichment import config as ec
    from chain import legacy_join_declaration as vjc

    monkeypatch.setitem(crud.TABLE_CONFIG, SRC, dict(TABLE))
    monkeypatch.setitem(crud.TABLE_CONFIG, DST, dict(TABLE))
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s234_mapper",
                        lambda db, payloads, rule=None: {"updates": []})
    # 🔴 THE LAST CENSUS IS THIS PROCESS'S, and a case that leaves it behind would make the
    #    next case print 「지난 적재와 다름」 for a set it never loaded.
    monkeypatch.setattr(worker, "_LAST_CENSUS", None)

    def run(chain_rules, enrichment_rules, virtual_join_rules, caplog):
        for name, body in (("chain_rules.json", {"rules": chain_rules}),
                           ("enrichment_rules.json", enrichment_rules),
                           ("virtual_join_rules.json", virtual_join_rules)):
            (tmp_path / name).write_text(json.dumps(body), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(tmp_path / "chain_rules.json"))
        monkeypatch.setattr(ec, "ENRICHMENT_RULES_PATH",
                            str(tmp_path / "enrichment_rules.json"))
        monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH",
                            str(tmp_path / "virtual_join_rules.json"))
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            rules = worker.load_chain_rules()
        lines = [record.getMessage() for record in caplog.records
                 if "[ChainRules" in record.getMessage()]
        return [r.get("name") for r in rules], lines

    return run


# ---------------------------------------------------------------------------
# ③ one boot line, and a clean three-file set stands whole
# ---------------------------------------------------------------------------

def test_a_clean_set_from_three_files_stands_whole_and_prints_one_set_line(load, caplog):
    """The sensitivity control for the refusal below: a judge that refused everything would
    pass that test and refuse every deployment. And the boot line is ONE line - the old
    「Synthesized N」 tally is folded into the set line, which names every rule with where it
    came from."""
    names, lines = load([FLAT, UNIFIED], {"s234_enrich": ENRICH}, {"s234_join": JOIN}, caplog)

    # ⚰️ [소유자 정본] THE JOIN MOVED TO THE FRONT, and that is the ordering telling
    #   the truth. `rule_order` skipped a producer that carried `follow_up` - 「not on the
    #   trigger path: it fires nothing, it orders nothing」. Every producer is on the
    #   trigger path now, so the materialised join is ordered like the producer it is.
    assert names == ["virtual_join:s234_join", "s234_flat", "s234_unified",
                     "enrichment_dedup:s234_enrich",
                     "enrichment_auto_confirm:s234_enrich"]
    set_lines = [line for line in lines if line.startswith("[ChainRules] set(")]
    assert len(set_lines) == 1, lines
    assert set_lines[0].startswith("[ChainRules] set(5): ")
    for name in names:
        assert name + "[" in set_lines[0], "a loaded rule is missing from the set line"
    assert not [line for line in lines if "Synthesized" in line], "the second boot line is back"
    assert not [line for line in lines if line.startswith("[ChainRules] refused(")]


# ---------------------------------------------------------------------------
# ① one namespace - a name claimed twice is refused by name, once, naming both files
# ---------------------------------------------------------------------------

def test_a_name_written_in_two_files_is_refused_once_naming_both_files(load, caplog):
    """🔴 NEITHER COPY RUNS. Which of the two the operator meant is not a thing this product
    can know; keeping one would be resolving, and the old checkers' 「drop the synthesised
    half」 was exactly that. The line is `operator_line`-shaped: what happened, both files,
    and the next action."""
    twin = dict(FLAT, name="enrichment_dedup:s234_enrich")
    names, lines = load([twin, UNIFIED], {"s234_enrich": ENRICH}, {"s234_join": JOIN}, caplog)

    assert "enrichment_dedup:s234_enrich" not in names
    # ⚰️ [소유자 정본] same reordering as above: the materialised join is a
    #   producer on the trigger path now, so `rule_order` puts it first.
    assert names == ["virtual_join:s234_join", "s234_unified",
                     "enrichment_auto_confirm:s234_enrich"]
    refusals = [line for line in lines
                if line.startswith("[ChainRules:enrichment_dedup:s234_enrich]")]
    assert len(refusals) == 1, lines
    assert "chain_rules.json" in refusals[0] and "enrichment_rules.json" in refusals[0]
    assert "→ 다음: 두 파일 중 하나에서 이름을 바꾸십시오" in refusals[0]
    # and the census says it is among what is NOT running, beside what is
    refused = [line for line in lines if line.startswith("[ChainRules] refused(")]
    assert refused == ["[ChainRules] refused(1): enrichment_dedup:s234_enrich(name_claimed_twice)"]


def test_a_join_name_written_in_chain_rules_is_refused_the_same_way(load, caplog):
    """The join half is in the same namespace, under the same judge - not a second checker."""
    twin = dict(FLAT, name="virtual_join:s234_join")
    names, lines = load([twin], {}, {"s234_join": JOIN}, caplog)

    assert "virtual_join:s234_join" not in names
    refusals = [line for line in lines if line.startswith("[ChainRules:virtual_join:s234_join]")]
    assert len(refusals) == 1
    assert "chain_rules.json" in refusals[0] and "virtual_join_rules.json" in refusals[0]


def test_a_name_written_twice_in_one_file_is_refused_rather_than_halved(load, caplog):
    """⚠️ THE SILENT CASE. `rule_order` keys its walk by name, so before this seat a second
    copy in `chain_rules.json` was kept-and-dropped without a word - one of the five zeros
    that render identically. Now it is named, and the line points at the one file."""
    names, lines = load([FLAT, dict(UNIFIED, name="s234_flat")], {}, {}, caplog)

    assert names == []
    refusals = [line for line in lines if line.startswith("[ChainRules:s234_flat]")]
    assert len(refusals) == 1
    assert "2 번" in refusals[0]
    assert "→ 다음: chain_rules.json 에서 한쪽 선언의 이름을 바꾸십시오" in refusals[0]


# ---------------------------------------------------------------------------
# 🔴 판정 413 (S-268) - only a rule that CAN FIRE claims the name
# ---------------------------------------------------------------------------

def test_a_switched_off_twin_does_not_take_the_live_rule_down_with_it(load, caplog):
    """🔴 THE PRODUCTION REGRESSION, 2026-09-16. Refusing BOTH copies rests on 「the product
    cannot know which one was meant」 - and a copy declaring `enabled: false` is the operator
    having ALREADY said it. The owner met the other reading: the declaration was right, the
    data was right, and only the live chain path dropped the rule
    (「체인을 끄니 안 됨 · 백필하니 돈다」).

    ⚠️ AND IT IS NOT A SILENT WIN: the off copy is still in the loaded set, reported OFF,
    because 「이 이름은 꺼져 있다」 and 「이 이름은 없다」 are different answers."""
    off_twin = dict(FLAT, name="enrichment_dedup:s234_enrich", enabled=False)
    names, lines = load([off_twin, UNIFIED], {"s234_enrich": ENRICH}, {}, caplog)

    assert "enrichment_dedup:s234_enrich" in names, (
        "the live rule was dropped by a twin that cannot fire")
    assert not [line for line in lines if line.startswith("[ChainRules] refused(")], lines
    assert not [line for line in lines
                if line.startswith("[ChainRules:enrichment_dedup:s234_enrich]")], lines
    set_lines = [line for line in lines if line.startswith("[ChainRules] set(")]
    assert len(set_lines) == 1, lines
    assert "enrichment_dedup:s234_enrich[" in set_lines[0]


def test_two_switched_off_copies_refuse_nothing_and_run_nothing(load, caplog):
    """⛔ THE OTHER ARM. Two names nobody can fire are not a collision to report - there is
    no question about which was meant, because neither was. Refusing them would put a line in
    front of an operator who has nothing to fix."""
    off = dict(FLAT, enabled=False)
    names, lines = load([off, dict(UNIFIED, name="s234_flat", enabled=False)], {}, {}, caplog)

    assert not [line for line in lines if line.startswith("[ChainRules] refused(")], lines
    assert not [line for line in lines if line.startswith("[ChainRules:s234_flat]")], lines
    # ⚠️ MEASURED, NOT ASSUMED, AND IT IS ONE NAME RATHER THAN TWO. Past this judge the set
    # still reaches `rule_order`, which keys its walk by name and keeps the first copy - the
    # silent halving S-234 named for ENABLED rules. Neither copy can fire, so nothing runs
    # either way and no answer changes; what is lost is the OFF twin's row in the census.
    # Reported rather than papered over: making the census show both is a separate question
    # from this ruling, and this line is where it would be caught if it is ever answered.
    assert names == ["s234_flat"], names


def test_the_two_seats_ask_the_same_question_of_a_rule_that_cannot_fire():
    """⚠️ ONE SENTENCE, TWO SEATS, ASKED BY BEHAVIOUR. `rule_order` skips a producer that
    cannot fire (`ea8f91d2`, 「AN EDGE THAT CANNOT FIRE CANNOT ORDER ANYTHING」) and this
    judge skips a claimant that cannot fire. The regression arrived precisely because one
    seat had learned it and the other had not, so the pair is asserted together - and on
    what they DO, because a check on their source text would pass on a seat that spells
    `enabled` in a comment."""
    from chain import rule_order

    live = {"name": "s268_live", "trigger_table": SRC, "target_table": DST}
    off_back_edge = {"name": "s268_off", "trigger_table": DST, "target_table": SRC,
                     "enabled": False}

    cycles = []
    rule_order.order_rules([live, off_back_edge], on_cycle=cycles.append)
    assert cycles == [], "a rule that cannot fire ordered its neighbours"

    kept, twice = worker._refuse_names_claimed_twice(
        [dict(off_back_edge, name="s268_live"), live], ["a.json", "b.json"])
    assert twice == [], "a rule that cannot fire claimed a name"
    assert "s268_live" in [(r or {}).get("name") for r in kept]


# ---------------------------------------------------------------------------
# ② one off switch - the retired name appears nowhere under server/
# ---------------------------------------------------------------------------

def test_the_retired_synthesis_switch_is_named_nowhere_under_server():
    """Drift oracle (판정 408). ⚠️ THE TEXT IS THE SUBJECT, not a proxy for behaviour - the
    standing rule's one permitted shape. The name is assembled so this file is not a hit."""
    retired = "ASSY_CHAIN_" + "SYNTHESIZE"
    repo = os.path.dirname(server_dir)
    try:
        hits = subprocess.run(["git", "grep", "-l", retired, "--", "server"],
                              cwd=repo, capture_output=True, text=True)
    except OSError:
        pytest.skip("git is not available here")
    assert hits.returncode == 1, "still named in: " + hits.stdout
