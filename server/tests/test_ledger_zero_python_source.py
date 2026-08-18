"""Round 1's own pass condition: a simple source produces atoms with ZERO Python.

This is the capability the round exists to create, so it is proven by RUNNING one, not by
asserting that the pieces are present.

The source below is declared entirely in config. It names `direct-join` (no joins, so it
computes nothing) and `declarative-role` (it executes the Profile's bindings). Both are
generic implementations that already existed in the repository and were unreachable from
every config file until the trusted set stopped being a hand-kept list -- compiling this
bundle before that change failed with `untrusted_implementation`, which is precisely why
"a simple source needs no Python" was not true.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.implementations import (                                     # noqa: E402
    role_mapper_registry,
    source_preparer_registry,
    trusted_implementations,
)
from ledger.roleframe import DeclarativeRoleMapper                       # noqa: E402
from ledger.runtime_v2 import preview_cursor_batch                       # noqa: E402
from ledger.setup_bundle import require_ready_bundle, validate_bundle    # noqa: E402
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from ledger.source_preparation import (                                  # noqa: E402
    DirectJoinSourcePreparer,
    VerifiedJoinBatchReader,
)


def _approved(**extra):
    return dict(binding_origin="user_declared", approval_status="approved", **extra)


def _column(name):
    return _approved(kind="column", column=name)


#: One whole source. No module, no function, no path -- `setup_bundle` forbids those keys,
#: and nothing here needs them.
SHIPMENT_SETUP = {
    "setup_version": 3,
    "virtual_joins": {},
    "vocabulary": {"register@1": {
        "status": "active", "layer": "ontology", "subjects": ["Box@1"],
        "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}},
    "entities": {"Box@1": {"keys": ["box"]}},
    "source_preparers": {"plain@1": {
        "implementation_id": "direct-join", "implementation_version": 1,
        "input_columns": [], "output_columns": {},
        "accepts_verified_join_rules": False}},
    "mappers": {"plain-role@1": {
        "implementation_id": "declarative-role", "implementation_version": 1,
        "unit": {"kind": "row"},
        "input_columns": ["shipment_id", "box", "shipped_at"],
        "emits": ["shipping@1/first_sight"]}},
    "packs": {"shipping@1": {"claims": {"first_sight": {
        "roles": {"subject": {"kind": "entity", "required": True},
                  "occurred_at": {"kind": "time", "required": True}},
        "emit": {"predicate": "register@1", "subject": "$subject",
                 "object": {"kind": "none"}, "occurred_at": "$occurred_at"}}}}},
    "profiles": {"shipping@1": {
        "source": "shipment", "packs": ["shipping@1"],
        "mappings": [{
            "mapping_id": "first_sight_box", "use": "shipping@1/first_sight",
            "bind": {
                "subject": _approved(kind="entity", entity_type="Box@1",
                                     keys={"box": _column("box")}),
                "occurred_at": _column("shipped_at")}}]}},
    "sources": {"shipment": {
        "relation": "shipment",
        "profile_id": "shipping@1",
        "driver": {
            "unit": "row",
            "identity": ["shipment_id"],
            "group_by": [],
            "order_by": ["shipment_id"],
            "occurred_at": {"column": "shipped_at", "timezone": "Asia/Seoul"},
            "cursor": {"columns": ["shipped_at", "shipment_id"]},
            "preparation": {"preparer_id": "plain@1",
                            "inherit_virtual_join_rules": []},
            "mapper_id": "plain-role@1",
            "registration_probe": [
                {"entity_type": "Box@1", "columns": ["box"]}],
        }}},

}


#: The PHYSICAL half of the same deployment -- what `server/config/table_config.json`
#: holds for a real one.  It is written out here rather than inside `SHIPMENT_SETUP` and
#: is never derived from it: the ledger dropped its own `tables` section because a
#: physical claim it made about itself was checked against nothing, and a catalog computed
#: from the setup under test would restore exactly that.
SHIPMENT_CATALOG = {
    "shipment": {
        "columns": {"shipment_id": "string", "box": "string",
                    "shipped_at": "datetime"},
        "business_key": "shipment_id",
    },
}


class _NoJoin(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("a simple source reads no joins")


@pytest.fixture(scope="module")
def snapshot():
    bundle = require_ready_bundle(
        validate_bundle(SHIPMENT_SETUP, catalog=SHIPMENT_CATALOG))
    return compile_setup_snapshot(
        bundle, trusted_implementations(), (), catalog=SHIPMENT_CATALOG)


@pytest.fixture
def rows():
    return pd.DataFrame([
        {"shipment_id": "S1", "box": "BX-01",
         "shipped_at": pd.Timestamp("2026-08-01T09:00:00", tz="Asia/Seoul")},
        {"shipment_id": "S2", "box": "BX-02",
         "shipped_at": pd.Timestamp("2026-08-01T10:00:00", tz="Asia/Seoul")},
    ])


def test_a_config_only_source_produces_atoms(snapshot, rows):
    preview = preview_cursor_batch(
        snapshot, "shipment", rows,
        {"shipped_at": rows.iloc[-1]["shipped_at"], "shipment_id": "S2"},
        _NoJoin(), source_preparer_registry(), role_mapper_registry(),
        known_registrations=(),
    )
    assert preview.molecule_count == 2
    assert preview.atom_count == 2
    assert preview.incomplete_count == 0
    assert [(a["subject_type"], a["subject_keys"], a["predicate"])
            for a in preview.candidate_semantics] == [
        ("Box", {"box": "BX-01"}, "register"),
        ("Box", {"box": "BX-02"}, "register"),
    ]


def test_the_source_is_served_by_generic_implementations_and_no_source_specific_code(
    snapshot,
):
    """No file anywhere is about `shipment`; both implementations serve any source."""
    plan = snapshot.source_plans["shipment"]
    assert source_preparer_registry().resolve(
        plan.driver.preparation.preparer.implementation).__class__ \
        is DirectJoinSourcePreparer
    assert role_mapper_registry().resolve(
        plan.driver.mapper.implementation).__class__ is DeclarativeRoleMapper


def test_first_sight_suppression_is_declaration_driven_for_this_source(snapshot, rows):
    """The probe that used to name lot_event's columns now answers for this table too."""
    from ledger.backfill import _v2_registration_subjects
    from ledger.envelope import canonical_keys

    subjects = _v2_registration_subjects(snapshot.source_plans["shipment"], rows)
    assert subjects == {
        ("Box", canonical_keys({"box": "BX-01"})),
        ("Box", canonical_keys({"box": "BX-02"})),
    }


def test_a_second_sight_is_suppressed_so_register_lands_once(snapshot, rows):
    """The whole point of the probe: a subject already in the store emits no register."""
    from ledger.envelope import canonical_keys

    preview = preview_cursor_batch(
        snapshot, "shipment", rows,
        {"shipped_at": rows.iloc[-1]["shipped_at"], "shipment_id": "S2"},
        _NoJoin(), source_preparer_registry(), role_mapper_registry(),
        known_registrations=(("Box", canonical_keys({"box": "BX-01"})),),
    )
    assert preview.atom_count == 1
    assert preview.candidate_semantics[0]["subject_keys"] == {"box": "BX-02"}
