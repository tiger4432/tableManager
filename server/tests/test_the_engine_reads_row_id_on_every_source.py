# -*- coding: utf-8 -*-
"""Eleven of fifteen sources never read `row_id`, and the delete path needs all fifteen.

S-54-b / 판정 135 (Ⓐ). Ruling 132 designed the DELETE half on the premise that `row_id`
「SELECT 에 «항상» 실림」. Measured before building it: `row_id` is a column of all 44
catalogue relations, but it reached the READ for only FOUR of the fifteen shipped sources --
`dt_transfer`, `lot_event`, `transfer_event`, `wafer_process_recipe` -- and those four only
because their `order_by` or a mapper input happened to name it.

🔴 THAT MATTERS BECAUSE THE FIRST FIXTURE THE RULING NAMED SITS INSIDE THE LUCKY FOUR. A
delete path built on it would have gone green on exactly the two sources chosen to prove it,
and done nothing at all on eleven others -- 「없어서 0」 wearing 「무해해서 0」's clothes.

So the engine reads it on every source, whatever the declaration says. It is a real physical
column, not an invented one; what is engine-owned is the DECISION to read it, because an
atom has to be able to name the physical row it came from on the day that row is DELETED and
there is nothing left to translate.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import event_frame                             # noqa: E402
from ledger.implementations import trusted_implementations        # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,           # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import (compile_setup_snapshot,        # noqa: E402
                                   source_cursor_fingerprint)

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")


@pytest.fixture(scope="module")
def catalog():
    return load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


@pytest.fixture(scope="module")
def document():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def compiled(document, catalog):
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(
        bundle, trusted_implementations(), catalog=catalog)


@pytest.fixture(scope="module")
def snapshot(document, catalog):
    return compiled(document, catalog)


# --------------------------------------------------------------------- every source, not four

def test_every_source_whose_relation_has_one_reads_the_row_id(snapshot):
    """🔴 ㉮. Stated over the WHOLE shipped set rather than over a sample: the defect this
    replaces was a mechanism that worked on four of fifteen, and any fixture drawn from the
    four would have agreed with it.

    Every source reads a table that has `row_id` (총괄 f3bc02f6e), so "every" is literal."""
    without = sorted(
        name for name, plan in snapshot.source_plans.items()
        if plan.runs and event_frame.FRAME_ROW_ID_COLUMN not in
        event_frame.base_select_columns(plan))
    assert without == []
    # Seven declared, six read: `lot_event` is retired (setup_version 6) and reads nothing.
    assert len([plan for plan in snapshot.source_plans.values() if plan.runs]) == 6, (
        "the shipped sample changed size -- confirm the claim still covers all of it")


def test_the_declaration_says_nothing_about_it(document, catalog, snapshot):
    """⚠️ ENGINE-OWNED MEANS THE DECLARATION DOES NOT CARRY IT. Three shipped sources name
    `row_id` nowhere in their `read`, `prepare` or `map`, and they read it anyway -- which is
    the whole point of Ⓐ over Ⓒ (a declaration edit and a moved fingerprint each)."""
    silent = [name for name, source in document["sources"].items()
              if snapshot.source_plans[name].runs and "row_id" not in json.dumps(
                  {key: value for key, value in source.items() if key != "bind"})]
    assert len(silent) >= 3, silent
    for name in silent:
        assert event_frame.FRAME_ROW_ID_COLUMN in \
            event_frame.base_select_columns(snapshot.source_plans[name])


def test_the_name_is_scored_against_the_catalogue_and_not_against_itself(catalog,
                                                                          snapshot):
    """⚠️ EVERY OTHER ASSERTION HERE COMPARES THE CONSTANT WITH THE CONSTANT. `X in
    base_select_columns(...)` where the read was built by adding `X` is true for any
    spelling of X, so a typo in it would keep this whole file green while the read asked
    every table for a column none of them has -- and the SELECT would fail at runtime, on
    all of them at once.

    The catalogue is what decides it: a TABLE gets the column planted by the loader."""
    checked = 0
    for relation in sorted({plan.relation for plan in snapshot.source_plans.values()}):
        declared = (catalog[relation] or {}).get("columns") or {}
        names = declared if isinstance(declared, dict) else {
            (item.get("name") if isinstance(item, dict) else item) for item in declared}
        assert event_frame.FRAME_ROW_ID_COLUMN in names, relation
        checked += 1
    assert checked == 7, "the seven relations the seven shipped sources read"


# ------------------------------------------------------- and it costs no cursor a restamp

def test_the_read_is_not_what_a_cursor_fingerprint_is_made_of(snapshot, monkeypatch):
    """🔴 ㉯, AS THE REASON RATHER THAN AS A LIST OF HASHES. No fingerprint moved for this
    change, and pinning fifteen hashes here would only say so until somebody edits the
    sample legitimately. What makes it true is that the fingerprint's material is the
    DECLARATION -- so computing all fifteen must not consult the read at all.

    Measured out of process at the same time, on the same sample: 15 fingerprints, none
    moved between HEAD and this change."""
    calls = []
    real = event_frame.base_select_columns
    monkeypatch.setattr(event_frame, "base_select_columns",
                        lambda plan: calls.append(plan) or real(plan))
    fingerprints = {name: source_cursor_fingerprint(snapshot, name)
                    for name, plan in snapshot.source_plans.items() if plan.runs}
    assert len(fingerprints) == 6 and calls == [], (
        "a cursor fingerprint read the SELECT list, so an engine-owned column would "
        "restamp every source")
    # 🔴 AND THE COMPILED ANSWER IS OUT OF THE MATERIAL TOO. `source_cursor_fingerprint`
    # hashes the compiled plan, so carrying `frame_row_id` there moved all fifteen -- caught
    # by re-measuring after 판정 136, which is the same restamp cost 판정 135 chose Ⓐ to
    # avoid. It is how the engine READS, not what it says, and the atoms are byte-identical
    # either way (the test below).
    from ledger.setup_registry import _NOT_ATOM_MATERIAL

    assert "frame_row_id" in _NOT_ATOM_MATERIAL


def test_a_declaration_edit_still_moves_the_one_it_should(document, catalog, snapshot):
    """⚠️ NOT VACUOUS. The check above would also pass on a fingerprint that reacted to
    nothing at all, so this proves the material is live: edit one source's declaration and
    that source's fingerprint moves."""
    edited = json.loads(json.dumps(document))
    # The declared timezone: a one-cell edit that needs no other declaration to agree with
    # it, and that moves every atom this source writes by nine hours -- squarely inside the
    # closure the fingerprint is drawn around.
    edited["sources"]["dt_job"]["read"]["occurred_at"]["timezone"] = "UTC"
    other = compiled(edited, catalog)
    assert (source_cursor_fingerprint(snapshot, "dt_job")
            != source_cursor_fingerprint(other, "dt_job"))


