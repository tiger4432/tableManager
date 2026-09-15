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
    import enrichment.config as ec
    import virtual_join.config as vjc

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

    assert names == ["s234_flat", "s234_unified",
                     "enrichment_dedup:s234_enrich", "enrichment_auto_confirm:s234_enrich",
                     "virtual_join:s234_join"]
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
    assert names == ["s234_unified", "enrichment_auto_confirm:s234_enrich",
                     "virtual_join:s234_join"]
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
