# -*- coding: utf-8 -*-
"""A red test run does not block activation, and the screen has to be able to know that.

Owner, 2026-09-04: "the ontology has not run in production for a month", and the test run
refuses with "the time column is empty" on a source whose time column is filled.

`activate` refuses on ONE thing - the snapshot compare-and-swap - and a test result is not
it. But nobody presses activate beside a red panel, so declarations that were activatable
the whole time were never activated. The screen was not wrong; the server never told it
what actually blocks.

⛔ VALUES, NOT SENTENCES. The codes here are the ones `activate` itself raises, so the two
cannot drift, and the wording stays in the client where it belongs.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.config_drafts import OntologyDraftStore as DraftStore                      # noqa: E402


class _Index:
    def __init__(self, snapshot_hash, nodes=None):
        self.snapshot_hash = snapshot_hash
        self.nodes = nodes or {}


def record(base_hash, *, target_key="sources.probe", creates=False):
    return {"draft_id": "d1", "target_key": target_key,
            "creates_declaration": creates, "base_snapshot_hash": base_hash}


def test_nothing_blocks_when_the_base_still_matches():
    """🔴 THE ANSWER THAT WAS MISSING. An empty list is "you may activate now" - and for a
    month there was no way to say it, so a red test run was read as a closed door."""
    assert DraftStore.activation_blockers(record("h1"), _Index("h1")) == []


def test_the_one_real_blocker_is_named_by_the_code_activate_raises():
    """When the file HAS moved, activation genuinely refuses - and it refuses with this
    name, so the list must carry the same one rather than a paraphrase."""
    blockers = DraftStore.activation_blockers(record("h1"), _Index("h2"))
    assert len(blockers) == 1
    assert blockers[0].endswith("_draft"), blockers
    assert blockers[0].removesuffix("_draft") == DraftStore.stale_status(
        record("h1"), _Index("h2"))


def test_it_answers_without_writing_anything():
    """⚠️ `activate` records the status it finds; this must not, or a screen polling it
    would rewrite draft history. The record it is handed comes back untouched."""
    given = record("h1")
    before = dict(given)
    DraftStore.activation_blockers(given, _Index("h2"))
    assert given == before


# 🔴 THE OTHER HALF - `"blocks_activation": False` in the test run's own result - IS NOT
# TESTED HERE, and that is said rather than faked. `_test_run` needs a live service, an
# engine and a compiled setup, and the test written first asserted on the method's SOURCE
# TEXT: that measures letters, not behaviour, and this repository forbids it. It was run,
# it failed for an unrelated reason, and it was deleted rather than repaired.
#
# What that field is, is a constant in the returned dict; what would catch its loss is the
# client reading the field, which is where it is consumed.
