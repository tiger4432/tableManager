# -*- coding: utf-8 -*-
"""Lead 11-12: the migration marks an old collision merge's copy by its name - `crud.merged_layer_origin` reads back
exactly the shape that merge built (`merged_layer_name` with «<key>_<row_id[:6]>», «<row_id[:6]>» or «merged»),
nothing that merely ends in brackets."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud  # noqa: E402

UUID = "0001fcf3-a5e3-45e3-8935-00000002a5e3"


@pytest.mark.parametrize("name, origin", [
    (crud.merged_layer_name("f0086.csv", "a1b2c3"), "f0086.csv"),
    (crud.merged_layer_name("f0086.csv", "K0001_a1b2c3"), "f0086.csv"),
    (crud.merged_layer_name("f0086.csv", "K_0_01_a1b2c3"), "f0086.csv"),             # a key holding the separator
    (crud.merged_layer_name("user", "K0001_" + UUID[:6]), "user"),
    (crud.merged_layer_name("f.csv", "merged"), "f.csv"),
    (crud.merged_layer_name(crud.merged_layer_name("f.csv", "a1b2c3"), "d4e5f6"), "f.csv (a1b2c3)"),  # outer only
])
def test_a_copy_reads_back_the_name_it_was_made_from(name, origin):
    assert crud.merged_layer_origin(name) == origin


@pytest.mark.parametrize("name", [
    "report (final).csv",                                      # brackets inside a file name
    "report (final)",                                          # not the merge's tag
    "f.csv (A1B2C3)",                                          # a row_id head is lower-case hex
    "f.csv (a1b2c)",                                           # five, not six
    "f.csv (K0001-a1b2c3)",                                    # not the merge's separator
    crud.merged_layer_name("user", "old_exist_a1b2c3"),        # the person's own value the merge kept
    crud.merged_layer_name(crud.CHAIN_SOURCE, UUID),           # a chain origin layer
    crud.owned_layer_name("rule_a", "k_a1b2c3"),               # an owned layer
    "f.csv", "user", "", None,
])
def test_anything_else_is_not_a_copy(name):
    assert crud.merged_layer_origin(name) is None
