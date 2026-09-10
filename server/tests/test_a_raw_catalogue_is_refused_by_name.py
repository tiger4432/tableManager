# -*- coding: utf-8 -*-
"""어댑터를 안 지난 카탈로그는 «이름 대어» 거절된다 (S-86).

🔴 A WRONG INPUT THAT PRODUCES A PLAUSIBLE ANSWER IS WORSE THAN ONE THAT RAISES.
`validate_bundle_errors(catalog=...)` took a raw `table_config.json` document without a
word. The cross-validators then looked for `columns` - which the raw file spells
`column_types` - found none, and reported 「column 'x' is not in EventFrame schema」 about a
perfectly good declaration.

⛔ THAT SENTENCE IS TRUE OF WHAT THEY WERE GIVEN AND FALSE ABOUT THE WORLD, which is the
hardest kind of wrong to chase: it sent one lane to invent a defect (S-85) out of a
caller's mistake, and it sent this session to the same place on the same day. A loud axis
standing in front of a quiet one.

⚠️ THE REFUSAL NAMES THE FUNCTION THAT FIXES IT. 「that is not the right shape」 leaves the
caller hunting for a shape; `load_physical_catalog()` is the whole answer, so it is in the
sentence.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                          # noqa: E402

from ledger.setup_bundle import (                                      # noqa: E402
    ADAPTED_CATALOG_KEYS,
    LedgerSetupValidationError,
    load_physical_catalog,
    refuse_unadapted_catalog,
    validate_bundle_errors,
)

_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SAMPLE = os.path.join(_SERVER, "config", "sample", "table_config.json.sample")
_BUNDLE = os.path.join(_SERVER, "config", "sample", "ledger_config.json.sample")


def _raw():
    return json.load(io.open(_SAMPLE, encoding="utf-8"))


def _bundle():
    return json.load(io.open(_BUNDLE, encoding="utf-8"))


def test_the_raw_document_is_refused_and_the_fix_is_named():
    with pytest.raises(LedgerSetupValidationError) as caught:
        validate_bundle_errors(_bundle(), catalog=_raw())

    message = str(caught.value)
    assert "load_physical_catalog" in message, message
    assert "column_types" in message, "it says WHICH key gave it away"
    assert getattr(caught.value, "code", None) == "unadapted_physical_catalog"


def test_the_adapted_catalogue_is_accepted_and_the_shipped_pair_agrees():
    """⚠️ THE HALF THAT MUST NOT MOVE. The guard is a shape check, so the declaration the
    repository ships must go through it untouched."""
    assert validate_bundle_errors(_bundle(),
                                  catalog=load_physical_catalog(_SAMPLE)) == ()


def test_business_key_is_not_the_tell_because_both_shapes_have_it():
    """🔴 MEASURED, AND THE FIRST VERSION OF THIS GUARD GOT IT WRONG. `business_key` is
    emitted by the adapter AND present in the raw file under the same name, so an entry
    carrying one is evidence of nothing - the raw catalogue sailed straight through until
    the discriminator was narrowed to keys only the adapted shape can have."""
    assert "business_key" not in ADAPTED_CATALOG_KEYS
    assert ADAPTED_CATALOG_KEYS == {"columns", "composite_key"}

    with pytest.raises(LedgerSetupValidationError):
        refuse_unadapted_catalog({"t": {"business_key": "k", "column_types": {"k": "s"}}})


def test_an_empty_adapted_catalogue_is_a_legitimate_answer():
    """⛔ SHAPE, NOT CONTENT. A deployment that declares no tables has an empty catalogue,
    and refusing it would turn this guard into a second, wrong rule."""
    refuse_unadapted_catalog({})
    refuse_unadapted_catalog(None)


def test_one_adapted_entry_is_enough_to_recognise_the_shape():
    refuse_unadapted_catalog({"t": {"columns": {"a": "string"}}})
    refuse_unadapted_catalog({"t": {"composite_key": ["a"]}})


def test_something_that_is_not_a_catalogue_at_all_is_named_too():
    for wrong in ([], "table_config.json", 7):
        with pytest.raises(LedgerSetupValidationError) as caught:
            refuse_unadapted_catalog(wrong)
        assert "load_physical_catalog" in str(caught.value)


def test_an_entry_that_is_not_an_object_says_which_one():
    with pytest.raises(LedgerSetupValidationError) as caught:
        refuse_unadapted_catalog({"some_table": "not an object"})

    assert "some_table" in str(caught.value.path if hasattr(caught.value, "path")
                               else caught.value)
