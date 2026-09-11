"""S-177 (1): a declaration that says "stop reading me" has its CONTENT left unread.

Owner, 2026-09-11: a declaration that cannot be read AT ALL did not take retirement.

The defect was the shape of a refusal, not a missing feature.  `status: retired` already
stopped the live path from translating a source -- `sources_for_table` filters on it, the
census sweep skips it, `backfill.run` refused it by name.  What nothing stopped was the
VALIDATOR: `_validate_sources` judged `bind`/`prepare`/`map` and `_cross_validate` judged
their columns against `table_config.json` for every source, retired or not.  So the table
an operator is free to drop once a source stops reading it is exactly the table whose
disappearance refused the WHOLE bundle -- and with the bundle refused, the ledger stops.

The split this file pins: retirement changes what is READ, and everything read is content.
The SHAPE is still judged (`exact` still refuses an unknown key, `relation` and `status`
are still checked) because the screens that show a retired source read those.
"""
from __future__ import annotations

import copy

import pytest

from ledger import setup_bundle as setup_bundle_module

from test_ledger_setup_bundle import (
    DEFAULT_CATALOG,
    binding,
    entity,
    logical_bundle,
    validate_bundle,
    validate_bundle_errors,
)
from test_ledger_setup_registry import (
    compile_setup_snapshot,
    physically_verified_joins,
    trusted_implementations,
)


#: The relation this source used to read.  ABSENT FROM `DEFAULT_CATALOG` ON PURPOSE -- the
#: owner's case is a declaration that cannot be read AT ALL, and the table being gone is
#: what makes the content unjudgeable rather than merely stale.
GONE_RELATION = "s177_gone_rows"
RETIRED_SOURCE = "s177_retired_source"


def bundle_with_a_retired_source(*, status="retired"):
    """One healthy active source plus one retired source nothing can resolve.

    Every clause of the retired source names something the catalog does not have: the
    relation, the ordering, the bound columns.  `status` is a parameter so the SAME
    fixture can be asked the two questions that must differ -- which is what makes it a
    discriminator rather than a description.
    """
    raw = copy.deepcopy(logical_bundle())
    raw["sources"][RETIRED_SOURCE] = {
        "relation": GONE_RELATION,
        "status": status,
        "read": {
            "unit": "group",
            "identity": ["gone_event"],
            "group_by": ["gone_event"],
            "order_by": ["gone_at", "gone_record"],
            "occurred_at": {"column": "gone_at", "timezone": "Asia/Seoul"},
        },
        "prepare": {
            "implementation_id": "prepare-input",
            "implementation_version": 1,
            "input_columns": ["gone_join"],
            "output_columns": {"gone_target": "string"},
            "accepts_verified_join_rules": False,
            "inherit_virtual_join_rules": [],
        },
        "map": {
            "implementation_id": "map-transition-role",
            "implementation_version": 1,
            "unit": {"kind": "event"},
            "input_columns": ["gone_source", "gone_target", "gone_at", "gone_event"],
        },
        "bind": {
            "mappings": {"gone_transition": {
                "predicate": "moves_to@1",
                "bind": {
                    "subject": entity("InputEntity@1", "input_id", "gone_source"),
                    "target": entity("OutputEntity@1", "output_id", "gone_target"),
                    "occurred_at": binding("gone_at"),
                    "event_key": binding("gone_event"),
                },
            }},
        },
    }
    return raw


def compile_fixture(raw):
    bundle = validate_bundle(raw)
    return compile_setup_snapshot(
        bundle, trusted_implementations(), physically_verified_joins(raw),
        catalog=DEFAULT_CATALOG)


# ---------------------------------------------------------------------------
# The bundle loads, and it loads BECAUSE the source is retired
# ---------------------------------------------------------------------------

def test_a_retired_source_whose_table_is_gone_does_not_refuse_the_bundle():
    assert validate_bundle_errors(bundle_with_a_retired_source()) == ()


def test_the_same_source_declared_active_is_refused_by_name():
    """The discriminator.  One word differs and the answer must differ with it -- a
    fixture both readings accept would decide nothing."""
    errors = validate_bundle_errors(bundle_with_a_retired_source(status="active"))
    assert errors, "an ACTIVE source reading a table the catalog lacks must be refused"
    paths = {error.path for error in errors}
    assert any(path.startswith("bundle.sources." + RETIRED_SOURCE)
               for path in paths), paths


