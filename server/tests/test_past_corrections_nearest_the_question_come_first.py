"""Lead 11-11 (안 1 · ㄱ · ㄱ): an AI rule's past corrections are the scope's, nearest the question in meaning first -
`help_guides.by_meaning`, the one ranking the guides' answer calls too. No embedding model, an equal meaning or a
failed embedding: newest first, the failure said in one line. The question side is one embedding call for every
group of a prompt, and the memory's vectors file is its own - the guides' vectors stay.

    rows      seven corrections of one rule: three of particles (oldest), four of scratches (newest)
    model     a fake embedding: [speaks of particle, speaks of scratch, 0.01] - `help_guides._model` names it
"""
import json
import logging
import os

import pytest

import paths
from admin import help_guides
from chain import ask_rule
from database import crud, models, schemas
from utils import llm

SPEC = {"output": {"cells": ["summary_text"]}}            # no memory block: the shipped table, the newest five
PURPOSE = "eval_summary"
ROWS = [("W%d" % n, "scratch led" if n > 3 else "scratch", "particle led" if n <= 3 else "scratch on edge",
         "2026-11-%02d" % n) for n in range(1, 8)]


@pytest.fixture
def memory(db_session, monkeypatch):
    with open(os.path.join(os.path.dirname(__file__), "..", "declarations", "table_config.json"), encoding="utf-8") as f:
        monkeypatch.setitem(crud.TABLE_CONFIG, ask_rule.MEMORY_TABLE, json.load(f)[ask_rule.MEMORY_TABLE])
    crud.apply_batch_updates(db_session, ask_rule.MEMORY_TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(source_name=crud.CHAIN_SOURCE, updated_by=PURPOSE, updates={
            "purpose": PURPOSE, "situation": json.dumps({"wafer_id": wafer}), "cell": "summary_text", "ai": ai,
            "right": right, "at": at}) for wafer, ai, right, at in ROWS]))
    db_session.commit()
    yield db_session
    db_session.rollback()
    db_session.query(models.DYNAMIC_TABLES[ask_rule.MEMORY_TABLE]).delete()
    db_session.commit()


@pytest.fixture
def meaning(monkeypatch, tmp_path):
    """The fake model: `meaning.made` each embedding request's inputs; `meaning.state["fail"]` raises from the next."""
    made, state = [], {"fail": None, "flat": False}

    def embed(texts):
        made.append(list(texts))
        if state["fail"]:
            raise state["fail"]
        return [[0.0, 0.0, 1.0] if state["flat"] else
                [1.0 if "particle" in t else 0.0, 1.0 if "scratch" in t else 0.0, 0.01] for t in texts]

    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(help_guides, "_model", lambda: "fake-embed")
    monkeypatch.setattr(llm, "embed", embed)
    embed.made, embed.state = made, state
    return embed


def _wafers(block):
    return [line.split('"wafer_id": "')[1][:2] for line in block.splitlines()[1:]]


def test_the_question_picks_the_corrections_nearest_it(memory, meaning):
    asks = [({"wafer_id": "W9"}, "particle near the notch"), ({"wafer_id": "W9"}, "scratch across the die")]
    particle, scratch = ask_rule.memory_blocks(memory, SPEC, PURPOSE, asks)
    assert _wafers(particle)[:3] == ["W3", "W2", "W1"], particle      # the particle ones, newest of them first
    assert _wafers(scratch)[:4] == ["W7", "W6", "W5", "W4"], scratch
    assert _wafers(particle) != _wafers(scratch), "the question changes what is carried"


@pytest.mark.parametrize("how", ["no model", "equal meaning", "failed"])
def test_newest_first_without_a_meaning_and_a_failure_says_why(memory, meaning, monkeypatch, caplog, how):
    if how == "no model":
        monkeypatch.setattr(help_guides, "_model", lambda: None)
    elif how == "equal meaning":
        meaning.state["flat"] = True
    else:
        meaning.state["fail"] = llm.LlmRefused("the gateway said 503")
    clock = {}
    with caplog.at_level(logging.WARNING, logger="Chain"):
        [block] = ask_rule.memory_blocks(memory, SPEC, PURPOSE, [({"wafer_id": "W9"}, "particle")], clock)
    assert _wafers(block) == ["W7", "W6", "W5", "W4", "W3"], block
    said = [r.getMessage() for r in caplog.records if "past corrections" in r.getMessage()]
    if how == "failed":
        assert len(said) == 1 and said[0].startswith(
            "[ChainRule] eval_summary: past corrections went newest first, not nearest the question - "
            "embedding failed: LlmRefused: the gateway said 503"), said
        assert clock["memory_by"].startswith("newest first (embedding failed")
    else:
        assert said == [] and clock["memory_by"] == ("newest first" if how == "no model" else "embedding")


def test_every_group_of_a_prompt_is_one_embedding_call_and_the_guides_vectors_stay(memory, meaning):
    guide = [{"name": "g: one", "text": "particle"}, {"name": "g: two", "text": "scratch"}]
    help_guides.by_meaning(guide, ["x"], [0, 0], "bm25", help_guides.GUIDES_CACHE, "fake-embed")
    asks = [({"wafer_id": "W%d" % n}, "particle %d" % n) for n in range(3)]
    ask_rule.memory_blocks(memory, SPEC, PURPOSE, asks)
    del meaning.made[:]
    ask_rule.memory_blocks(memory, SPEC, PURPOSE, asks)
    assert [len(inputs) for inputs in meaning.made] == [3], "the rows' vectors kept, the three questions one call"
    del meaning.made[:]
    help_guides.by_meaning(guide, ["y"], [0, 0], "bm25", help_guides.GUIDES_CACHE, "fake-embed")
    assert meaning.made == [["y"]], "the guides' vectors were not dropped by the memory's"


def test_the_scope_keeps_its_own_and_the_meaning_only_orders_them(memory, meaning):
    spec = dict(SPEC, prompts={"memory": {"scope": ["wafer_id"]}})
    [block] = ask_rule.memory_blocks(memory, spec, PURPOSE, [({"wafer_id": "W2"}, "scratch")])
    assert _wafers(block) == ["W2"], block


def test_the_vectors_file_is_written_once_however_many_batches(meaning, monkeypatch):
    """Written after every batch it was quadratic - 1,000 rows took 61 s the first time (B 11-11)."""
    replaced = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: replaced.append(b) or real(a, b))
    pieces = [{"name": "", "text": "row %d" % n} for n in range(3 * help_guides.EMBED_BATCH + 1)]
    help_guides.by_meaning(pieces, ["q"], list(range(len(pieces))), "newest first", "probe", "fake-embed")
    assert len(meaning.made) == 5 and len(replaced) == 1, (len(meaning.made), replaced)
    del replaced[:], meaning.made[:]
    help_guides.by_meaning(pieces, ["q"], list(range(len(pieces))), "newest first", "probe", "fake-embed")
    assert meaning.made == [["q"]] and replaced == [], "nothing new: no piece asked, nothing written"