# ----------------------------------------------------------------- and no atom moved either

def test_the_atoms_are_byte_identical_with_the_column_in_the_frame(snapshot):
    """🔴 ㉰. A column the declaration never named is now in every frame a mapper sees, so
    the question is whether any mapper reacts to it - translated twice, once with the column
    and once without.

    ⚠️ IT WAS MEASURED ON `dt_job`'s CODE MAPPER, "the one most likely to react", AND THAT
    MAPPER IS GONE (S-100 ⓐ): the count moved to the chain and this source now goes through
    the generic declarative mapper like every other. The case still scores something real -
    the declarative mapper is what all fifteen sources use - but it is no longer the
    adversarial one it was written to be. The remaining python mapper is `lot-event-role`,
    and its own source's tests are where that half now lives."""
    import pandas as pd
    from ledger.envelope import source_event_identity
    from ledger.implementations import role_mapper_registry
    from ledger.roleframe import (SOURCE_OCCURRED_AT_COLUMN, SOURCE_ROW_REF_COLUMN,
                                  dry_run_event_frame, mapper_context)

    occurred = pd.Timestamp("2026-09-08T01:00:00+00:00")

    def atoms(extra):
        row = {"dt_job": "J1", "netdie_count": 3, "dt_eqp": "E7",
               "event_time": occurred.to_pydatetime()}
        row.update(extra)
        frame = pd.DataFrame([row])
        frame[SOURCE_OCCURRED_AT_COLUMN] = occurred.to_pydatetime()
        frame[SOURCE_ROW_REF_COLUMN] = ["r0"]
        event_id, _ = source_event_identity(
            "dt_job", occurred.to_pydatetime(), molecule_ref="m", source_raw_ref="r")
        frame.attrs.update({
            "source_id": "dt_job", "source_event_id": event_id, "molecule_ref": "m",
            "source_raw_ref": "r", "setup_snapshot_hash": snapshot.snapshot_sha256})
        result = dry_run_event_frame(
            mapper_context(snapshot, "dt_job"), frame, role_mapper_registry())
        return [(row["predicate"], row["subject_keys"], row["object_kind"],
                 row["object_payload"])
                for _, row in result.ledger_frame.iterrows()]

    assert atoms({}) == atoms({"row_id": "RID-1"})


def test_a_misspelt_kind_is_refused_by_path(catalog, tmp_path):
    """⛔ A CLOSED LIST, REFUSED BY PATH (판정 138 ㉡). `"veiw"` would otherwise read as
    `table` and plant `row_id` back on the view -- so the typo would look exactly like never
    having written the line, which is the one failure mode this field has."""
    import io as _io
    from ledger.setup_bundle import LedgerSetupValidationError, load_physical_catalog

    document = json.loads(_io.open(
        os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8").read())
    document["dt_log"]["kind"] = "veiw"
    path = tmp_path / "table_config.json"
    _io.open(path, "w", encoding="utf-8").write(json.dumps(document))
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_physical_catalog(str(path))
    assert caught.value.code == "invalid_catalog"
    assert caught.value.path == "dt_log.kind"
    assert "veiw" in caught.value.message, "the refusal must quote what was typed"