def test_removing_the_retirement_test_turns_the_bundle_red(monkeypatch):
    """The guard is load-bearing: with `is_retired` answering False the bundle refuses.

    Substituted through `import`, and the substitution is asserted -- a mutation that does
    not apply reports a hole as a catch.
    """
    monkeypatch.setattr(setup_bundle_module, "is_retired", lambda item: False)
    assert setup_bundle_module.is_retired({"status": "retired"}) is False
    assert validate_bundle_errors(bundle_with_a_retired_source()), (
        "the retired source's content must be judged again once the test is removed")


# ---------------------------------------------------------------------------
# What the compiler registers for it
# ---------------------------------------------------------------------------

def test_a_retired_source_is_registered_by_name_and_status_with_no_plan():
    snapshot = compile_fixture(bundle_with_a_retired_source())

    plan = snapshot.source_plans[RETIRED_SOURCE]
    assert plan.status == "retired"
    assert plan.relation == GONE_RELATION
    # NO READ PLAN AND NO TRANSLATE PLAN.  Both were compiled from clauses the validator
    # has stopped reading, so compiling them would be the one pass still trusting content
    # nobody checked.
    assert plan.driver is None
    assert plan.profile is None
    # AND NOTHING ELSE HOLDS A BODY FOR IT EITHER -- one of these surviving would be a
    # second door into the same unread clauses.
    assert RETIRED_SOURCE not in snapshot.mappers
    assert RETIRED_SOURCE not in snapshot.profiles
    assert RETIRED_SOURCE not in snapshot.source_preparers


def test_the_active_neighbour_is_planned_in_full():
    """Retiring one source must not narrow the one beside it."""
    snapshot = compile_fixture(bundle_with_a_retired_source())

    plan = snapshot.source_plans["input_rows"]
    assert plan.status == "active"
    assert plan.driver is not None and plan.profile is not None
    assert "input_rows" in snapshot.mappers
    assert "input_rows" in snapshot.profiles
    assert "input_rows" in snapshot.source_preparers


# ---------------------------------------------------------------------------
# The entity half of the same rule
# ---------------------------------------------------------------------------

def entity_bundle_pointing_at_a_deleted_type(*, status="retired"):
    """A retired entity whose `references` names a type that is no longer declared.

    `references` is the ONE entity clause whose truth depends on something outside the
    entity, which makes it the only one an operator can falsify by deleting something
    else -- the same shape as the source's relation.
    """
    raw = copy.deepcopy(logical_bundle())
    raw["entities"]["RetiredEntity@1"] = {
        "keys": ["retired_id", "points_at"],
        "status": status,
        "references": {"points_at": {"entity_type": "DeletedEntity@1"}},
    }
    return raw


def test_a_retired_entity_may_reference_a_type_that_is_gone():
    assert validate_bundle_errors(entity_bundle_pointing_at_a_deleted_type()) == ()


def test_an_active_entity_may_not():
    errors = validate_bundle_errors(
        entity_bundle_pointing_at_a_deleted_type(status="active"))
    assert errors, "an active entity referencing an undeclared type must be refused"
    assert all(error.path.startswith("bundle.entities.RetiredEntity@1.references")
               for error in errors), errors


def test_the_cursor_fingerprint_refuses_a_retired_source_by_name():
    """⛔ NOT AN `AttributeError` THREE FRAMES DOWN. The boot re-stamp, the census sweep and
    the CLI all ask for this string in a loop; a retired source has no material to hash, and
    the loops that legitimately reach one need a word rather than a traceback."""
    from ledger.setup_bundle import LedgerSetupValidationError
    from ledger.setup_registry import source_cursor_fingerprint

    snapshot = compile_fixture(bundle_with_a_retired_source())
    with pytest.raises(LedgerSetupValidationError) as caught:
        source_cursor_fingerprint(snapshot, RETIRED_SOURCE)
    assert caught.value.code == "source_retired"
    # The active neighbour still gets one.
    assert source_cursor_fingerprint(snapshot, "input_rows")
