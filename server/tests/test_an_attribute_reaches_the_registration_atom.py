# -*- coding: utf-8 -*-
"""S-52 gave an entity attributes and the shipped declaration died translating one.

S-52-g. Ruling 127 said an attribute is bound once on the source and folds into that
source's `register` sentence as a qualifier. The SHAPE landed -- `predicate_claim` opens one
optional qualifier per attribute -- and nothing filled the VALUE, so the shipped sample's own
`dt_job` raised a bare `KeyError: 'dt_eqp'` from inside `roleframe.say`. Two more layers were
wrong behind it: the compiled predicate signature refused the qualifier it had just opened,
and an object-less atom had nowhere to put one.

🔴 THE SUBJECT IS THE REAL TRANSLATION PATH, NOT `predicate_claim`. A unit test on that
derivation was green through all three defects, which is exactly why the ruling forbade it
here: what is scored is `dry_run_event_frame` -- the function in the traceback -- over the
SHIPPED sample and the SHIPPED catalog, both tracked. The only thing standing in for the
database is the event frame's rows, which is what `preview_cursor_batch` fetches.
"""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.envelope import registration_fingerprint, source_event_identity  # noqa: E402
from ledger.implementations import (role_mapper_registry,                    # noqa: E402
                                    trusted_implementations)
from ledger.roleframe import (SOURCE_OCCURRED_AT_COLUMN,                     # noqa: E402
                              SOURCE_ROW_REF_COLUMN, BaseLedgerMapper,
                              RoleEmission, RoleFrameError, dry_run_event_frame,
                              mapper_context)
from ledger.setup_bundle import (load_physical_catalog,                      # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                     # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
OCCURRED_AT = pd.Timestamp("2026-09-08T01:00:00+00:00")
#: ⚠️ A ROLLUP ROW SINCE S-100 ⓐ. `dt_job` used to read `dt_log` as a GROUP and count it in
#: python; the chain writes the count now and this source reads one row per job. What this
#: file is about - where an entity ATTRIBUTE comes from - did not move with it.
ROW = {"dt_job": "SYN-DTJ-002-04", "netdie_count": 3,
       "event_time": OCCURRED_AT.to_pydatetime()}


@pytest.fixture(scope="module")
def catalog():
    return load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


@pytest.fixture(scope="module")
def shipped():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def compiled(document, catalog):
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), (), catalog=catalog)


def event_frame(snapshot, source, rows):
    """What `preview_cursor_batch` hands the mapper, minus the fetch."""
    frame = pd.DataFrame(rows)
    frame[SOURCE_OCCURRED_AT_COLUMN] = OCCURRED_AT.to_pydatetime()
    frame[SOURCE_ROW_REF_COLUMN] = [f"r{index}" for index in range(len(rows))]
    event_id, _ = source_event_identity(
        source, OCCURRED_AT.to_pydatetime(), molecule_ref="m1", source_raw_ref="r1")
    frame.attrs.update({
        "source_id": source, "source_event_id": event_id, "molecule_ref": "m1",
        "source_raw_ref": "r1", "setup_snapshot_hash": snapshot.snapshot_sha256})
    return frame


def atoms(snapshot, source, rows):
    return dry_run_event_frame(
        mapper_context(snapshot, source), event_frame(snapshot, source, rows),
        role_mapper_registry()).ledger_frame


def registration(frame):
    rows = frame[frame["predicate"] == "register"]
    assert len(rows) == 1, "the shipped dt_job says `register` exactly once per unit"
    return rows.iloc[0]


def without_attributes(document):
    bare = json.loads(json.dumps(document))
    bare["entities"]["dtjob@1"].pop("attributes", None)
    bare["sources"]["dt_job"]["bind"].pop("entities", None)
    return bare


# ------------------------------------------------------------------- the value gets there

def test_the_shipped_declaration_reaches_the_registration_atom(shipped, catalog):
    """🔴 ㉠. The declaration says `dtjob@1` has an attribute `dt_eqp` and the source binds
    it to a column; nothing else is written anywhere. This is the whole of the operator's
    work, and it has to come out the far end of the real path as a qualifier on the
    registration -- which is where `registration_fingerprint` and the walk both read it."""
    row = registration(atoms(compiled(shipped, catalog), "dt_job",
                             [dict(ROW, dt_eqp="EQP-7")]))
    assert row["object_kind"] is None, "a registration still has no OBJECT"
    assert row["object_payload"] == {"qualifiers": {"dt_eqp": "EQP-7"}}
    assert registration_fingerprint(row["object_payload"]) == '{"dt_eqp":"EQP-7"}'


# ⚰️ `test_the_declarative_mapper_gets_it_from_the_same_place` STOOD HERE AND DIED WITH ITS
# SUBJECT (S-100 ⓐ). It swapped this source's CODE mapper for `declarative-role` to prove
# both fill the attribute from the same place - and `dt_job` now SHIPS declarative, so the
# swap was to what the case above already runs: two names for one assertion. The property is
# unchanged and still scored above; the half that needed a code mapper belongs to the source
# that still has one (`lot_event`), and its own file owns it.


# ------------------------------------------------------------- and the three empty answers

