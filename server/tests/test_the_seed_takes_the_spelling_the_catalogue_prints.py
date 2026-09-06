# -*- coding: utf-8 -*-
"""C-25: `/declaration` prints `wafer@1`; seeding with that spelling must WALK.

🔴 WHY THIS IS AN ABSENCE AND NOT A LENIENCY. The catalogue publishes versioned entity
names and the ledger writes bare ones. `collect` already trims the version on BOTH sides,
so a caller who reads one axis off the catalogue is right and a caller who reads the other
axis off the same catalogue is silently wrong. The two axes disagreed about one declaration.

🔴 AND THE WRONG ANSWER LOOKED LIKE A SHY ONE. A versioned seed named a `subject_type` with
no rows, so the walk came back with the seed node alone - which renders as 「여기 아무것도
없다」 rather than 「버전을 붙여 물으셨습니다」. That is the failure this file exists to
keep closed.

🔴 THE FIXTURE IS PART OF THE ASSERTION. The bare seed must reach MORE THAN ITSELF, or the
comparison in `test_the_versioned_spelling_answers_what_the_bare_one_answers` passes for a
graph of one node and the repair could be deleted without turning it red.
"""
from datetime import datetime, timezone
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger_explorer                                          # noqa: E402
import pytest                                                   # noqa: E402
from ledger_api import ledger_subgraph                          # noqa: E402


NOW = datetime(2026, 9, 7, 3, 0, tzinfo=timezone.utc)
EVENT = str(uuid.UUID("3101e12e-c814-58f4-87cf-c8e31084e923"))


def _lookup():
    """One Lot that CONTAINS one Wafer, both spelled bare - the way the ledger writes."""
    atom = ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=251)), subject_type="Lot", subject_keys={"lot": "L-25"},
        predicate="contains", object_kind="entity_ref",
        object_payload={"type": "Wafer", "keys": {"wafer": "W-25"}, "qualifiers": {}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1",
        source_raw_ref="row:251", supersedes=None, source_event_id=EVENT,
        source_event_state="source_molecule")
    return ledger_subgraph.InMemoryEvidenceLookup([atom])


BARE = ledger_explorer.entity_id("Lot", {"lot": "L-25"})
VERSIONED = ledger_explorer.entity_id("Lot@1", {"lot": "L-25"})


def test_the_two_spellings_are_different_ids_or_this_file_proves_nothing():
    """🔴 THE PREMISE, ASSERTED. The id encodes the type verbatim, so the versioned and
    bare spellings mint DIFFERENT tokens. If they were ever the same string, every other
    test here would pass with the repair removed."""
    assert BARE != VERSIONED


def test_the_bare_spelling_reaches_more_than_itself():
    """The baseline, and the thing that makes the comparison below non-vacuous."""
    body = ledger_subgraph.subgraph(BARE, _lookup(), hops=2)
    assert len(body["nodes"]) > 1, "the fixture must walk somewhere or nothing is proved"
    assert body["edges"], "the fixture must have an edge or nothing is proved"


def test_the_versioned_spelling_answers_what_the_bare_one_answers():
    """🔴 THE GATE. `/declaration` prints `Lot@1`; that spelling must answer identically.

    Compared as SETS OF IDS rather than as whole bodies: the response also carries counts
    and budget flags, and pinning those would make this red for reasons that have nothing
    to do with the spelling.
    """
    bare = ledger_subgraph.subgraph(BARE, _lookup(), hops=2)
    versioned = ledger_subgraph.subgraph(VERSIONED, _lookup(), hops=2)
    assert {n["id"] for n in versioned["nodes"]} == {n["id"] for n in bare["nodes"]}
    assert len(versioned["edges"]) == len(bare["edges"])


def test_the_answer_names_the_seed_it_actually_used():
    """🔴 A SEED THAT WAS REWRITTEN SAYS SO. The caller sent the versioned token; the walk
    ran on the canonical one, and the response points at the one it ran on. Echoing the
    caller's spelling back would leave the client keyed on an id no node in the answer has,
    which is the same two-identities defect one layer out."""
    body = ledger_subgraph.subgraph(VERSIONED, _lookup(), hops=2)
    assert body["seed"]["id"] == BARE
    assert [item["id"] for item in body["seeds"]] == [BARE]


def test_the_bare_spelling_is_not_rewritten():
    """No-regression: an id with no version in it comes back byte-identical."""
    assert ledger_subgraph._canonical_seed(BARE) == BARE
    body = ledger_subgraph.subgraph(BARE, _lookup(), hops=2)
    assert body["seed"]["id"] == BARE


def test_a_seed_that_is_not_an_entity_id_is_still_refused_by_the_one_refuser():
    """🔴 THE TRIM DOES NOT SWALLOW ANYTHING. A non-entity id passes through unchanged so
    `decode_node_id` keeps being the single place that refuses, with its own wording."""
    assert ledger_subgraph._canonical_seed("claim:v1:whatever") == "claim:v1:whatever"
    with pytest.raises(ValueError, match="ledger-entity:v1"):
        ledger_subgraph.subgraph("claim:v1:whatever", _lookup(), hops=2)


def test_one_subject_asked_two_ways_is_one_subject():
    """The conflict check now sees through the spelling.

    Before the seed was canonicalised, `Lot@1` positive and `Lot` negative were two keys
    and BOTH got through - the same subject counted as observed and as a control in one
    walk. This is a consequence of the repair, asserted so that removing the repair cannot
    quietly restore it.
    """
    with pytest.raises(ValueError, match="both observed and a control"):
        ledger_subgraph.subgraph({"positive": [VERSIONED], "negative": [BARE]},
                                 _lookup(), hops=2)
