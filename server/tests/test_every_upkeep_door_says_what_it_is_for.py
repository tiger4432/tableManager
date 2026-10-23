# -*- coding: utf-8 -*-
"""소유자 10-23 ㄴ · 총괄 91c799e43 — the catalog the admin help picks from: every retroactive operation and every
upkeep door outside the tab says what the operator means to do (`what_is_missing`), carries the operator's own
questions (`examples`, two at least) and the door to call next by hand (`next`, a list - empty when none). A tool
added or changed without them is red here; a retired one is marked and stays out."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                        # noqa: E402


def _catalog():
    return {**{op: spec for op, spec in retroactive.OPERATIONS.items() if not spec.get("retired")},
            **retroactive.DOORS_OUTSIDE}


def test_every_door_in_the_catalog_says_what_it_is_for_with_questions_and_the_next_door():
    catalog = _catalog()
    assert len(catalog) > len(retroactive.DOORS_OUTSIDE) > 0, "canary: the catalog reads both lists"
    missing = {name: [cell for cell in ("what_is_missing", "examples", "next") if not (
        isinstance(spec.get(cell), str) and spec[cell].strip() if cell == "what_is_missing"
        else isinstance(spec.get(cell), list) and all(isinstance(x, str) and x.strip() for x in spec[cell])
        and (cell == "next" or len(spec[cell]) >= 2))]
        for name, spec in catalog.items()}
    assert {name: cells for name, cells in missing.items() if cells} == {}


def test_a_retired_operation_is_marked_and_left_out():
    retired = [op for op, spec in retroactive.OPERATIONS.items() if spec.get("retired")]
    assert retired == [retroactive.RULE_ROWS_OP] and retired[0] not in _catalog()


def test_a_door_outside_the_tab_names_how_each_of_its_doors_is_called():
    for name, spec in retroactive.DOORS_OUTSIDE.items():
        assert spec["doors"] and all(door["name"] and door["how"] and door["when"] for door in spec["doors"]), name
        assert name not in retroactive.OPERATIONS