def test_a_null_leaves_the_qualifier_absent(shipped, catalog):
    """🔴 ㉢. An attribute is a value an entity MAY have, so an empty cell says nothing --
    it does not refuse, and it does not write a null. The atom has to be the one a
    declaration with no attributes at all writes, because `registration_fingerprint` reads
    the empty string off exactly that shape."""
    row = registration(atoms(compiled(shipped, catalog), "dt_job",
                             [dict(ROW, dt_eqp=None)]))
    assert row["object_payload"] is None
    assert registration_fingerprint(row["object_payload"]) == ""


def test_an_attribute_less_declaration_writes_the_same_atom(shipped, catalog):
    """🔴 ㉡. Taking the two declared cells back out has to leave the atom byte-identical to
    the one a NULL produces above -- the two are the same statement ("this entity, nothing
    said about it") and an atom that could tell them apart would split one registration into
    two generations."""
    with_axis = registration(atoms(compiled(shipped, catalog), "dt_job",
                                   [dict(ROW, dt_eqp=None)]))
    without = registration(atoms(compiled(without_attributes(shipped), catalog), "dt_job",
                                 [dict(ROW, dt_eqp=None)]))
    for column in ("subject_type", "subject_keys", "predicate", "object_kind",
                   "object_payload", "derivation"):
        assert repr(with_axis[column]) == repr(without[column]), column


def test_a_vocabulary_that_declares_no_attribute_compiles_the_arrays_it_declares(
        shipped, catalog):
    """🔴 ㉡, THE COMPILER'S HALF. The predicate signature is now derived through
    `predicate_claim` rather than read off `object.qualifiers`, and for a declaration with
    no attributes the two must agree TERM FOR TERM AND IN ORDER -- a set comparison would
    pass while every source's fingerprint moved."""
    snapshot = compiled(without_attributes(shipped), catalog)
    declared = without_attributes(shipped)["vocabulary"]
    assert declared, "the sample declares a vocabulary"
    for predicate_id, item in declared.items():
        compiled_predicate = snapshot.vocabulary[predicate_id]
        qualifiers = item["object"]["qualifiers"]
        assert list(compiled_predicate.required_qualifiers) == list(qualifiers["required"])
        assert list(compiled_predicate.optional_qualifiers) == list(qualifiers["optional"])


# -------------------------------------------------------------------- and the two refusals

def test_a_group_whose_rows_disagree_is_refused_by_name(shipped, catalog):
    """🔴 ㉣. `dt_job` reads a GROUP, so one unit is many rows. Two different values for one
    attribute is a question the declaration cannot answer, and quietly taking the first row
    would make the atom depend on the page order. The refusal names the column and the path
    the operator has to go to.

    ⚠️ This is `_evaluate_binding`'s existing refusal, reached rather than reimplemented:
    a second reading of one binding is how the two drift."""
    # ⚠️ THE GROUP IS DECLARED HERE NOW. `dt_job` read `dt_log` as a group until S-100 ⓐ
    # moved the grouping into the chain, so the shape this refusal is about has to be asked
    # for rather than assumed - the refusal belongs to `_evaluate_binding` and to any group
    # source, not to this one's old relation.
    grouped = json.loads(json.dumps(shipped))
    grouped["sources"]["dt_job"]["read"]["unit"] = "group"
    grouped["sources"]["dt_job"]["read"]["group_by"] = ["dt_job"]
    grouped["sources"]["dt_job"]["map"]["unit"] = {"kind": "group_by",
                                                  "columns": ["dt_job"]}
    with pytest.raises(RoleFrameError) as caught:
        atoms(compiled(grouped, catalog), "dt_job",
              [dict(ROW, dt_eqp="EQP-7"), dict(ROW, dt_eqp="EQP-8", netdie_count=4)])
    assert caught.value.code == "ambiguous_binding_value"
    # ⚠️ THE ATTRIBUTE AND THE COLUMN ARE PINNED, NOT WHICH SENTENCE REACHED THEM FIRST.
    # Both of this source's sentences bind the same `dtjob@1` subject, so both carry the
    # attribute and either may raise; naming one made this assert an evaluation ORDER that
    # nothing declares. What the operator needs from the path is the column to go and look
    # at, and that is what is scored.
    assert caught.value.path.endswith("bind.subject.attributes.dt_eqp.column")
    assert "dt_job" in caught.value.path


def test_a_mapper_that_passes_the_name_is_refused(shipped, catalog):
    """⛔ 두 주인. A mapper that fills an attribute is not being helpful: two declarations
    would decide one value, and the day they disagree the atom silently follows whichever
    ran last. The name belongs to the operator's binding, so the mapper is told so."""
    snapshot = compiled(shipped, catalog)
    context = mapper_context(snapshot, "dt_job")

    class TwoOwners(BaseLedgerMapper):
        def interpret_unit(self, context, unit, profile):
            return [RoleEmission(
                sentence="register",
                roles={"subject": {"type": "dtjob@1",
                                   "keys": {"dt_job": unit.iloc[0]["dt_job"]}},
                       "occurred_at": unit.iloc[0][SOURCE_OCCURRED_AT_COLUMN],
                       "dt_eqp": "MINE"},
                source_row_refs=(unit.iloc[0][SOURCE_ROW_REF_COLUMN],))]

    with pytest.raises(RoleFrameError) as caught:
        TwoOwners().map(
            context, event_frame(snapshot, "dt_job", [dict(ROW, dt_eqp="EQP-7")]),
            context.source_plan.driver.mapper, context.source_plan.profile)
    assert caught.value.code == "attribute_has_two_owners"
    assert "dt_eqp" in caught.value.message and "dtjob@1" in caught.value.message
