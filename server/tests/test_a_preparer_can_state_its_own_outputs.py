# -*- coding: utf-8 -*-
"""The square asked for a fact the code already held.

`prepare.output_columns` was a free square an operator had to fill by hand, and the
completion test ("say how to declare it in two lines") failed on exactly that clause:

    before  「<이 표>에 <이 칸>을 적고, 준비기가 새로 만드는 컬럼 이름도 같이 적으면 됩니다」
    after   「<이 표>에 <이 칸>을 적으면 됩니다」

Measured 2026-09-05: `lot-event-live-frame` emits seven names and every one of them is a
module constant -- `_event_outputs` takes its VALUES from the rows and its KEYS from the
code -- and `prepare_outputs` refuses when the declaration disagrees. So the operator's
degrees of freedom there are zero, and the owner already ruled on squares like that
(2026-08-20): a declaration with no freedom is a copy, and `state="derived"` is the mark.

⛔ "IT DID NOT SAY" IS THE DEFAULT AND IS NOT "IT ADDS NOTHING". Two preparers ship and
both happen to know their own outputs; turning that into "preparers know" would be a
description of those two. A silent class leaves the square exactly as it is.

🔴 AND THE RUNTIME COMPARISON MUST STAY UNCHANGED. If `_assemble_prepared_frame` scored
the produced columns against the CLASS rather than against the DECLARATION, it would be
comparing the class with itself -- and the refusal that makes this square zero-freedom in
the first place would go vacuous. The last test here pokes exactly that.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import implementations as impl                       # noqa: E402
from ledger.config_authoring import authoring_plan               # noqa: E402
from ledger.source_preparation import BaseSourcePreparer, SourcePreparationError  # noqa: E402
from mappers import ledger_v2_lot_event_role_mapper as live      # noqa: E402

LIVE_ID = "lot-event-live-frame"
JOIN_ID = "direct-join"


def prepare_clause(implementation_id, output_columns):
    return {"implementation_id": implementation_id, "implementation_version": 1,
            "input_columns": [], "output_columns": output_columns,
            "accepts_verified_join_rules": False, "inherit_virtual_join_rules": []}


#: The block that yields this square is gated on `if physical:` -- a source whose relation
#: is not in the catalog has no column squares at all -- so the fixture carries one.
CATALOG = {"lot_event": {"columns": {"lot_id": "string", "event_type": "string",
                                     "txn_seq": "string", "event_time": "timestamp"}}}


def plan_row(implementation_id, output_columns, source_id="s"):
    bundle = {"sources": {source_id: {
        "relation": "lot_event",
        "read": {}, "map": {}, "bind": {},
        "prepare": prepare_clause(implementation_id, output_columns)}}}
    rows = authoring_plan(bundle, CATALOG)["fields"]
    return next(r for r in rows
                if r["path"] == f"bundle.sources.{source_id}.prepare.output_columns")


# ------------------------------------------------------- gate 1: the seven come from code

def test_the_class_states_exactly_what_it_emits():
    """🔴 SCORED AGAINST THE EMISSION, not typed twice. `prepare_outputs` builds its keys
    from `LIVE_LOT_EVENT_OUTPUT_MAP` plus three module constants; adding one there without
    adding it to the declaration turns this red."""
    emitted = set(live.LIVE_LOT_EVENT_OUTPUT_MAP) | {
        live.EVENT_GROUP_COLUMN, live.SOURCE_EVENT_INCOMPLETE_COLUMN,
        live.SOURCE_ROW_EXCLUDED_COLUMN}
    assert set(live.LiveLotEventSourcePreparer.declared_output_columns) == emitted
    assert len(emitted) == 7


def test_the_operator_writes_none_of_them():
    row = plan_row(LIVE_ID, {})
    assert row["state"] == "derived"
    assert set(row["value"]) == set(impl.preparer_output_columns(LIVE_ID))
    assert len(row["value"]) == 7


def test_the_filled_value_is_the_file_shape_and_not_a_name_list():
    """⚠️ `filled_declaration` WRITES a derived value into the document, and
    `_column_types` refuses anything that is not `{column: type}`. A list of names here
    would fill the square with a shape the validator then refuses -- on the very square
    that said it had filled itself."""
    value = plan_row(LIVE_ID, {})["value"]
    assert isinstance(value, dict)
    assert all(isinstance(v, str) and v for v in value.values())


def test_the_fill_names_what_filled_it():
    row = plan_row(LIVE_ID, {})
    assert row["ground"]["from_paths"] == ["bundle.sources.s.prepare.implementation_id"]
    assert LIVE_ID in row["ground"]["text"]


# ---------------------------------------------------- gate 2: direct-join does not move

def test_a_silent_preparer_leaves_the_square_a_question():
    """🔴 GATE 3. Not dead, not blank: the row it had before, asked the way it was asked."""
    row = plan_row(JOIN_ID, {})
    assert row["state"] == "unanswered"
    assert row["value"] == []
    assert row["ground"]["rule"] == "preparer_output_collision_from_relation"


def test_a_silent_preparer_that_declared_something_still_reads_answered():
    row = plan_row(JOIN_ID, {"made_up": "string"})
    assert row["state"] == "answered"
    assert row["value"] == ["made_up"]


def test_direct_join_says_nothing_and_that_is_the_default():
    assert impl.preparer_output_columns(JOIN_ID) is None
    assert BaseSourcePreparer.declared_output_columns is None


# ------------------------------------------------------- the read-back is off the class

def test_an_inherited_answer_is_not_lent_to_a_subclass():
    """`__dict__`, not `getattr`, for the reason the identity read uses it: a subclass that
    adds one column would otherwise get a declaration filled in that is short by one."""
    class Quiet(live.LiveLotEventSourcePreparer):
        implementation_id = "probe-quiet-subclass"
        implementation_version = 1
    assert Quiet.__dict__.get("declared_output_columns") is None
    assert impl.preparer_output_columns("probe-quiet-subclass") is None


def test_an_unregistered_or_blank_name_answers_none_rather_than_guessing():
    for name in (None, "", "   ", "no-such-preparer", 7):
        assert impl.preparer_output_columns(name) is None
    assert impl.preparer_output_columns(LIVE_ID, 99) is None


# ------------------------------------------ gate 5: the runtime refusal is NOT made vacuous

def frame():
    pd = pytest.importorskip("pandas")
    return pd.DataFrame([{"lot_id": "L1", "event_type": "track_in", "slotnumbers": "1",
                          "waferids": "W1", "parent_lot": "", "child_lot": "",
                          "txn_seq": "7", "event_time": "2026-09-05T00:00:00+00:00"}])


def context_declaring(output_columns):
    preparer = SimpleNamespace(output_columns=tuple(output_columns))
    return SimpleNamespace(source_plan=SimpleNamespace(driver=SimpleNamespace(
        preparation=SimpleNamespace(preparer=preparer))))


def test_the_truthful_declaration_is_accepted():
    got = live.LiveLotEventSourcePreparer().prepare_outputs(
        context_declaring(live.LiveLotEventSourcePreparer.declared_output_columns),
        frame(), {})
    assert set(got) == set(live.LiveLotEventSourcePreparer.declared_output_columns)


@pytest.mark.parametrize("bend", ["drop", "add"])
def test_a_declaration_that_disagrees_is_still_refused(bend):
    """🔴 THE ANTI-VACUITY POKE. The derivation feeds the FORM; the runtime keeps scoring
    the produced columns against the DECLARATION. If someone routes the class's own answer
    into this comparison, both arms below go green and the zero-freedom property that
    justified deriving the square disappears with them."""
    declared = dict(live.LiveLotEventSourcePreparer.declared_output_columns)
    if bend == "drop":
        declared.pop("event_group_key")
    else:
        declared["a_column_nothing_emits"] = "string"

    with pytest.raises(SourcePreparationError) as caught:
        live.LiveLotEventSourcePreparer().prepare_outputs(
            context_declaring(declared), frame(), {})
    assert caught.value.code == "unsupported_source_preparer_output"
