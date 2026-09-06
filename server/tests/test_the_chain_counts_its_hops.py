# -*- coding: utf-8 -*-
"""Between "the chain may never wake the chain" and "opt in, then unbounded" there was nothing.

The owner's words: 「원래는 체인이 체인 유발 아예 막았는데 너무 빡빡해서 풀었더니 이래 된
거네, 깊이 넣으면 될 듯」. `source_name == "chain_ingestion"` says WHETHER the chain wrote a
row; it cannot say HOW MANY hops produced it, so `allow_chain_trigger` opted a rule in and
then had no further word to say. The only brake was the loader's static cycle check, which
runs before the worker starts and cannot see a cascade that is long rather than circular.

Measured 2026-09-06 before this: nothing anywhere in the server counted hops.

⚠️ THREE STATES, NOT TWO. No key means "not written by the chain" -- such an event must
never be refused for depth. A key means the chain wrote it, INCLUDING when the number is 0.
Folding absence into zero loses the distinction exactly where it decides.

⛔ AND THE STATIC CHECK IS UNTOUCHED. Relaxing it in the same round would open a real
unbounded loop wherever the depth failed to bite; depth has to be shown to bite first.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402
from database import models                                      # noqa: E402
from database.context import request_chain_depth                 # noqa: E402


# --------------------------------------------------------- the three states are separate

def test_an_event_from_outside_the_chain_has_no_depth():
    """🔴 GATE ③. It is not deep, it is not shallow -- it is not the chain's."""
    assert event_constants.chain_depth_of({"source_name": "user"}) is None
    assert event_constants.chain_depth_of({}) is None


def test_zero_is_a_number_and_not_an_absence():
    assert event_constants.chain_depth_of({"chain_depth": 0}) == 0


def test_a_depth_reads_back_as_itself():
    assert event_constants.chain_depth_of({"chain_depth": 4}) == 4


@pytest.mark.parametrize("junk", [None, "3", True, 3.5, [3]])
def test_a_value_that_is_not_a_whole_number_is_not_a_depth(junk):
    """⚠️ `True` is an `int` in Python. A boolean here would be read as depth 1 and refuse
    a cascade one hop early, which is the kind of wrong that looks right."""
    assert event_constants.chain_depth_of({"chain_depth": junk}) is None


# ----------------------------------------------------------- the limit is a DECLARATION

def test_the_limit_comes_from_the_declaration():
    assert event_constants.max_chain_depth({"max_chain_depth": 2}) == 2


def test_a_config_that_predates_the_key_gets_the_default():
    """Not the answer, just what a config written before this existed gets."""
    assert event_constants.max_chain_depth({"rules": []}) == \
        event_constants.DEFAULT_MAX_CHAIN_DEPTH


@pytest.mark.parametrize("junk", [0, -1, "8", True, None, 3.5])
def test_a_limit_that_is_not_a_positive_whole_number_falls_back(junk):
    assert event_constants.max_chain_depth({"max_chain_depth": junk}) == \
        event_constants.DEFAULT_MAX_CHAIN_DEPTH


def test_the_sample_declares_the_limit():
    """⛔ THE SAMPLE, WHICH IS WHAT SHIPS. The live file is gitignored, so this is the half
    a test can hold; the live one was set in the same edit and reported."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc = json.load(open(os.path.join(here, "config", "sample",
                                      "chain_rules.json.sample"), encoding="utf-8"))
    assert isinstance(doc.get("max_chain_depth"), int) and doc["max_chain_depth"] >= 1


# ------------------------------------------------------- ㉰ the stamp is in ONE place

def test_only_the_envelope_stamps_the_depth():
    """🔴 GATE ④, COUNTED. Ten mappers spell `source_name: "chain_ingestion"` in the rows
    they return, and stamping depth beside each would be ten places to keep in step. The
    outbox envelope is built once (`database._outbox_envelope`), so the worker sets one
    context var and both stagers read it."""
    import inspect

    from database import database as db_module

    stampers = [name for name, obj in vars(db_module).items()
                if inspect.isfunction(obj)
                and event_constants.CHAIN_DEPTH_KEY in inspect.getsource(obj)]
    assert sorted(stampers) == ["_outbox_envelope", "stage_collapsed_event", "stage_event"], \
        stampers


def test_the_worker_sets_it_once_and_resets_it():
    """A depth left set would stamp the next write, and the next write may not be the
    chain's at all."""
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.process_chain_transaction_group)
    assert body.count("request_chain_depth.set(") == 1
    assert "request_chain_depth.reset(" in body


def test_the_depth_is_one_more_than_what_woke_it():
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.process_chain_transaction_group)
    assert "incoming_depth + 1" in body


# ------------------------------------------------- ㉱ over the limit refuses, and says so

def test_the_refusal_is_in_one_place_and_is_not_silent():
    """🔴 GATE ①. Not inside `_rule_accepts_event`: that predicate is called five times per
    event, so refusing there would log five times or say nothing at all -- and saying
    nothing is the failure this mechanism replaces."""
    import inspect

    import chain_ingestion_worker as worker

    predicate = inspect.getsource(worker._rule_accepts_event)
    assert event_constants.CHAIN_DEPTH_KEY not in predicate
    assert "chain_depth_of" not in predicate

    loop = inspect.getsource(worker.start_chain_ingestion_worker)
    assert loop.count("chain_depth_of(") == 1, "the limit is decided in more than one place"
    assert "[Chain Depth]" in loop, "the refusal does not name itself"
    assert "max_chain_depth" in loop


def test_the_refused_row_is_finished_not_left_pending():
    """⚠️ THE LESSON FROM `92d1c1ff`, ONE FILE AWAY. An over-deep event left
    `processed_chain=False` would be re-read on every tick forever and block the queue
    behind it -- the poisoned-row defect, reintroduced by a new feature."""
    import inspect

    import chain_ingestion_worker as worker

    loop = inspect.getsource(worker.start_chain_ingestion_worker)
    head = loop.split("[Chain Depth]", 1)[1][:600]
    assert "mark_processed(event" in head
    assert "db.commit()" in loop.split("[Chain Depth]", 1)[1][:1200]


def test_the_static_cycle_check_is_untouched():
    """⛔ NOT RELAXED THIS ROUND. Depth and the loader's refusal answer different questions
    -- one bounds a long cascade, the other rejects a circular one -- and dropping the
    second before the first is shown to bite opens a real unbounded loop."""
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker._validate_chain_cascade_graph)
    assert "cycle" in body and "raise" in body
    assert event_constants.CHAIN_DEPTH_KEY not in body
