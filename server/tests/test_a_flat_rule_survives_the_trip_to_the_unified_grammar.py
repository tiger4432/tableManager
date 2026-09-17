# -*- coding: utf-8 -*-
"""판정 536 ③ · 539. 평면 규칙을 통합으로 옮겼다가 되돌리면 «키 하나까지» 같아야 한다.

> 총괄 2026-09-17: 「이관은 «제품이 모르는 키»를 «그대로 실어 날라야» 합니다.
>  떨어뜨리면 운영에서 기능이 «조용히» 꺼집니다」

🔴 THE PROPERTY IS NOT 「the ten rules in this box round-trip」. That is a box number, and it
would go green on an installation whose rules this box never had. The subject is ANY flat
rule dict, and the cells that matter most are the ones the grammar DOES NOT KNOW - because
those are the ones a converter can drop without anything going red.

🔴 WHY THIS EXISTS EVEN THOUGH THE PROPERTY ALREADY HOLDS. 「지시받지 않은 것은 만들지
않는다」 would normally refuse a gate on behaviour nobody broke. This round is the exception
the rule allows for: it EDITS THE CONVERTER THIS PROPERTY RESTS ON (the axis cells move into
the skeleton, `derive.mapper` becomes a record). A property you are about to stand on is
worth a gate the moment you start moving it - 상설 「갈라질 수 있는 축을 표로, 그리고 «먼저»」.

⚠️ WHO READS THOSE UNKNOWN CELLS. Not this repository: they live in `server/mappers/*.py`,
which is the owner's and gitignored. 「읽는 자를 못 본다」 and 「아무도 안 읽는다」 are
different facts (판정 536 ②), and this file is the second one's refusal.
"""
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                              # noqa: E402
from chain import rule_shape                                       # noqa: E402

#: 🔴 CELLS THE CHAIN GRAMMAR DOES NOT KNOW, and the point of the whole trip. Spelled here
#: rather than read off a box rule: a fixture that took its shape from this installation
#: would stop covering the case on the day this box's rules change.
UNKNOWN_CELLS = {
    "alignment_thresholds": {"void": 0.42, "delam": 1.5},
    "x_col": "inchip_x",
    "y_col": "inchip_y",
    "primary_selector": "first",
    "list_delimiter": ",",
}

#: ⚠️ AXIS CELLS THIS BOX NEVER USES. Measured 2026-09-17: five of the fourteen axis cells
#: appear in no rule here, so a fixture built from this box would not carry them - and an
#: installation that declares `reads` or `follow_up` would be the first to find out.
AXIS_CELLS_THIS_BOX_DOES_NOT_USE = {
    "reads": ["wafer_map_metadata"],
    "follow_up": True,
    "derivation_source_table": "dt_log",
    "companion_of": "some_other_rule",
    "origin": "declared",
}

FLAT_RULE = dict(
    {
        "name": "a_flat_rule",
        "enabled": True,
        "trigger_table": "dt_log",
        "trigger_columns": ["dt_job"],
        "target_table": "dt_map",
        "mapper_module": "mappers.some_mapper",
        "mapper_function": "build",
        "is_batch": True,
        "source_table": "dt_log",
        "map_table": "dt_map",
        "allow_chain_trigger": True,
        "params": {"declared_argument": 7},
        "group_by": ["dt_job"],
        "max_group_rows": 500,
    },
    **UNKNOWN_CELLS,
    **AXIS_CELLS_THIS_BOX_DOES_NOT_USE)


def _round_trip(raw):
    """The trip an operator's 「통합으로 저장」 takes: flat -> internal -> declaration -> back."""
    internal = rule_shape.from_chain_rule(raw)
    declaration = rule_shape.to_declaration(internal)
    return rule_shape.as_chain_rule(rule_shape.from_declaration(declaration))


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the property
# ---------------------------------------------------------------------------

def test_a_flat_rule_comes_back_cell_for_cell():
    """🔴 THE GATE. Key for key and value for value - not 「the same shape」, which is what a
    converter that silently dropped a dict cell would also satisfy."""
    back = _round_trip(FLAT_RULE)

    assert back == FLAT_RULE, (
        "the trip changed the rule: lost %s · added %s"
        % (sorted(k for k in FLAT_RULE if k not in back),
           sorted(k for k in back if k not in FLAT_RULE)))


def test_the_cells_the_grammar_does_not_know_are_the_ones_that_survive():
    """⚠️ NAMED SEPARATELY, because the assertion above would still pass if the unknown cells
    were simply absent from BOTH sides of a fixture that never carried them. This one says
    they were there, and says which ones."""
    back = _round_trip(FLAT_RULE)

    for cell, value in UNKNOWN_CELLS.items():
        assert back.get(cell) == value, (
            "%r did not survive the trip - and nothing in this repository reads it, which is "
            "exactly why nothing would have gone red" % cell)


def test_the_axis_cells_this_box_never_declares_survive_too():
    """🔴 THE CASE THIS INSTALLATION CANNOT SHOW. Five axis cells appear in no rule here, so
    a fixture taken from the box would carry none of them and this gate would be green about
    a trip it never made."""
    back = _round_trip(FLAT_RULE)

    for cell, value in AXIS_CELLS_THIS_BOX_DOES_NOT_USE.items():
        assert back.get(cell) == value, "%r was dropped on the way" % cell


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the control: what carries them, and what happens without it
# ---------------------------------------------------------------------------

def test_removing_the_carrier_makes_the_property_fail():
    """🔴 THE CONTROL. Without it, ⓐ passes for any reason at all - including a converter
    that never had to carry anything because the fixture held nothing unknown.

    This is the repository's own rule from today: 「무언가를 은퇴시켰으면 그것이 «아팠던
    증상»을 대조군으로 남긴다」, in its 「property you depend on」 form. `extra` is the cell
    that carries what the grammar cannot name; drop it and the trip must lose exactly those.
    """
    internal = rule_shape.from_chain_rule(FLAT_RULE)
    assert internal["extra"], "the fixture put nothing in `extra`, so this proves nothing"

    internal.pop("extra")
    back = rule_shape.as_chain_rule(
        rule_shape.from_declaration(rule_shape.to_declaration(internal)))

    lost = sorted(k for k in FLAT_RULE if k not in back)
    assert lost, "the carrier was removed and nothing was lost, so `extra` carries nothing"
    for cell in UNKNOWN_CELLS:
        assert cell in lost, (
            "%r survived without `extra`, so ⓐ is green for a reason other than the "
            "carrier and would stay green after the carrier is broken" % cell)


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — and the two lists the classification rests on, so a rename is not silent
# ---------------------------------------------------------------------------

def test_the_axis_set_is_the_difference_between_the_two_lists():
    """⚠️ THE AXIS SET HAS NO THIRD AUTHOR. It is what the chain grammar KNOWS minus what the
    unified grammar FOLDS, and both lists already exist. A hand-kept copy of the answer would
    be a second author, and this round's whole subject is what that costs."""
    known = set(chain_bindings.routing_keys())
    folded = set(rule_shape.CHAIN_MODELLED)

    assert folded <= known, (
        "the unified grammar folds a cell the chain grammar does not know: %s"
        % sorted(folded - known))
    # ⚠️ A NUMBER, NOT A LIST OF BLESSED NAMES. Pinning the members would go red on every
    #    legitimate addition; the number going up means 「a cell was added and nobody decided
    #    where it lives」, which is the thing worth a red.
    assert len(known - folded) == 14, (
        "the axis set moved to %d - a cell was added to one list and not the other: %s"
        % (len(known - folded), sorted(known - folded)))
